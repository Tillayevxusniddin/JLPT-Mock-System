"""
OpenAPI / Swagger documentation for the assignments app (drf-spectacular).

Assignments bridge educational resources and students: **ExamAssignment** (one MockTest
per exam room) and **HomeworkAssignment** (multiple MockTests/Quizzes, groups and/or
assigned_user_ids).

**Visibility (get_queryset):**
- **CENTER_ADMIN:** All assignments in the center.
- **TEACHER:** Only assignments linked to groups where they are members with role TEACHER.
- **STUDENT:** **Exams** — assignments linked to their group. **Homework** — assignments
  linked to their group OR where their User ID is in `assigned_user_ids`.
- **GUEST:** Only homework where their User ID is in `assigned_user_ids`.
- List views use `.distinct()` where needed to avoid duplicate rows.

**ExamAssignment.status (CLOSED / OPEN):**
- **CLOSED:** Students do not see this assignment in the exam room.
- **OPEN:** Students can see and access the assignment in the exam room. Teacher/CenterAdmin
  controls status; changing to OPEN makes the exam visible to assigned groups.

**Resource constraints & validation:**
- Only **PUBLISHED** MockTests and **ACTIVE** Quizzes can be assigned.
- Homework **deadline** must be in the future (400 if past).
- **assigned_user_ids:** List of **integers** (User IDs from the **public schema**). All IDs
  must exist in the public User table and belong to the **current center**; otherwise 400.

**Performance:** List actions batch-fetch `created_by` (Public User) via `user_map` (single
public-schema query). Homework retrieve uses one batch query for Submissions (zero N+1).
"""
from drf_spectacular.utils import (
    OpenApiExample,
    OpenApiParameter,
    OpenApiResponse,
    extend_schema,
    extend_schema_view,
)

from .serializers import (
    ExamAssignmentSerializer,
    HomeworkAssignmentSerializer,
    HomeworkDetailSerializer,
)

# -----------------------------------------------------------------------------
# Reusable responses
# -----------------------------------------------------------------------------

RESP_400 = OpenApiResponse(
    description=(
        "Validation error: mock_test not PUBLISHED, quiz not ACTIVE, past deadline, "
        "invalid resource IDs, or assigned_user_ids not in current center."
    ),
    examples=[
        OpenApiExample(
            "Past deadline",
            value={"deadline": "Deadline must be in the future."},
            response_only=True,
        ),
        OpenApiExample(
            "Invalid resource",
            value={"mock_test_ids": "MockTest '...' is not PUBLISHED."},
            response_only=True,
        ),
        OpenApiExample(
            "User IDs not in center",
            value={"assigned_user_ids": "The following user IDs do not belong to this center: [99]."},
            response_only=True,
        ),
    ],
)
RESP_401 = OpenApiResponse(description="Authentication required.")
RESP_403 = OpenApiResponse(
    description="Permission denied: e.g. teacher managing assignments for groups they do not teach."
)
RESP_404 = OpenApiResponse(description="Assignment not found.")

# -----------------------------------------------------------------------------
# ExamAssignment
# -----------------------------------------------------------------------------

EXAM_LIST_DESC = """
List exam assignments. **Visibility:** CENTER_ADMIN all; TEACHER only groups they teach;
STUDENT only their groups; GUEST none. **Performance:** `created_by` from public schema (user_map).
"""
EXAM_RETRIEVE_DESC = "Retrieve an exam assignment. Same visibility as list."
EXAM_CREATE_DESC = (
    "Create exam assignment. CENTER_ADMIN or TEACHER. mock_test must be PUBLISHED. "
    "**status:** CLOSED = not visible in exam room; OPEN = visible to assigned groups."
)
EXAM_UPDATE_DESC = "Update exam assignment. CENTER_ADMIN or teacher for assigned groups."
EXAM_DESTROY_DESC = "Delete exam assignment. CENTER_ADMIN or teacher for assigned groups."

