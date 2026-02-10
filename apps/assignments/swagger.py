"""
OpenAPI / Swagger documentation for the assignments app (drf-spectacular).

Assignments bridge educational resources and students: **ExamAssignment** (one MockTest
per exam room with OPEN/CLOSED visibility control) and **HomeworkAssignment** (multiple
MockTests/Quizzes, assigned to groups and/or individual users with deadlines).

================================================================================
ROLE-BASED ACCESS CONTROL (RBAC) MATRIX
================================================================================

**Visibility (get_queryset):**

| Role          | ExamAssignment         | HomeworkAssignment                      |
|---------------|------------------------|-----------------------------------------|
| CENTER_ADMIN  | All assignments        | All assignments                         |
| TEACHER       | Groups they teach ONLY | Groups they teach ONLY                  |
| STUDENT       | Assigned groups only   | Assigned groups OR user_id in assigned_user_ids |
| GUEST         | NONE                   | User ID in assigned_user_ids only       |

**Create/Update/Delete Permissions:**
- **CENTER_ADMIN:** Can manage any assignment, any groups
- **TEACHER:** Can manage assignments for groups where they have TEACHER role
  (enforced via GroupMembership lookup)
- **STUDENT & GUEST:** Read-only (403 on POST/PUT/PATCH/DELETE)

**Teacher Boundary Enforcement:** TEACHER attempting to assign groups they do NOT teach
returns **400 Bad Request** with message: "Teachers can only assign groups they teach."

================================================================================
EXAM ASSIGNMENT: OPEN vs CLOSED STATUS
================================================================================

**CLOSED (default):**
- Assignment exists in database but is **invisible in exam room** to students
- Teacher use case: Prepare exam room before opening; test infrastructure
- Students cannot see or access the assignment

**OPEN:**
- Assignment is **visible in exam room** to students in assigned groups
- Teacher use case: Ready for live exam; students can see and attempt
- Students in assigned groups can view and interact with assignment

**Workflow Example:**
1. Create ExamAssignment with status=CLOSED
2. Teacher previews test, verifies content
3. Update to status=OPEN when ready
4. Students see assignment in exam room and can attempt
5. Update to status=CLOSED after exam time (prevents late attempts)

================================================================================
HOMEWORK ASSIGNMENT: DEADLINE & STUDENT STATUS
================================================================================

**Deadline Validation:**
- Must be a future timestamp (current_time < deadline)
- 400 Bad Request if deadline <= current time ("Deadline must be in the future.")
- Supported time formats: ISO 8601 with timezone (e.g., "2025-02-07T23:59:59Z")

**Student's Current Status (from Submission records):**

| Status       | Condition                                    |
|--------------|----------------------------------------------|
| Not Started  | No Submission record exists for this resource |
| In Progress  | Submission exists with status STARTED or SUBMITTED |
| Completed    | Submission exists with status GRADED        |

**Calculation Method:**
- One batch query per homework retrieve: `Submission.objects.filter(homework=hw, user=current_user)`
- Returns {"mock_test": {id: status}, "quiz": {id: status}}
- Zero N+1 queries; all statuses loaded in single query
- Each MockTest/Quiz in response includes its status for current student

================================================================================
ASSIGNED_USER_IDS: CROSS-SCHEMA USER VALIDATION
================================================================================

**Field Format:** ArrayField of integers (User IDs from public schema)

**Validation Process:**
1. **Type Check:** All values must be integers
2. **Public Schema Lookup:** Verify each ID exists in User table (public schema)
   - Query: `User.objects.filter(id__in=user_ids)`
   - Error: "The following user IDs do not exist: [99, 101]" (if missing)
3. **Tenant Boundary Check:** Verify each user belongs to current center
   - Query: `User.objects.filter(id__in=user_ids, center_id=tenant_center_id)`
   - Error: "The following user IDs do not belong to this center: [15, 22]"
   - Prevents accidental assignment of users from wrong center

**Use Cases:**
- STUDENT: Assigned individually for personalized homework
- GUEST: Assigned individually for guest access (no group membership required)
- TEACHER: NOT assignable (400 error if attempted)

**Security:** Cross-schema validation ensures strict tenant isolation; users cannot
assign individuals from other centers to their assignments.

================================================================================
RESOURCE CONSTRAINTS
================================================================================

**MockTests:**
- Must be PUBLISHED status (not DRAFT)
- Cannot be deleted (deleted_at IS NOT NULL check)
- Error: "MockTest '{title}' is not PUBLISHED." or "MockTest is deleted."

**Quizzes:**
- Must be ACTIVE (is_active=True)
- Cannot be deleted
- Error: "Quiz '{title}' is not active." or "Quiz is deleted."

**At Least One Resource:**
- ExamAssignment: Requires 1 MockTest (foreign key, required)
- HomeworkAssignment: Requires at least 1 MockTest OR 1 Quiz
- Error: "At least one MockTest or Quiz must be assigned."

**At Least One Assignment Target:**
- ExamAssignment: Requires at least 1 group in assigned_groups
- HomeworkAssignment: Requires at least 1 group OR 1 user
- Error: "At least one group or one user must be assigned."

================================================================================
PERFORMANCE OPTIMIZATIONS
================================================================================

**ExamAssignment List:** Batch-fetches created_by (Public User) via user_map
- Collects all created_by_id values from paginated assignments
- Single query in public schema: `User.objects.filter(id__in=user_ids)`
- Passes user_map to serializer context
- Result: 20 assignments = 1 public schema query (not 20)

**HomeworkAssignment Retrieve:** Batch-fetches submission statuses
- Single query for all submissions: `Submission.objects.filter(homework=hw, user=user)`
- Maps submission status per MockTest/Quiz ID
- Result: 10 resources = 1 submission query (not 10)

**Queryset Optimization:**
- `select_related('mock_test')` for ExamAssignment
- `prefetch_related('assigned_groups', 'mock_tests', 'quizzes')` for HomeworkAssignment
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
        "Validation error: resource not PUBLISHED/ACTIVE, past deadline, teacher "
        "assigning non-taught groups, invalid resource IDs, or assigned_user_ids "
        "not in current center."
    ),
    examples=[
        OpenApiExample(
            "Past deadline",
            value={"deadline": "Deadline must be in the future."},
            response_only=True,
        ),
        OpenApiExample(
            "Resource not published",
            value={"mock_test_ids": "MockTest 'Draft Exam' is not PUBLISHED."},
            response_only=True,
            description="Cannot assign DRAFT or DELETED MockTests."
        ),
        OpenApiExample(
            "Teacher assigning non-taught group",
            value={"assigned_group_ids": "Teachers can only assign groups they teach."},
            response_only=True,
            description="TEACHER role enforced: must have TEACHER role in target groups."
        ),
        OpenApiExample(
            "User IDs not in center",
            value={"assigned_user_ids": "The following user IDs do not belong to this center: [99, 101]."},
            response_only=True,
            description="Cross-schema validation: User.center_id must match current center."
        ),
        OpenApiExample(
            "User IDs don't exist",
            value={"assigned_user_ids": "The following user IDs do not exist: [999]."},
            response_only=True,
            description="Public schema lookup: User must exist in User table."
        ),
    ],
)
RESP_401 = OpenApiResponse(description="Authentication required.")
RESP_403 = OpenApiResponse(
    description="Permission denied: students/guests cannot create/update/delete; teachers managing non-taught groups.",
    examples=[
        OpenApiExample(
            "Student attempting POST/PUT/PATCH",
            value={"detail": "You do not have permission to perform this action."},
            response_only=True,
            description="STUDENT role lacks POST/PUT/PATCH/DELETE permissions."
        ),
        OpenApiExample(
            "Teacher retrieving hidden assignment",
            value={"detail": "Not found."},
            response_only=True,
            description="TEACHER can only retrieve assignments for groups they teach. Returns 404 if not in taught groups."
        ),
    ],
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
    "Create exam assignment. CENTER_ADMIN or TEACHER. MockTest must be PUBLISHED. "
    "**Status:** CLOSED = invisible in exam room (preparation); OPEN = visible to assigned groups. "
    "**Teacher Boundary:** TEACHER can only assign groups where they have TEACHER role (GroupMembership); "
    "returns 400 if attempting to assign non-taught groups."
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
Retrieve homework (detailed). For each assigned MockTest/Quiz, response includes
**Student's Current Status** (calculated from Submission records, one batch query):
- **Not Started:** No Submission exists for that resource
- **In Progress:** Submission.status in (STARTED, SUBMITTED)
- **Completed:** Submission.status = GRADED

**Performance:** Single batch query for all submissions: `Submission.objects.filter(homework=hw, user=current_user)`.
Zero N+1 queries; all statuses loaded at once. Same visibility as list (role-based filtering).
"""
HOMEWORK_CREATE_DESC = """
Create homework. CENTER_ADMIN or TEACHER. Only **PUBLISHED** MockTests and **ACTIVE**
Quizzes. **Deadline** must be in the future. **assigned_user_ids:** list of integers
(User IDs from public schema; validated: (1) exist in User table, (2) belong to current center).
**Teacher Boundary:** TEACHER can only assign groups where they teach.
"""
HOMEWORK_UPDATE_DESC = "Update homework. CENTER_ADMIN or teacher for assigned groups."
HOMEWORK_DESTROY_DESC = "Delete homework. CENTER_ADMIN or teacher for assigned groups."

