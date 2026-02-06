"""
OpenAPI / Swagger documentation for the analytics app (drf-spectacular).

Role-based dashboards with distinct tags and rich JSON examples for frontend charts/tables.
Performance: Count/Avg, user_map (no N+1), select_related/prefetch where appropriate.

**Multi-tenant aggregation:**
- **Owner:** PUBLIC schema only (Center, User, ContactRequest). No tenant tables.
- **Center Admin:** User counts via with_public_schema; Group/ExamAssignment in tenant.
- **Teacher:** Distinct students across teacher's groups; pending = SUBMITTED; user_map for names.
- **Student:** Upcoming = assigned_groups OR assigned_user_ids, exclude homeworks with GRADED submission; skill_performance from Submission.results.

**Permissions:** 401 Unauthorized if not authenticated. 403 Forbidden if role does not match (e.g. student calling Owner dashboard).
"""
from drf_spectacular.utils import (
    OpenApiExample,
    OpenApiResponse,
    extend_schema,
)

from .serializers import (
    OwnerAnalyticsSerializer,
    CenterAdminAnalyticsSerializer,
    TeacherAnalyticsSerializer,
    StudentAnalyticsSerializer,
)

RESP_401 = OpenApiResponse(description="Authentication required.")
RESP_403_OWNER = OpenApiResponse(description="Only platform owners can access this dashboard.")
RESP_403_CENTER_ADMIN = OpenApiResponse(description="Only center admins can access this dashboard.")
RESP_403_TEACHER = OpenApiResponse(description="Only teachers can access this dashboard.")
RESP_403_STUDENT = OpenApiResponse(description="Only students can access this dashboard.")

# ---- Owner ----
OWNER_DESCRIPTION = """
**Owner dashboard.** Runs strictly in **PUBLIC** schema. No tenant tables.
- **total_centers:** All centers.
- **total_users:** All users (all roles).
- **active_centers_count:** Centers with status ACTIVE and non-empty schema.
- **recent_contact_requests:** Last 10 platform-wide contact requests.
- **growth_centers_pct:** Optional (null); reserved for time-series.
"""
OWNER_RESPONSE_EXAMPLE = {
    "total_centers": 12,
    "total_users": 450,
    "active_centers_count": 10,
    "growth_centers_pct": None,
    "recent_contact_requests": [
        {
            "id": "550e8400-e29b-41d4-a716-446655440000",
            "center_name": "JLPT Academy",
            "full_name": "Jane Doe",
            "phone_number": "+998901234567",
            "status": "PENDING",
            "created_at": "2025-01-29T10:00:00Z",
        },
    ],
}

owner_analytics_schema = extend_schema(
    tags=["Analytics – Owner"],
    summary="Owner dashboard",
    description=OWNER_DESCRIPTION,
    responses={
        200: OwnerAnalyticsSerializer,
        401: RESP_401,
        403: RESP_403_OWNER,
    },
    examples=[
        OpenApiExample(
            "Owner dashboard response",
            value=OWNER_RESPONSE_EXAMPLE,
            response_only=True,
        ),
    ],
)

# ---- Center Admin ----
CENTER_ADMIN_DESCRIPTION = """
**Center Admin dashboard.** User counts from **PUBLIC** schema via with_public_schema (current center).
Group and ExamAssignment counts from **current TENANT** schema.
- **total_students / total_teachers:** Public User filtered by center_id.
- **total_groups:** Tenant Group count.
- **active_exams_count:** Tenant ExamAssignment with status OPEN.
- **growth_students_pct:** Optional (null); reserved for time-series.
"""
CENTER_ADMIN_RESPONSE_EXAMPLE = {
    "total_students": 120,
    "total_teachers": 8,
    "total_groups": 15,
    "active_exams_count": 2,
    "growth_students_pct": None,
}

center_admin_analytics_schema = extend_schema(
    tags=["Analytics – Center Admin"],
    summary="Center Admin dashboard",
    description=CENTER_ADMIN_DESCRIPTION,
    responses={
        200: CenterAdminAnalyticsSerializer,
        401: RESP_401,
        403: RESP_403_CENTER_ADMIN,
    },
    examples=[
        OpenApiExample(
            "Center Admin dashboard response",
            value=CENTER_ADMIN_RESPONSE_EXAMPLE,
            response_only=True,
        ),
    ],
)