exam_assignment_viewset_schema = extend_schema_view(
    list=extend_schema(
        tags=["Exam Assignments"],
        summary="List exam assignments",
        description=EXAM_LIST_DESC,
        parameters=[
            OpenApiParameter(name="search", type=str, description="Search title, description"),
            OpenApiParameter(
                name="status",
                type=str,
                enum=["OPEN", "CLOSED"],
                description="OPEN = visible in exam room; CLOSED = hidden.",
            ),
            OpenApiParameter(name="ordering", type=str),
        ],
        responses={200: ExamAssignmentSerializer(many=True), 401: RESP_401, 403: RESP_403},
    ),
    retrieve=extend_schema(
        tags=["Exam Assignments"],
        summary="Get exam assignment",
        description=EXAM_RETRIEVE_DESC,
        responses={200: ExamAssignmentSerializer, 401: RESP_401, 403: RESP_403, 404: RESP_404},
    ),
    create=extend_schema(
        tags=["Exam Assignments"],
        summary="Create exam assignment",
        description=EXAM_CREATE_DESC,
        request=ExamAssignmentSerializer,
        responses={201: ExamAssignmentSerializer, 400: RESP_400, 401: RESP_401, 403: RESP_403},
        examples=[
            OpenApiExample(
                "Create exam assignment",
                value={
                    "title": "JLPT N5 Mock Exam - Room A",
                    "description": "Scheduled for Saturday 9:00.",
                    "mock_test": "550e8400-e29b-41d4-a716-446655440000",
                    "status": "CLOSED",
                    "estimated_start_time": "2025-02-01T09:00:00Z",
                    "is_published": False,
                    "assigned_group_ids": ["660e8400-e29b-41d4-a716-446655440001"],
                },
                request_only=True,
            ),
        ],
    ),
    update=extend_schema(
        tags=["Exam Assignments"],
        summary="Full update exam assignment",
        description=EXAM_UPDATE_DESC,
        request=ExamAssignmentSerializer,
        responses={200: ExamAssignmentSerializer, 400: RESP_400, 401: RESP_401, 403: RESP_403, 404: RESP_404},
        examples=[
            OpenApiExample(
                "Full update exam assignment",
                value={
                    "title": "JLPT N5 Mock Exam - Room A (Updated)",
                    "description": "Scheduled for Saturday 10:00.",
                    "mock_test": "550e8400-e29b-41d4-a716-446655440000",
                    "status": "OPEN",
                    "estimated_start_time": "2025-02-01T10:00:00Z",
                    "is_published": False,
                    "assigned_group_ids": ["660e8400-e29b-41d4-a716-446655440001", "660e8400-e29b-41d4-a716-446655440002"],
                },
                request_only=True,
            ),
        ],
    ),
    partial_update=extend_schema(
        tags=["Exam Assignments"],
        summary="Partial update exam assignment",
        request=ExamAssignmentSerializer,
        responses={200: ExamAssignmentSerializer, 400: RESP_400, 401: RESP_401, 403: RESP_403, 404: RESP_404},
        examples=[
            OpenApiExample(
                "Partial update exam assignment",
                value={
                    "title": "JLPT N5 Mock Exam - Room A (Updated)",
                    "description": "Scheduled for Saturday 10:00.",
                    "mock_test": "550e8400-e29b-41d4-a716-446655440000",
                    "status": "OPEN",
                    "estimated_start_time": "2025-02-01T10:00:00Z",
                    "is_published": False,
                    "assigned_group_ids": ["660e8400-e29b-41d4-a716-446655440001", "660e8400-e29b-41d4-a716-446655440002"],
                },
                request_only=True,
            ),
        ],
    ),
    destroy=extend_schema(
        tags=["Exam Assignments"],
        summary="Delete exam assignment",
        description=EXAM_DESTROY_DESC,
        responses={204: OpenApiResponse(description="Deleted."), 401: RESP_401, 403: RESP_403, 404: RESP_404},
    ),
)

# -----------------------------------------------------------------------------
# HomeworkAssignment
# -----------------------------------------------------------------------------

HOMEWORK_LIST_DESC = """
List homework assignments. **Visibility:** CENTER_ADMIN all; TEACHER groups they teach;
STUDENT their groups OR their user ID in assigned_user_ids; GUEST only assigned_user_ids.
**Performance:** created_by from public schema (user_map). Results are distinct().
"""
HOMEWORK_RETRIEVE_DESC = """
Retrieve homework (detail). For each assigned MockTest/Quiz, the response includes
**Student's Current Status** (from attempts.Submission):
- **Not Started:** No submission for that resource.
- **In Progress:** Submission exists with status STARTED or SUBMITTED.
- **Completed:** Submission exists with status GRADED.
One batch query for submissions (zero N+1). Same visibility as list.
"""
HOMEWORK_CREATE_DESC = """
Create homework. CENTER_ADMIN or TEACHER. Only **PUBLISHED** MockTests and **ACTIVE**
Quizzes. **Deadline** must be in the future. **assigned_user_ids:** list of integers
(User IDs from public schema; must belong to current center).
"""
HOMEWORK_UPDATE_DESC = "Update homework. CENTER_ADMIN or teacher for assigned groups."
HOMEWORK_DESTROY_DESC = "Delete homework. CENTER_ADMIN or teacher for assigned groups."

# Example response for homework detail (student status)
HOMEWORK_DETAIL_RESPONSE_EXAMPLE = OpenApiExample(
    "Homework detail with student status",
    value={
        "id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
        "title": "Week 3 Homework",
        "description": "Complete N5 mock and quiz by Friday.",
        "deadline": "2025-02-07T23:59:59Z",
        "mock_tests": [
            {
                "id": "550e8400-e29b-41d4-a716-446655440000",
                "title": "JLPT N5 Mock",
                "level": "N5",
                "description": "",
                "status": "In Progress",
                "type": "mock_test",
            },
        ],
        "quizzes": [
            {
                "id": "660e8400-e29b-41d4-a716-446655440001",
                "title": "Vocabulary Quiz",
                "description": "Basic vocab",
                "status": "Completed",
                "type": "quiz",
            },
        ],
        "assigned_groups": [{"id": "770e8400-e29b-41d4-a716-446655440002", "name": "N5 Morning"}],
        "show_results_immediately": True,
        "created_at": "2025-01-15T10:00:00Z",
        "updated_at": "2025-01-15T10:00:00Z",
    },
    response_only=True,
    description="status per resource: Not Started | In Progress | Completed.",
)

