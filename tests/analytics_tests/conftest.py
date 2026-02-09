# tests/analytics_tests/conftest.py
"""
Fixtures for Analytics app QA automation.
Multi-tenant setup: Centers A and B with different schemas.
Complex data: Users, submissions with JLPT JSON results, contact requests.
"""
import pytest
from decimal import Decimal
from datetime import timedelta
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.utils import timezone
from rest_framework_simplejwt.tokens import RefreshToken

from apps.centers.models import Center, ContactRequest
from apps.core.tenant_utils import schema_context, with_public_schema
from apps.groups.models import Group, GroupMembership
from apps.mock_tests.models import MockTest, TestSection, Question
from apps.assignments.models import ExamAssignment, HomeworkAssignment
from apps.attempts.models import Submission

User = get_user_model()


@pytest.fixture(scope="session", autouse=True)
def disable_center_schema_creation_for_tests():
    """Disable Center signals during tests to avoid tenant migration side effects."""
    from django.db.models.signals import post_save
    from apps.centers.signals import (
        run_migrations_for_new_center,
        create_free_subscription_for_new_center,
    )
    post_save.disconnect(run_migrations_for_new_center, sender=Center)
    post_save.disconnect(create_free_subscription_for_new_center, sender=Center)


def _get_error_detail(response, key):
    """Return error detail for a field, supporting wrapped error responses."""
    data = response.data
    if isinstance(data, dict) and "error" in data and isinstance(data["error"], dict):
        data = data["error"]
    if isinstance(data, dict):
        return data.get(key)
    return None


@pytest.fixture(autouse=True)
def clear_cache():
    """Clear cache before each test."""
    cache.clear()
    yield
    cache.clear()


# ============================================================================
# CENTER FIXTURES
# ============================================================================

@pytest.fixture
def center_a(db):
    """Center A in public schema."""
    return Center.objects.create(
        name="Center A",
        schema_name="center_a_schema",
        status=Center.Status.ACTIVE,
        is_ready=True,
    )


@pytest.fixture
def center_b(db):
    """Center B in public schema (different schema)."""
    return Center.objects.create(
        name="Center B",
        schema_name="center_b_schema",
        status=Center.Status.ACTIVE,
        is_ready=True,
    )


# ============================================================================
# USER FIXTURES (PUBLIC SCHEMA)
# ============================================================================

@pytest.fixture
def owner_user(db):
    """Platform owner."""
    return User.objects.create_user(
        email="owner@platform.test",
        password="Pass12345!",
        role=User.Role.OWNER,
        is_active=True,
        is_approved=True,
    )


@pytest.fixture
def center_admin_a(db, center_a):
    """Center Admin for Center A."""
    return User.objects.create_user(
        email="admin_a@center.test",
        password="Pass12345!",
        role=User.Role.CENTERADMIN,
        center=center_a,
        is_active=True,
        is_approved=True,
    )


@pytest.fixture
def center_admin_b(db, center_b):
    """Center Admin for Center B."""
    return User.objects.create_user(
        email="admin_b@center.test",
        password="Pass12345!",
        role=User.Role.CENTERADMIN,
        center=center_b,
        is_active=True,
        is_approved=True,
    )


@pytest.fixture
def teacher_a(db, center_a):
    """Teacher in Center A."""
    return User.objects.create_user(
        email="teacher_a@center.test",
        password="Pass12345!",
        role=User.Role.TEACHER,
        center=center_a,
        is_active=True,
        is_approved=True,
    )


@pytest.fixture
def teacher_b(db, center_b):
    """Teacher in Center B."""
    return User.objects.create_user(
        email="teacher_b@center.test",
        password="Pass12345!",
        role=User.Role.TEACHER,
        center=center_b,
        is_active=True,
        is_approved=True,
    )


@pytest.fixture
def student_a1(db, center_a):
    """Student 1 in Center A."""
    return User.objects.create_user(
        email="student_a1@center.test",
        password="Pass12345!",
        role=User.Role.STUDENT,
        center=center_a,
        is_active=True,
        is_approved=True,
    )


