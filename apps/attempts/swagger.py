"""
OpenAPI / Swagger documentation for the attempts app (drf-spectacular).

The attempts app is the engine between assignments and results: **Submissions** for
exams (one MockTest per ExamAssignment) and homework (MockTest or Quiz per item).

**Security & anti-cheat (visibility isolation):**
- **start-exam** and **homework-start** return a **sanitized** paper: the response MUST
  NOT include `correct_option_index` or `is_correct` in any question/option. Only
  option text and structure are returned so students cannot see correct answers.
- Stored **results** after grading do not expose `correct_index`; only `correct`
  (bool), `score`, and `selected_index` (student's choice) are stored.

**Immutability:**
- Only **STARTED** submissions can be submitted. Once **GRADED**, re-submit and
  edit/delete are blocked with **400** or **403**.
- **PUT/PATCH/DELETE** on a submission with status GRADED return **400**:
  \"Cannot modify a graded submission. Results are immutable.\"

**Snapshot & historical integrity:**
- At grading time, **create_snapshot** saves the full MockTest/Quiz structure
  (including correct answers) into `Submission.snapshot`. If a teacher later
  deletes a question or changes the correct answer, the student's historical
  result remains unchanged.

**JLPT scoring engine:**
- **Sectional pass:** FAIL if total score is above pass mark but any single
  section is below minimum (e.g. <19 for N1–N3).
- **N4/N5:** Vocabulary, Grammar, and Reading are aggregated into one section
  (120 pts, min 38); Listening separate (60 pts, min 19).
- All calculations use **Decimal** to avoid floating-point errors.

**Workflow:**
- **start-exam** is only allowed when **ExamAssignment.status** is **OPEN**
  (enforced by CanStartExam permission and StartExamService).
- **Time taken:** `time_taken_seconds` = completed_at − started_at (for dashboard).

**Role-based queryset & performance:**
- **TEACHER:** Only submissions from groups where they teach.
- **STUDENT/GUEST:** Only their own submissions.
- List view batch-fetches student names via **user_map** (public schema) to avoid N+1.
"""
from drf_spectacular.utils import (
    OpenApiExample,
    OpenApiParameter,
    OpenApiResponse,
    extend_schema,
    extend_schema_view,
)

from .serializers import (
    SubmissionSerializer,
    SubmissionResultSerializer,
    SubmissionAnswerSerializer,
)

RESP_400 = OpenApiResponse(
    description="Validation error: not STARTED, missing answers, past deadline, or re-submit on GRADED.",
    examples=[
        OpenApiExample(
            "Already submitted",
            value={"detail": "Only STARTED submissions can be submitted. This attempt is already submitted or graded."},
            response_only=True,
        ),
        OpenApiExample(
            "Graded immutable",
            value={"detail": "Cannot modify a graded submission. Results are immutable."},
            response_only=True,
        ),
    ],
)
RESP_401 = OpenApiResponse(description="Authentication required.")
RESP_403 = OpenApiResponse(
    description="Permission denied: e.g. only students can start/submit; exam not OPEN."
)
RESP_404 = OpenApiResponse(description="Submission or assignment not found.")

# ---- Answers payload: {"question_uuid": selected_option_index} ----
ANSWERS_EXAMPLE = {
    "550e8400-e29b-41d4-a716-446655440000": 2,
    "660e8400-e29b-41d4-a716-446655440001": 0,
    "770e8400-e29b-41d4-a716-446655440002": 1,
}
ANSWERS_DESCRIPTION = "Object: question UUID (string) -> selected option index (0-based integer)."