homework_assignment_viewset_schema = extend_schema_view(
    list=extend_schema(
        tags=["Homework Assignments"],
        summary="List homework assignments",
        description=HOMEWORK_LIST_DESC,
        parameters=[
            OpenApiParameter(name="search", type=str),
            OpenApiParameter(name="ordering", type=str, description="e.g. -deadline, created_at"),
        ],
        responses={200: HomeworkAssignmentSerializer(many=True), 401: RESP_401, 403: RESP_403},
    ),
    retrieve=extend_schema(
        tags=["Homework Assignments"],
        summary="Get homework (detailed)",
        description=HOMEWORK_RETRIEVE_DESC,
        responses={
            200: HomeworkDetailSerializer,
            401: RESP_401,
            403: RESP_403,
            404: RESP_404,
        },
        examples=[HOMEWORK_DETAIL_RESPONSE_EXAMPLE],
    ),
    create=extend_schema(
        tags=["Homework Assignments"],
        summary="Create homework assignment",
        description=HOMEWORK_CREATE_DESC,
        request=HomeworkAssignmentSerializer,
        responses={201: HomeworkAssignmentSerializer, 400: RESP_400, 401: RESP_401, 403: RESP_403},
        examples=[
            OpenApiExample(
                "Homework with MockTest and Quiz (assigned_user_ids: list of User IDs)",
                value={
                    "title": "Week 3 Homework",
                    "description": "Complete N5 mock and quiz by Friday.",
                    "deadline": "2025-02-07T23:59:59Z",
                    "mock_test_ids": ["550e8400-e29b-41d4-a716-446655440000"],
                    "quiz_ids": ["660e8400-e29b-41d4-a716-446655440001"],
                    "assigned_group_ids": ["770e8400-e29b-41d4-a716-446655440002"],
                    "assigned_user_ids": [101, 102],
                    "show_results_immediately": True,
                },
                request_only=True,
                description="assigned_user_ids: list of integers (User IDs from public schema, this center).",
            ),
            OpenApiExample(
                "Homework with both MockTest and Quiz only (no users)",
                value={
                    "title": "Practice Set",
                    "description": "One mock test and one quiz.",
                    "deadline": "2025-03-01T23:59:59Z",
                    "mock_test_ids": ["550e8400-e29b-41d4-a716-446655440000"],
                    "quiz_ids": ["660e8400-e29b-41d4-a716-446655440001"],
                    "assigned_group_ids": ["770e8400-e29b-41d4-a716-446655440002"],
                    "assigned_user_ids": [],
                    "show_results_immediately": False,
                },
                request_only=True,
            ),
        ],
    ),
    update=extend_schema(
        tags=["Homework Assignments"],
        summary="Full update homework",
        description=HOMEWORK_UPDATE_DESC,
        request=HomeworkAssignmentSerializer,
        responses={200: HomeworkAssignmentSerializer, 400: RESP_400, 401: RESP_401, 403: RESP_403, 404: RESP_404},
        examples=[
            OpenApiExample(
                "Full update homework",
                value={
                    "title": "Week 3 Homework (Updated)",
                    "description": "Complete N5 mock and quiz by Friday.",
                    "deadline": "2025-02-14T23:59:59Z",
                    "mock_test_ids": ["550e8400-e29b-41d4-a716-446655440000"],
                    "quiz_ids": ["660e8400-e29b-41d4-a716-446655440001"],
                    "assigned_group_ids": ["770e8400-e29b-41d4-a716-446655440002"],
                    "assigned_user_ids": [101, 102],
                    "show_results_immediately": True,
                },
                request_only=True,
            ),
        ],
    ),
    partial_update=extend_schema(
        tags=["Homework Assignments"],
        summary="Partial update homework",
        request=HomeworkAssignmentSerializer,
        responses={200: HomeworkAssignmentSerializer, 400: RESP_400, 401: RESP_401, 403: RESP_403, 404: RESP_404},
        examples=[
            OpenApiExample(
                "Partial update homework",
                value={
                    "title": "Week 3 Homework (Updated)",
                    "description": "Complete N5 mock and quiz by Friday.",
                    "deadline": "2025-02-14T23:59:59Z",
                    "mock_test_ids": ["550e8400-e29b-41d4-a716-446655440000"],
                    "quiz_ids": ["660e8400-e29b-41d4-a716-446655440001"],
                    "assigned_group_ids": ["770e8400-e29b-41d4-a716-446655440002"],
                    "assigned_user_ids": [101, 102],
                    "show_results_immediately": True,
                },
                request_only=True,
            ),
        ],
    ),
    destroy=extend_schema(
        tags=["Homework Assignments"],
        summary="Delete homework",
        description=HOMEWORK_DESTROY_DESC,
        responses={204: OpenApiResponse(description="Deleted."), 401: RESP_401, 403: RESP_403, 404: RESP_404},
    ),
)