@pytest.fixture
def student_a2(db, center_a):
    """Student 2 in Center A."""
    return User.objects.create_user(
        email="student_a2@center.test",
        password="Pass12345!",
        role=User.Role.STUDENT,
        center=center_a,
        is_active=True,
        is_approved=True,
    )


@pytest.fixture
def student_b1(db, center_b):
    """Student 1 in Center B."""
    return User.objects.create_user(
        email="student_b1@center.test",
        password="Pass12345!",
        role=User.Role.STUDENT,
        center=center_b,
        is_active=True,
        is_approved=True,
    )


# ============================================================================
# CONTACT REQUEST FIXTURES (PUBLIC SCHEMA)
# ============================================================================

@pytest.fixture
def contact_requests(db, center_a):
    """5 contact requests for Center A."""
    requests = []
    for i in range(5):
        cr = ContactRequest.objects.create(
            center_name=center_a.name,
            full_name=f"Visitor {i+1}",
            phone_number=f"555-000{i}",
            message=f"Request from visitor {i+1}",
            status="PENDING",  # String value, not enum
        )
        requests.append(cr)
    return requests


# ============================================================================
# MOCK TEST FIXTURES (TENANT SCHEMA - Center A)
# ============================================================================

@pytest.fixture
def mock_test_n5(db, teacher_a, center_a):
    """N5 level MockTest in Center A schema."""
    with schema_context(center_a.schema_name):
        mock_test = MockTest.objects.create(
            title="N5 Practice Test",
            level=MockTest.Level.N5,
            status=MockTest.Status.PUBLISHED,
            created_by_id=teacher_a.id,
        )
        # Vocabulary section
        vocab_section = TestSection.objects.create(
            mock_test=mock_test,
            name="Vocabulary",
            section_type=TestSection.SectionType.VOCAB,
            duration=20,
            order=1,
            total_score=60,
        )
        # Reading section
        reading_section = TestSection.objects.create(
            mock_test=mock_test,
            name="Reading",
            section_type=TestSection.SectionType.GRAMMAR_READING,
            duration=40,
            order=2,
            total_score=60,
        )
        # Listening section
        listening_section = TestSection.objects.create(
            mock_test=mock_test,
            name="Listening",
            section_type=TestSection.SectionType.LISTENING,
            duration=30,
            order=3,
            total_score=60,
        )
        return mock_test


@pytest.fixture
def group_a(db, center_a):
    """Group in Center A schema."""
    with schema_context(center_a.schema_name):
        return Group.objects.create(name="Group A")


@pytest.fixture
def exam_assignment_a(db, teacher_a, group_a, mock_test_n5, center_a):
    """Exam assignment in Center A schema."""
    with schema_context(center_a.schema_name):
        exam = ExamAssignment.objects.create(
            title="N5 Exam",
            description="Test N5 level",
            mock_test=mock_test_n5,
            status=ExamAssignment.RoomStatus.CLOSED,
            created_by_id=teacher_a.id,
        )
        exam.assigned_groups.set([group_a.id])
        return exam


@pytest.fixture
def homework_assignment_a(db, teacher_a, group_a, mock_test_n5, center_a):
    """Homework assignment in Center A schema."""
    with schema_context(center_a.schema_name):
        hw = HomeworkAssignment.objects.create(
            title="N5 Homework",
            description="Weekly homework",
            deadline=timezone.now() + timedelta(days=7),
            created_by_id=teacher_a.id,
            show_results_immediately=True,
        )
        hw.assigned_groups.set([group_a.id])
        hw.mock_tests.set([mock_test_n5.id])
        return hw


@pytest.fixture
def group_membership_student_a1(db, student_a1, group_a, center_a):
    """Student A1 membership in Group A."""
    with schema_context(center_a.schema_name):
        return GroupMembership.objects.create(
            group=group_a,
            user_id=student_a1.id,
            role_in_group=GroupMembership.ROLE_STUDENT,
        )