# ---- Results response (JLPT): sections breakdown + jlpt_result ----
RESULTS_JLPT_EXAMPLE = {
    "total_score": 95.5,
    "sections": {
        "section-uuid-1": {
            "section_id": "section-uuid-1",
            "section_name": "Vocabulary",
            "section_type": "VOCAB",
            "score": 28.0,
            "max_score": 60.0,
            "questions": {
                "question-uuid-1": {"correct": True, "score": 1.0, "selected_index": 2},
                "question-uuid-2": {"correct": False, "score": 0.0, "selected_index": 0},
            },
        },
    },
    "jlpt_result": {
        "level": "N2",
        "total_score": 95.5,
        "pass_mark": 90,
        "passed": True,
        "section_results": {
            "language_knowledge": {"score": 32.0, "min_required": 19, "passed": True},
            "reading": {"score": 35.5, "min_required": 19, "passed": True},
            "listening": {"score": 28.0, "min_required": 19, "passed": True},
        },
        "total_passed": True,
        "all_sections_passed": True,
    },
    "resource_type": "mock_test",
}

submission_viewset_schema = extend_schema_view(
    list=extend_schema(
        tags=["Submissions"],
        summary="List submissions",
        description=(
            "CENTER_ADMIN: all. TEACHER: submissions for groups they teach. "
            "STUDENT/GUEST: own only. **Performance:** student_display is batch-fetched via user_map (public schema)."
        ),
        parameters=[
            OpenApiParameter(name="exam_assignment_id", type=str, ),
            OpenApiParameter(name="homework_assignment_id", type=str, ),
            OpenApiParameter(name="ordering", type=str),
        ],
        responses={200: SubmissionSerializer(many=True), 401: RESP_401, 403: RESP_403},
    ),
    retrieve=extend_schema(
        tags=["Submissions"],
        summary="Get submission",
        responses={200: SubmissionSerializer, 401: RESP_401, 403: RESP_403, 404: RESP_404},
    ),
    update=extend_schema(
        tags=["Submissions"],
        summary="Update submission (partial)",
        description="**Blocked** if status is GRADED (400: results are immutable).",
        responses={200: SubmissionSerializer, 400: RESP_400, 401: RESP_401, 403: RESP_403, 404: RESP_404},
    ),
    partial_update=extend_schema(
        tags=["Submissions"],
        summary="Partial update submission",
        description="**Blocked** if status is GRADED (400: results are immutable).",
        responses={200: SubmissionSerializer, 400: RESP_400, 401: RESP_401, 403: RESP_403, 404: RESP_404},
    ),
    destroy=extend_schema(
        tags=["Submissions"],
        summary="Delete submission",
        description="**Blocked** if status is GRADED (400: results are immutable).",
        responses={204: OpenApiResponse(description="Deleted."), 400: RESP_400, 401: RESP_401, 403: RESP_403, 404: RESP_404},
    ),
    start_exam=extend_schema(
        tags=["Submissions – Exam"],
        summary="Start exam",
        description=(
            "Start an exam attempt. Returns **sanitized** exam paper (MockTest structure "
            "without correct_option_index or is_correct). Only STUDENT/GUEST. "
            "**ExamAssignment.status must be OPEN** (enforced by CanStartExam)."
        ),
        request={
            "application/json": {
                "type": "object",
                "required": ["exam_assignment_id"],
                "properties": {"exam_assignment_id": {"type": "string", "format": "uuid"}},
            }
        },
        responses={
            201: OpenApiResponse(
                description="submission_id, started_at, exam_paper (no correct answers).",
                examples=[
                    OpenApiExample(
                        "Success",
                        value={
                            "submission_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
                            "started_at": "2025-01-29T10:00:00Z",
                            "exam_paper": {
                                "id": "550e8400-e29b-41d4-a716-446655440000",
                                "title": "JLPT N5 Mock",
                                "level": "N5",
                                "description": "",
                                "pass_score": 90,
                                "total_score": 180,
                                "sections": [],
                            },
                            "message": "Exam started successfully. Timer begins now.",
                        },
                        response_only=True,
                    ),
                ],
            ),
            400: RESP_400,
            401: RESP_401,
            403: RESP_403,
        },
        examples=[
            OpenApiExample(
                "Request",
                value={"exam_assignment_id": "550e8400-e29b-41d4-a716-446655440000"},
                request_only=True,
            ),
        ],
    ),
    submit_exam=extend_schema(
        tags=["Submissions – Exam"],
        summary="Submit exam",
        description=(
            "Submit exam answers. Only **STARTED** submissions; once submitted status becomes "
            "**GRADED** (immutable). Re-submit on GRADED returns 400. Grading is atomic."
        ),
        request={
            "application/json": {
                "type": "object",
                "required": ["submission_id", "answers"],
                "properties": {
                    "submission_id": {"type": "string", "format": "uuid"},
                    "answers": {
                        "type": "object",
                        "additionalProperties": {"type": "integer"},
                        "description": ANSWERS_DESCRIPTION,
                    },
                },
            }
        },
        responses={
            200: OpenApiResponse(
                description="Submission received; result under review until teacher publishes.",
                examples=[
                    OpenApiExample(
                        "Success",
                        value={
                            "submission_id": "uuid",
                            "status": "GRADED",
                            "message": "Submission received. Your result is under review.",
                            "note": "Results will be visible after the teacher publishes them.",
                        },
                        response_only=True,
                    ),
                ],
            ),
            400: RESP_400,
            401: RESP_401,
            403: RESP_403,
        },
        examples=[
            OpenApiExample(
                "Request",
                value={"submission_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890", "answers": ANSWERS_EXAMPLE},
                request_only=True,
            ),
        ],
    ),
    my_results=extend_schema(
        tags=["Submissions – Exam"],
        summary="My exam results",
        description=(
            "GET student's own exam result. Only if **ExamAssignment.is_published** is True. "
            "Includes time_taken_seconds (completed_at − started_at) and percentage for dashboard."
        ),
        parameters=[OpenApiParameter(name="exam_assignment_id", type=str, required=True)],
        responses={
            200: OpenApiResponse(
                description="submission (score, results, time_taken_seconds, percentage) if published.",
                examples=[
                    OpenApiExample(
                        "Success",
                        value={
                            "submission": {
                                "id": "uuid",
                                "user_id": 1,
                                "status": "GRADED",
                                "score": 95.5,
                                "results": RESULTS_JLPT_EXAMPLE,
                                "time_taken_seconds": 3600,
                                "percentage": 53.06,
                            },
                            "is_published": True,
                        },
                        response_only=True,
                    ),
                ],
            ),
            404: OpenApiResponse(description="No graded submission or not published."),
            401: RESP_401,
            403: RESP_403,
        },
    ),
    start_homework_item=extend_schema(
        tags=["Submissions – Homework"],
        summary="Homework start",
        description=(
            "Start a homework item (MockTest or Quiz). Returns **sanitized** item paper "
            "(no correct_option_index or is_correct). Deadline must not have passed."
        ),
        request={
            "application/json": {
                "type": "object",
                "required": ["homework_assignment_id", "item_type", "item_id"],
                "properties": {
                    "homework_assignment_id": {"type": "string", "format": "uuid"},
                    "item_type": {"type": "string", "enum": ["mock_test", "quiz"]},
                    "item_id": {"type": "string", "format": "uuid"},
                },
            }
        },
        responses={
            201: OpenApiResponse(
                description="submission_id, started_at, item_data (sanitized), item_type.",
                examples=[
                    OpenApiExample(
                        "Success",
                        value={
                            "submission_id": "uuid",
                            "started_at": "2025-01-29T10:00:00Z",
                            "item_data": {"id": "uuid", "title": "JLPT N5 Mock", "sections": []},
                            "item_type": "mock_test",
                            "message": "Homework item started successfully.",
                        },
                        response_only=True,
                    ),
                ],
            ),
            400: RESP_400,
            401: RESP_401,
            403: RESP_403,
        },
        examples=[
            OpenApiExample(
                "Request",
                value={
                    "homework_assignment_id": "550e8400-e29b-41d4-a716-446655440000",
                    "item_type": "mock_test",
                    "item_id": "660e8400-e29b-41d4-a716-446655440001",
                },
                request_only=True,
            ),
        ],
    ),
    show_result=extend_schema(
        tags=["Submissions – Homework"],
        summary="Show result (practice)",
        description=(
            "Practice mode: returns grading result **WITHOUT** saving or locking. "
            "**GUEST forbidden.** Submission stays STARTED; student can retry before final submit."
        ),
        request={
            "application/json": {
                "type": "object",
                "required": ["submission_id", "answers"],
                "properties": {
                    "submission_id": {"type": "string", "format": "uuid"},
                    "answers": {
                        "type": "object",
                        "additionalProperties": {"type": "integer"},
                        "description": ANSWERS_DESCRIPTION,
                    },
                },
            }
        },
        responses={
            200: OpenApiResponse(
                description="results (same format as submit); submission not locked.",
                examples=[
                    OpenApiExample(
                        "Success",
                        value={
                            "submission_id": "uuid",
                            "status": "STARTED",
                            "results": RESULTS_JLPT_EXAMPLE,
                            "message": "Practice results. You can retry before submitting.",
                            "note": "This is practice mode. Your submission is not locked.",
                        },
                        response_only=True,
                    ),
                ],
            ),
            400: RESP_400,
            401: RESP_401,
            403: RESP_403,
        },
        examples=[
            OpenApiExample(
                "Request",
                value={"submission_id": "uuid", "answers": ANSWERS_EXAMPLE},
                request_only=True,
            ),
        ],
    ),
    submit_homework=extend_schema(
        tags=["Submissions – Homework"],
        summary="Submit homework",
        description=(
            "Final submit: grades and **locks** submission (status GRADED). Only STARTED. "
            "If homework_assignment.show_results_immediately is True, returns results in response. "
            "Re-submit on GRADED returns 400."
        ),
        request={
            "application/json": {
                "type": "object",
                "required": ["submission_id", "answers"],
                "properties": {
                    "submission_id": {"type": "string", "format": "uuid"},
                    "answers": {
                        "type": "object",
                        "additionalProperties": {"type": "integer"},
                        "description": ANSWERS_DESCRIPTION,
                    },
                },
            }
        },
        responses={
            200: OpenApiResponse(
                description="submission_id, status GRADED, message; optionally results if show_results_immediately.",
                examples=[
                    OpenApiExample(
                        "With results",
                        value={
                            "submission_id": "uuid",
                            "status": "GRADED",
                            "message": "Homework submitted successfully. Your submission is now locked.",
                            "results": RESULTS_JLPT_EXAMPLE,
                            "note": "Results are shown immediately as configured.",
                        },
                        response_only=True,
                    ),
                ],
            ),
            400: RESP_400,
            401: RESP_401,
            403: RESP_403,
        },
        examples=[
            OpenApiExample(
                "Request",
                value={"submission_id": "uuid", "answers": ANSWERS_EXAMPLE},
                request_only=True,
            ),
        ],
    ),
    my_homework_results=extend_schema(
        tags=["Submissions – Homework"],
        summary="My homework results",
        description=(
            "GET student's graded submissions for a homework assignment. "
            "Each item includes time_taken_seconds (completed_at − started_at). "
            "results included per item only if show_results_immediately is True."
        ),
        parameters=[OpenApiParameter(name="homework_assignment_id", type=str, required=True)],
        responses={
            200: OpenApiResponse(
                description="homework_id, homework_title, show_results_immediately, submissions (score, time_taken_seconds, results if shown).",
                examples=[
                    OpenApiExample(
                        "Success",
                        value={
                            "homework_id": "uuid",
                            "homework_title": "Week 3 Homework",
                            "show_results_immediately": True,
                            "submissions": [
                                {
                                    "submission_id": "uuid",
                                    "item_type": "mock_test",
                                    "item_id": "uuid",
                                    "item_title": "JLPT N5 Mock",
                                    "status": "GRADED",
                                    "score": 95.5,
                                    "started_at": "2025-01-29T10:00:00Z",
                                    "completed_at": "2025-01-29T11:00:00Z",
                                    "time_taken_seconds": 3600,
                                    "results": RESULTS_JLPT_EXAMPLE,
                                },
                            ],
                        },
                        response_only=True,
                    ),
                ],
            ),
            401: RESP_401,
            403: RESP_403,
        },
    ),
)