# Example response for homework detail (student status)
HOMEWORK_DETAIL_RESPONSE_EXAMPLE = OpenApiExample(
    "Homework detail with student status (mixed states)",
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
        "created_by": {
            "id": 42,
            "email": "teacher@example.com",
            "full_name": "John Smith",
            "role": "TEACHER"
        },
        "created_at": "2025-01-15T10:00:00Z",
        "updated_at": "2025-01-15T10:00:00Z",
    },
    response_only=True,
    description="Status values per resource: 'Not Started' | 'In Progress' | 'Completed' (from Submission.status mapping).",
)

HOMEWORK_DETAIL_NOT_STARTED_EXAMPLE = OpenApiExample(
    "Homework detail - student not started any resources",
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
                "status": "Not Started",
                "type": "mock_test",
            },
        ],
        "quizzes": [
            {
                "id": "660e8400-e29b-41d4-a716-446655440001",
                "title": "Vocabulary Quiz",
                "description": "Basic vocab",
                "status": "Not Started",
                "type": "quiz",
            },
        ],
        "assigned_groups": [{"id": "770e8400-e29b-41d4-a716-446655440002", "name": "N5 Morning"}],
        "show_results_immediately": True,
        "created_at": "2025-01-15T10:00:00Z",
        "updated_at": "2025-01-15T10:00:00Z",
    },
    response_only=True,
    description="No Submission records exist for this user; all resources show 'Not Started'.",
)

HOMEWORK_DETAIL_COMPLETED_EXAMPLE = OpenApiExample(
    "Homework detail - student completed all resources",
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
                "status": "Completed",
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
        "created_by": {
            "id": 42,
            "email": "teacher@example.com",
            "full_name": "John Smith",
            "role": "TEACHER"
        },
        "created_at": "2025-01-15T10:00:00Z",
        "updated_at": "2025-01-15T10:00:00Z",
    },
    response_only=True,
    description="All Submission records have status=GRADED; all resources show 'Completed'.",
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
        examples=[
            HOMEWORK_DETAIL_NOT_STARTED_EXAMPLE,
            HOMEWORK_DETAIL_RESPONSE_EXAMPLE,
            HOMEWORK_DETAIL_COMPLETED_EXAMPLE,
        ],
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