@pytest.fixture
def group_membership_student_a2(db, student_a2, group_a, center_a):
    """Student A2 membership in Group A."""
    with schema_context(center_a.schema_name):
        return GroupMembership.objects.create(
            group=group_a,
            user_id=student_a2.id,
            role_in_group=GroupMembership.ROLE_STUDENT,
        )


@pytest.fixture
def group_membership_teacher_a(db, teacher_a, group_a, center_a):
    """Teacher A membership in Group A."""
    with schema_context(center_a.schema_name):
        return GroupMembership.objects.create(
            group=group_a,
            user_id=teacher_a.id,
            role_in_group=GroupMembership.ROLE_TEACHER,
        )


# ============================================================================
# SUBMISSION FIXTURES (TENANT SCHEMA - Center A)
# ============================================================================

def _create_jlpt_results(vocab_score=50.0, reading_score=45.0, listening_score=40.0):
    """Helper to create realistic JLPT results JSON."""
    return {
        "resource_type": "mock_test",
        "jlpt_result": {
            "level": "N5",
            "total_score": vocab_score + reading_score + listening_score,
            "pass_mark": 90,
            "passed": (vocab_score + reading_score + listening_score) >= 90,
            "total_passed": True,
            "section_results": {
                "language_knowledge": {
                    "score": vocab_score,
                    "min_required": 19,
                    "passed": vocab_score >= 19,
                },
                "reading": {
                    "score": reading_score,
                    "min_required": 19,
                    "passed": reading_score >= 19,
                },
                "listening": {
                    "score": listening_score,
                    "min_required": 19,
                    "passed": listening_score >= 19,
                },
                "language_reading_combined": {
                    "score": vocab_score + reading_score,
                    "min_required": 38,
                    "passed": (vocab_score + reading_score) >= 38,
                },
            },
        },
    }


@pytest.fixture
def submission_student_a1_1(db, student_a1, exam_assignment_a, center_a):
    """Student A1's first graded submission (60 + 50 + 40 = 150)."""
    with schema_context(center_a.schema_name):
        return Submission.objects.create(
            user_id=student_a1.id,
            exam_assignment=exam_assignment_a,
            status=Submission.Status.GRADED,
            score=Decimal("150.00"),
            results=_create_jlpt_results(vocab_score=60.0, reading_score=50.0, listening_score=40.0),
            completed_at=timezone.now() - timedelta(days=5),
        )


@pytest.fixture
def submission_student_a1_2(db, student_a1, exam_assignment_a, center_a):
    """Student A1's second graded submission (55 + 48 + 42 = 145)."""
    with schema_context(center_a.schema_name):
        return Submission.objects.create(
            user_id=student_a1.id,
            exam_assignment=exam_assignment_a,
            status=Submission.Status.GRADED,
            score=Decimal("145.00"),
            results=_create_jlpt_results(vocab_score=55.0, reading_score=48.0, listening_score=42.0),
            completed_at=timezone.now() - timedelta(days=3),
        )


@pytest.fixture
def submission_student_a1_3(db, student_a1, exam_assignment_a, center_a):
    """Student A1's third graded submission (58 + 52 + 45 = 155)."""
    with schema_context(center_a.schema_name):
        return Submission.objects.create(
            user_id=student_a1.id,
            exam_assignment=exam_assignment_a,
            status=Submission.Status.GRADED,
            score=Decimal("155.00"),
            results=_create_jlpt_results(vocab_score=58.0, reading_score=52.0, listening_score=45.0),
            completed_at=timezone.now() - timedelta(days=1),
        )


@pytest.fixture
def submission_student_a1_pending_hw(db, student_a1, homework_assignment_a, center_a):
    """Student A1's pending homework submission (not yet submitted)."""
    with schema_context(center_a.schema_name):
        return Submission.objects.create(
            user_id=student_a1.id,
            homework_assignment=homework_assignment_a,
            status=Submission.Status.STARTED,
            score=None,
            results={},
        )


