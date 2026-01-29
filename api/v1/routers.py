#api/v1/routers.py
from rest_framework.routers import DefaultRouter

from apps.centers.views import (
    OwnerCenterViewSet,
    OwnerCenterAdminViewSet,
    CenterAdminCenterViewSet,
    OwnerContactRequestViewSet,
)
from apps.groups.views import GroupViewSet, GroupMembershipViewSet
from apps.materials.views import MaterialViewSet
from apps.mock_tests.views import (
    MockTestViewSet,
    TestSectionViewSet,
    QuestionGroupViewSet,
    QuestionViewSet,
    QuizViewSet,
    QuizQuestionViewSet,
)
from apps.assignments.views import ExamAssignmentViewSet, HomeworkAssignmentViewSet
from apps.attempts.views import SubmissionViewSet
from apps.notifications.views import NotificationViewSet


api_router = DefaultRouter()

# Centers / Owner / Admin management
api_router.register(
    r"owner-centers",
    OwnerCenterViewSet,
    basename="owner-centers",
)
api_router.register(
    r"owner-center-admins",
    OwnerCenterAdminViewSet,
    basename="owner-center-admins",
)
api_router.register(
    r"center-admin-centers",
    CenterAdminCenterViewSet,
    basename="center-admin-centers",
)
api_router.register(
    r"owner-contact-requests",
    OwnerContactRequestViewSet,
    basename="owner-contact-requests",
)

# Groups
api_router.register(
    r"groups",
    GroupViewSet,
    basename="groups",
)
api_router.register(
    r"group-memberships",
    GroupMembershipViewSet,
    basename="group-memberships",
)

# Materials
api_router.register(
    r"materials",
    MaterialViewSet,
    basename="materials",
)

# Mock tests & quizzes
api_router.register(
    r"mock-tests",
    MockTestViewSet,
    basename="mock-tests",
)
api_router.register(
    r"test-sections",
    TestSectionViewSet,
    basename="test-sections",
)
api_router.register(
    r"question-groups",
    QuestionGroupViewSet,
    basename="question-groups",
)
api_router.register(
    r"questions",
    QuestionViewSet,
    basename="questions",
)
api_router.register(
    r"quizzes",
    QuizViewSet,
    basename="quizzes",
)
api_router.register(
    r"quiz-questions",
    QuizQuestionViewSet,
    basename="quiz-questions",
)

# Assignments
api_router.register(
    r"exam-assignments",
    ExamAssignmentViewSet,
    basename="exam-assignments",
)
api_router.register(
    r"homework-assignments",
    HomeworkAssignmentViewSet,
    basename="homework-assignments",
)

# Attempts / Submissions
api_router.register(
    r"submissions",
    SubmissionViewSet,
    basename="submissions",
)

# Notifications
api_router.register(
    r"notifications",
    NotificationViewSet,
    basename="notifications",
)

