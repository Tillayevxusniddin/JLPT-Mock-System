"""
Fixtures for Assignments app QA automation.
"""
import pytest
from datetime import timedelta
from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework.test import APIClient

from apps.centers.models import Center
from apps.groups.models import Group, GroupMembership
from apps.mock_tests.models import MockTest, Quiz
from apps.assignments.models import ExamAssignment, HomeworkAssignment

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


@pytest.fixture
def api_client():
    client = APIClient()
    client.raise_request_exception = True
    return client


@pytest.fixture
def test_center(db):
    return Center.objects.create(name="Test Center", schema_name="public")


@pytest.fixture
def foreign_center(db):
    return Center.objects.create(name="Foreign Center", schema_name="foreign")


@pytest.fixture
def admin_user(db, test_center):
    return User.objects.create_user(
        email="admin@center.test",
        password="Pass12345!",
        role=User.Role.CENTERADMIN,
        center=test_center,
        is_active=True,
        is_approved=True,
    )


@pytest.fixture
def teacher_a(db, test_center):
    return User.objects.create_user(
        email="teacher.a@center.test",
        password="Pass12345!",
        role=User.Role.TEACHER,
        center=test_center,
        is_active=True,
        is_approved=True,
    )


@pytest.fixture
def teacher_b(db, test_center):
    return User.objects.create_user(
        email="teacher.b@center.test",
        password="Pass12345!",
        role=User.Role.TEACHER,
        center=test_center,
        is_active=True,
        is_approved=True,
    )


@pytest.fixture
def student_a(db, test_center):
    return User.objects.create_user(
        email="student.a@center.test",
        password="Pass12345!",
        role=User.Role.STUDENT,
        center=test_center,
        is_active=True,
        is_approved=True,
    )


@pytest.fixture
def student_b(db, test_center):
    return User.objects.create_user(
        email="student.b@center.test",
        password="Pass12345!",
        role=User.Role.STUDENT,
        center=test_center,
        is_active=True,
        is_approved=True,
    )


@pytest.fixture
def guest_user(db, test_center):
    return User.objects.create_user(
        email="guest@center.test",
        password="Pass12345!",
        role=User.Role.GUEST,
        center=test_center,
        is_active=True,
        is_approved=True,
    )


@pytest.fixture
def foreign_student(db, foreign_center):
    return User.objects.create_user(
        email="student@foreign.test",
        password="Pass12345!",
        role=User.Role.STUDENT,
        center=foreign_center,
        is_active=True,
        is_approved=True,
    )


@pytest.fixture
def group_a(db):
    return Group.objects.create(name="Group A")


@pytest.fixture
def group_b(db):
    return Group.objects.create(name="Group B")


@pytest.fixture
def membership_teacher_a(db, teacher_a, group_a):
    return GroupMembership.objects.create(
        group=group_a,
        user_id=teacher_a.id,
        role_in_group=GroupMembership.ROLE_TEACHER,
    )


@pytest.fixture
def membership_teacher_b(db, teacher_b, group_b):
    return GroupMembership.objects.create(
        group=group_b,
        user_id=teacher_b.id,
        role_in_group=GroupMembership.ROLE_TEACHER,
    )


@pytest.fixture
def membership_student_a(db, student_a, group_a):
    return GroupMembership.objects.create(
        group=group_a,
        user_id=student_a.id,
        role_in_group=GroupMembership.ROLE_STUDENT,
    )


@pytest.fixture
def membership_student_b(db, student_b, group_b):
    return GroupMembership.objects.create(
        group=group_b,
        user_id=student_b.id,
        role_in_group=GroupMembership.ROLE_STUDENT,
    )


@pytest.fixture
def published_mock_test(db, admin_user):
    return MockTest.objects.create(
        title="Published Mock",
        level=MockTest.Level.N5,
        status=MockTest.Status.PUBLISHED,
        created_by_id=admin_user.id,
    )


@pytest.fixture
def draft_mock_test(db, admin_user):
    return MockTest.objects.create(
        title="Draft Mock",
        level=MockTest.Level.N5,
        status=MockTest.Status.DRAFT,
        created_by_id=admin_user.id,
    )


@pytest.fixture
def active_quiz(db, admin_user):
    return Quiz.objects.create(
        title="Active Quiz",
        description="Quiz desc",
        is_active=True,
        created_by_id=admin_user.id,
    )


@pytest.fixture
def exam_assignment_a(db, teacher_a, group_a, membership_teacher_a, published_mock_test):
    assignment = ExamAssignment.objects.create(
        title="Exam A",
        description="Exam for group A",
        mock_test=published_mock_test,
        status=ExamAssignment.RoomStatus.CLOSED,
        created_by_id=teacher_a.id,
    )
    assignment.assigned_groups.set([group_a.id])
    return assignment


@pytest.fixture
def exam_assignment_b(db, teacher_b, group_b, membership_teacher_b, published_mock_test):
    assignment = ExamAssignment.objects.create(
        title="Exam B",
        description="Exam for group B",
        mock_test=published_mock_test,
        status=ExamAssignment.RoomStatus.CLOSED,
        created_by_id=teacher_b.id,
    )
    assignment.assigned_groups.set([group_b.id])
    return assignment


@pytest.fixture
def homework_assignment_multi(
    db,
    teacher_a,
    group_a,
    membership_teacher_a,
    student_a,
    published_mock_test,
    active_quiz,
):
    assignment = HomeworkAssignment.objects.create(
        title="Homework Multi",
        description="Homework with mock and quiz",
        deadline=timezone.now() + timedelta(days=7),
        created_by_id=teacher_a.id,
        show_results_immediately=True,
    )
    assignment.mock_tests.set([published_mock_test.id])
    assignment.quizzes.set([active_quiz.id])
    assignment.assigned_groups.set([group_a.id])
    assignment.assigned_user_ids = [student_a.id]
    assignment.save(update_fields=["assigned_user_ids"])
    return assignment


@pytest.fixture
def api_client_admin(api_client, admin_user):
    api_client.force_authenticate(user=admin_user)
    return api_client


@pytest.fixture
def api_client_teacher_a(api_client, teacher_a):
    api_client.force_authenticate(user=teacher_a)
    return api_client


@pytest.fixture
def api_client_teacher_b(api_client, teacher_b):
    api_client.force_authenticate(user=teacher_b)
    return api_client


@pytest.fixture
def api_client_student_a(api_client, student_a):
    api_client.force_authenticate(user=student_a)
    return api_client


@pytest.fixture
def api_client_student_b(api_client, student_b):
    api_client.force_authenticate(user=student_b)
    return api_client


@pytest.fixture
def api_client_guest(api_client, guest_user):
    api_client.force_authenticate(user=guest_user)
    return api_client
