"""
OpenAPI / Swagger documentation for the attempts app (drf-spectacular).

The attempts app is the scoring heart between assignments and results: **Submissions** for
exams (one MockTest per ExamAssignment) and homework (MockTest or Quiz per item).

================================================================================
EXAM / HOMEWORK LIFECYCLE STATE MACHINE
================================================================================

**Status values:** STARTED → (SUBMITTED) → GRADED

**Current API transitions:**
- `start-exam` / `homework-start` creates **STARTED** submissions.
- `submit-exam` / `submit-homework` grade immediately and set **GRADED**.

**Immutability:**
- Only **STARTED** can be submitted. Once **GRADED**, re-submit and edit/delete are blocked.
- PUT/PATCH/DELETE on GRADED → 400: "Cannot modify a graded submission. Results are immutable."

================================================================================
ANSWER PROTECTION (ANTI-CHEAT)
================================================================================

**start-exam** and **homework-start** return a **sanitized** paper. The response MUST NOT include:
- Question.correct_option_index
- Option.is_correct

Options are returned with text only. This is enforced by `ExamQuestionSerializer` and
`QuizQuestionPaperSerializer` which strip `is_correct` and exclude `correct_option_index`.

================================================================================
SECURITY ISOLATION (TENANT + OWNERSHIP)
================================================================================

- **Students/GUests can only access their own submissions.**
- Cross-center submission attempts are rejected with 403.
- TEACHER visibility is limited to groups they teach; CENTER_ADMIN sees all.

================================================================================
JLPT SCORING ENGINE (RESULTS JSON)
================================================================================

**MockTest Results (`results` JSONField):**
- `total_score`: float
- `sections`: map of section_id → {section_name, section_type, score, max_score, questions}
- `jlpt_result`: {level, pass_mark, passed, section_results, total_passed, all_sections_passed}
- `resource_type`: "mock_test"

**Quiz Results (`results` JSONField):**
- `total_score`, `max_score`, `correct_count`, `total_count`, `percentage`
- `questions`: map of question_id → {correct, score, points, selected_index}
- `resource_type`: "quiz"

**Pass/Fail Rules:**
- **N1–N3:** 3 sections — Language Knowledge, Reading, Listening (min 19 each)
- **N4–N5:** 2 sections — Language+Reading combined (min 38), Listening (min 19)
- **PASS** requires both `total_passed` and `all_sections_passed`

================================================================================
RACE-CONDITION PROTECTION & SINGLE ATTEMPT GUARANTEE
================================================================================

- DB-level **UniqueConstraint** enforces one attempt per user per assignment.
- Start-exam uses `transaction.atomic()`; on IntegrityError:
    - If existing is **STARTED**, returns/resumes.
    - If **SUBMITTED/GRADED**, returns 400 (already completed).

================================================================================
AUTO-SUBMIT GRACE PERIOD (SERVER-SIDE)
================================================================================

- After the deadline, the server allows a **10-minute grace period** before auto-submit locks.
- After grace ends, submissions are locked and return 400 if attempted.

================================================================================
PERFORMANCE NOTES
================================================================================

- List view batch-fetches student names via **user_map** (public schema) to avoid N+1.
- `time_taken_seconds` = completed_at − started_at (dashboard).
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
    description=(
        "Validation error: not STARTED, missing answers, past deadline, already completed, "
        "exam not OPEN, or resource not PUBLISHED/ACTIVE."
    ),
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
        OpenApiExample(
            "Exam not open",
            value={"detail": "Exam is not open. Current status: CLOSED"},
            response_only=True,
        ),
        OpenApiExample(
            "Homework deadline passed",
            value={"detail": "Homework deadline has passed."},
            response_only=True,
        ),
        OpenApiExample(
            "MockTest not published",
            value={"detail": "Mock test is not published."},
            response_only=True,
        ),
    ],
)
RESP_401 = OpenApiResponse(description="Authentication required.")
RESP_403 = OpenApiResponse(
    description="Permission denied: only students can start/submit; cross-center or ownership violation.",
    examples=[
        OpenApiExample(
            "Cross-center submission",
            value={"detail": "Cross-center submission is not allowed."},
            response_only=True,
        ),
        OpenApiExample(
            "Not owner",
            value={"detail": "You can only submit your own submissions."},
            response_only=True,
        ),
        OpenApiExample(
            "Role blocked",
            value={"detail": "Only students can start exams."},
            response_only=True,
        ),
    ],
)
RESP_404 = OpenApiResponse(description="Submission or assignment not found.")

# ---- Answers payload: {"question_uuid": selected_option_index} ----
ANSWERS_EXAMPLE = {
    "550e8400-e29b-41d4-a716-446655440000": 2,
    "660e8400-e29b-41d4-a716-446655440001": 0,
    "770e8400-e29b-41d4-a716-446655440002": 1,
}
ANSWERS_DESCRIPTION = "Object: question UUID (string) -> selected option index (0-based integer)."

RESULTS_SCHEMA_DESCRIPTION = (
    "Results JSON schema for frontend charts: "
    "MockTest: {total_score, sections{section_id:{section_name, section_type, score, max_score, questions}}, "
    "jlpt_result{level, pass_mark, passed, section_results, total_passed, all_sections_passed}, resource_type}. "
    "Quiz: {total_score, max_score, correct_count, total_count, percentage, questions, resource_type}."
)

# ---- Results response (JLPT): sections breakdown + jlpt_result ----
RESULTS_JLPT_EXAMPLE = {
    "total_score": 112.0,
    "sections": {
        "section-uuid-vocab": {
            "section_id": "section-uuid-vocab",
            "section_name": "Vocabulary",
            "section_type": "VOCAB",
            "score": 32.0,
            "max_score": 60.0,
            "questions": {
                "question-uuid-1": {"correct": True, "score": 1.0, "selected_index": 2},
                "question-uuid-2": {"correct": False, "score": 0.0, "selected_index": 0},
            },
        },
        "section-uuid-reading": {
            "section_id": "section-uuid-reading",
            "section_name": "Reading",
            "section_type": "GRAMMAR_READING",
            "score": 40.0,
            "max_score": 60.0,
            "questions": {
                "question-uuid-3": {"correct": True, "score": 2.0, "selected_index": 1},
            },
        },
        "section-uuid-listening": {
            "section_id": "section-uuid-listening",
            "section_name": "Listening",
            "section_type": "LISTENING",
            "score": 40.0,
            "max_score": 60.0,
            "questions": {
                "question-uuid-4": {"correct": True, "score": 2.0, "selected_index": 3},
            },
        },
    },
    "jlpt_result": {
        "level": "N2",
        "total_score": 112.0,
        "pass_mark": 90,
        "passed": True,
        "section_results": {
            "language_knowledge": {"score": 32.0, "min_required": 19, "passed": True},
            "reading": {"score": 40.0, "min_required": 19, "passed": True},
            "listening": {"score": 40.0, "min_required": 19, "passed": True},
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
        description=(
            "Retrieve a submission. **Security isolation:** students/guests can only access their own submissions; "
            "cross-center access is forbidden."
        ),
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
            "**ExamAssignment.status must be OPEN** (enforced by CanStartExam). "
            "**Race-safe:** one attempt per user; if already STARTED, the existing attempt is resumed; "
            "if already SUBMITTED/GRADED, returns 400."
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
            "**GRADED** (immutable). Re-submit on GRADED returns 400. Grading is atomic. "
            "**Security:** students can submit only their own submissions; cross-center rejected (403)."
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
            "Includes time_taken_seconds (completed_at − started_at) and percentage for dashboard. "
            f"{RESULTS_SCHEMA_DESCRIPTION}"
        ),
        parameters=[OpenApiParameter(name="exam_assignment_id", type=str, required=True)],
        responses={
            200: OpenApiResponse(
                description="submission (score, results, time_taken_seconds, percentage) if published.",
                examples=[
                    OpenApiExample(
                        "GRADED result (JLPT breakdown)",
                        value={
                            "submission": {
                                "id": "uuid",
                                "user_id": 1,
                                "status": "GRADED",
                                "score": 112.0,
                                "results": RESULTS_JLPT_EXAMPLE,
                                "time_taken_seconds": 3600,
                                "percentage": 62.22,
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
            "(no correct_option_index or is_correct). Deadline must not have passed. "
            "**Grace period:** 10 minutes after deadline before auto-submit lock."
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
            "**GUEST forbidden.** Submission stays STARTED; student can retry before final submit. "
            f"{RESULTS_SCHEMA_DESCRIPTION}"
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
            "Re-submit on GRADED returns 400. "
            "**Grace period:** 10 minutes after deadline before auto-submit lock. "
            f"{RESULTS_SCHEMA_DESCRIPTION}"
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
