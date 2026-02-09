"""Fixtures for Notifications app QA automation."""
from contextlib import contextmanager

import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken
from channels.testing import WebsocketCommunicator

from config.asgi import application
from apps.centers.models import Center
from apps.core.tenant_utils import schema_context
from apps.groups.models import Group, GroupMembership
from apps.mock_tests.models import MockTest, TestSection
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
    return Center.objects.create(name="Test Center", schema_name="test_tenant")


@pytest.fixture
def approved_student(db, test_center):
    return User.objects.create_user(
        email="approved@student.test",
        password="Pass12345!",
        role=User.Role.STUDENT,
        center=test_center,
        is_active=True,
        is_approved=True,
    )


@pytest.fixture
def unapproved_student(db, test_center):
    return User.objects.create_user(
        email="unapproved@student.test",
        password="Pass12345!",
        role=User.Role.STUDENT,
        center=test_center,
        is_active=True,
        is_approved=False,
    )


@pytest.fixture
def teacher_user(db, test_center):
    return User.objects.create_user(
        email="teacher@center.test",
        password="Pass12345!",
        role=User.Role.TEACHER,
        center=test_center,
        is_active=True,
        is_approved=True,
    )


@pytest.fixture
def tenant_schema(test_center):
    """Run DB ops in a tenant schema context (public schema in tests)."""
    with schema_context(test_center.schema_name):
        yield


@pytest.fixture
def group_a(db, tenant_schema):
    return Group.objects.create(name="Group A")


@pytest.fixture
def membership_approved(db, tenant_schema, approved_student, group_a):
    return GroupMembership.objects.create(
        group=group_a,
        user_id=approved_student.id,
        role_in_group=GroupMembership.ROLE_STUDENT,
    )


@pytest.fixture
def membership_unapproved(db, tenant_schema, unapproved_student, group_a):
    return GroupMembership.objects.create(
        group=group_a,
        user_id=unapproved_student.id,
        role_in_group=GroupMembership.ROLE_STUDENT,
    )


@pytest.fixture
def mock_test_basic(db, tenant_schema, teacher_user):
    mock_test = MockTest.objects.create(
        title="Mock Test",
        level=MockTest.Level.N5,
        status=MockTest.Status.PUBLISHED,
        created_by_id=teacher_user.id,
    )
    TestSection.objects.create(
        mock_test=mock_test,
        name="Vocabulary",
        section_type=TestSection.SectionType.VOCAB,
        duration=20,
        order=1,
        total_score=60,
    )
    TestSection.objects.create(
        mock_test=mock_test,
        name="Listening",
        section_type=TestSection.SectionType.LISTENING,
        duration=30,
        order=2,
        total_score=60,
    )
    return mock_test


@pytest.fixture
def exam_assignment(db, tenant_schema, teacher_user, group_a, mock_test_basic):
    exam = ExamAssignment.objects.create(
        title="Exam",
        description="Exam",
        mock_test=mock_test_basic,
        status=ExamAssignment.RoomStatus.CLOSED,
        created_by_id=teacher_user.id,
    )
    exam.assigned_groups.set([group_a.id])
    return exam


@pytest.fixture
def homework_assignment(db, tenant_schema, teacher_user, group_a, mock_test_basic):
    from django.utils import timezone
    from datetime import timedelta

    hw = HomeworkAssignment.objects.create(
        title="Homework",
        description="HW",
        deadline=timezone.now() + timedelta(days=7),
        created_by_id=teacher_user.id,
        show_results_immediately=True,
    )
    hw.assigned_groups.set([group_a.id])
    hw.mock_tests.set([mock_test_basic.id])
    return hw


@pytest.fixture
def jwt_token_for_approved(approved_student):
    return str(RefreshToken.for_user(approved_student).access_token)


@pytest.fixture
def jwt_token_for_unapproved(unapproved_student):
    return str(RefreshToken.for_user(unapproved_student).access_token)


@pytest.fixture
async def ws_communicator_student(jwt_token_for_approved):
    path = f"/ws/notifications/?token={jwt_token_for_approved}"
    communicator = WebsocketCommunicator(application, path)
    connected, _ = await communicator.connect()
    assert connected is True
    try:
        yield communicator
    finally:
        await communicator.disconnect()


@pytest.fixture
def api_client_approved(api_client, approved_student):
    api_client.force_authenticate(user=approved_student)
    return api_client


@pytest.fixture
def api_client_unapproved(api_client, unapproved_student):
    api_client.force_authenticate(user=unapproved_student)
    return api_client


@pytest.fixture
def mock_dispatch_ws(monkeypatch):
    calls = []

    def _spy(user_id, payload):
        calls.append({"user_id": user_id, "payload": payload})

    monkeypatch.setattr(
        "apps.notifications.tasks.dispatch_ws_notification.delay",
        lambda user_id, payload: _spy(user_id, payload),
    )
    return calls