# ---- Teacher ----
TEACHER_DESCRIPTION = """
**Teacher dashboard.** Tenant + Public:
- **my_groups_count:** Groups where the user is TEACHER.
- **total_students:** Distinct students across those groups (no double-count).
- **pending_grading_count:** Submissions with status **SUBMITTED** (awaiting grading).
- **recent_submissions:** Last 10 submissions with student names (from public schema via **user_map**, no N+1).
- **submission_trend_count:** Optional (null); reserved for trend metrics.
"""
TEACHER_RESPONSE_EXAMPLE = {
    "my_groups_count": 4,
    "total_students": 45,
    "pending_grading_count": 3,
    "submission_trend_count": None,
    "recent_submissions": [
        {
            "id": "660e8400-e29b-41d4-a716-446655440001",
            "student_name": "John Doe",
            "assignment_title": "JLPT N5 Mock Exam",
            "score": 95.5,
            "submitted_at": "2025-01-29T11:30:00Z",
        },
        {
            "id": "770e8400-e29b-41d4-a716-446655440002",
            "student_name": "Jane Smith",
            "assignment_title": "Week 3 Homework",
            "score": None,
            "submitted_at": "2025-01-29T10:00:00Z",
        },
    ],
}

teacher_analytics_schema = extend_schema(
    tags=["Analytics – Teacher"],
    summary="Teacher dashboard",
    description=TEACHER_DESCRIPTION,
    responses={
        200: TeacherAnalyticsSerializer,
        401: RESP_401,
        403: RESP_403_TEACHER,
    },
    examples=[
        OpenApiExample(
            "Teacher dashboard response",
            value=TEACHER_RESPONSE_EXAMPLE,
            response_only=True,
        ),
    ],
)

# ---- Student ----
STUDENT_DESCRIPTION = """
**Student dashboard.** Tenant-level:
- **average_score:** Mean score across all GRADED submissions.
- **completed_exams_count:** Count of GRADED submissions (exams + homework).
- **upcoming_deadlines:** Homeworks with deadline in future where user is in **assigned_groups** OR **assigned_user_ids**, excluding homeworks for which the user already has a **GRADED** submission.
- **recent_results:** Last 10 graded submissions with assignment title and score.
- **skill_performance:** Derived from **Submission.results** (JLPT section_results: Vocabulary, Reading, Listening; or Language & Reading + Listening for N4/N5; or Quiz percentage). Exact structure for charts: `[{"skill_name": "Listening", "average_score": 45.5}, ...]`.
- **skill_performance (standardized):** Always includes ordered entries for Vocabulary, Reading, Listening, Language & Reading, and Quiz (missing values = 0.0), plus any extra sections.
- **submission_trend_count:** Optional (null); reserved for trend metrics.
"""
STUDENT_RESPONSE_EXAMPLE = {
    "average_score": 78.5,
    "completed_exams_count": 5,
    "submission_trend_count": None,
    "upcoming_deadlines": [
        {
            "id": "770e8400-e29b-41d4-a716-446655440002",
            "title": "Week 4 Homework",
            "deadline": "2025-02-05T23:59:00Z",
            "type": "Homework",
        },
    ],
    "recent_results": [
        {
            "id": "880e8400-e29b-41d4-a716-446655440003",
            "assignment_title": "JLPT N5 Mock",
            "score": 82.0,
            "status": "GRADED",
            "completed_at": "2025-01-28T14:00:00Z",
        },
    ],
    "skill_performance": [
        {"skill_name": "Vocabulary", "average_score": 28.0},
        {"skill_name": "Reading", "average_score": 32.5},
        {"skill_name": "Listening", "average_score": 18.0},
    ],
}

student_analytics_schema = extend_schema(
    tags=["Analytics – Student"],
    summary="Student dashboard",
    description=STUDENT_DESCRIPTION,
    responses={
        200: StudentAnalyticsSerializer,
        401: RESP_401,
        403: RESP_403_STUDENT,
    },
    examples=[
        OpenApiExample(
            "Student dashboard response (with skill_performance for charts)",
            value=STUDENT_RESPONSE_EXAMPLE,
            response_only=True,
        ),
    ],
)