@pytest.fixture
def submission_student_a2_graded(db, student_a2, exam_assignment_a, center_a):
    """Student A2's graded submission."""
    with schema_context(center_a.schema_name):
        return Submission.objects.create(
            user_id=student_a2.id,
            exam_assignment=exam_assignment_a,
            status=Submission.Status.GRADED,
            score=Decimal("120.00"),
            results=_create_jlpt_results(vocab_score=40.0, reading_score=40.0, listening_score=40.0),
            completed_at=timezone.now() - timedelta(days=2),
        )


@pytest.fixture
def submission_student_a2_submitted(db, student_a2, exam_assignment_a, center_a):
    """Student A2's submitted but not yet graded submission."""
    with schema_context(center_a.schema_name):
        return Submission.objects.create(
            user_id=student_a2.id,
            exam_assignment=exam_assignment_a,
            status=Submission.Status.SUBMITTED,
            score=None,
            results={},
            completed_at=timezone.now(),
        )


# ============================================================================
# JWT TOKEN FIXTURES
# ============================================================================

@pytest.fixture
def jwt_token_owner(owner_user):
    """JWT token for owner."""
    return str(RefreshToken.for_user(owner_user).access_token)


@pytest.fixture
def jwt_token_center_admin_a(center_admin_a):
    """JWT token for Center Admin A."""
    return str(RefreshToken.for_user(center_admin_a).access_token)


@pytest.fixture
def jwt_token_center_admin_b(center_admin_b):
    """JWT token for Center Admin B."""
    return str(RefreshToken.for_user(center_admin_b).access_token)


@pytest.fixture
def jwt_token_teacher_a(teacher_a):
    """JWT token for Teacher A."""
    return str(RefreshToken.for_user(teacher_a).access_token)


@pytest.fixture
def jwt_token_teacher_b(teacher_b):
    """JWT token for Teacher B."""
    return str(RefreshToken.for_user(teacher_b).access_token)


@pytest.fixture
def jwt_token_student_a1(student_a1):
    """JWT token for Student A1."""
    return str(RefreshToken.for_user(student_a1).access_token)


@pytest.fixture
def jwt_token_student_a2(student_a2):
    """JWT token for Student A2."""
    return str(RefreshToken.for_user(student_a2).access_token)


@pytest.fixture
def jwt_token_student_b1(student_b1):
    """JWT token for Student B1."""
    return str(RefreshToken.for_user(student_b1).access_token)


# ============================================================================
# API CLIENT FIXTURES
# ============================================================================

@pytest.fixture
def api_client(db):
    """Unauthenticated API client."""
    from rest_framework.test import APIClient
    client = APIClient()
    client.raise_request_exception = True
    return client


@pytest.fixture
def api_client_owner(api_client, jwt_token_owner):
    """API client authenticated as owner."""
    api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {jwt_token_owner}")
    return api_client


@pytest.fixture
def api_client_center_admin_a(api_client, jwt_token_center_admin_a):
    """API client authenticated as Center Admin A."""
    api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {jwt_token_center_admin_a}")
    return api_client


@pytest.fixture
def api_client_center_admin_b(api_client, jwt_token_center_admin_b):
    """API client authenticated as Center Admin B."""
    api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {jwt_token_center_admin_b}")
    return api_client


@pytest.fixture
def api_client_teacher_a(api_client, jwt_token_teacher_a):
    """API client authenticated as Teacher A."""
    api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {jwt_token_teacher_a}")
    return api_client


@pytest.fixture
def api_client_teacher_b(api_client, jwt_token_teacher_b):
    """API client authenticated as Teacher B."""
    api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {jwt_token_teacher_b}")
    return api_client


@pytest.fixture
def api_client_student_a1(api_client, jwt_token_student_a1):
    """API client authenticated as Student A1."""
    api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {jwt_token_student_a1}")
    return api_client


@pytest.fixture
def api_client_student_a2(api_client, jwt_token_student_a2):
    """API client authenticated as Student A2."""
    api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {jwt_token_student_a2}")
    return api_client


@pytest.fixture
def api_client_student_b1(api_client, jwt_token_student_b1):
    """API client authenticated as Student B1."""
    api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {jwt_token_student_b1}")
    return api_client
