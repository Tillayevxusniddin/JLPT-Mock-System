import pytest
from django.db import transaction

from apps.notifications.models import Notification
from apps.assignments.models import ExamAssignment


@pytest.mark.django_db(transaction=True)
def test_exam_opened_only_approved_receive(
    tenant_schema,
    exam_assignment,
    membership_approved,
    membership_unapproved,
    approved_student,
    unapproved_student,
    mock_dispatch_ws,
):
    exam_assignment.status = ExamAssignment.RoomStatus.OPEN
    exam_assignment.save(update_fields=["status"])

    notifications = Notification.objects.filter(
        notification_type=Notification.NotificationType.EXAM_OPENED,
        related_task_id=exam_assignment.id,
    )

    assert notifications.filter(user_id=approved_student.id).exists()
    assert not notifications.filter(user_id=unapproved_student.id).exists()

    user_ids = {c["user_id"] for c in mock_dispatch_ws}
    assert approved_student.id in user_ids
    assert unapproved_student.id not in user_ids


@pytest.mark.django_db(transaction=True)
def test_unapproved_receives_nothing_db_and_ws(
    tenant_schema,
    exam_assignment,
    membership_unapproved,
    unapproved_student,
    mock_dispatch_ws,
):
    exam_assignment.status = ExamAssignment.RoomStatus.OPEN
    exam_assignment.save(update_fields=["status"])

    assert not Notification.objects.filter(user_id=unapproved_student.id).exists()
    user_ids = {c["user_id"] for c in mock_dispatch_ws}
    assert unapproved_student.id not in user_ids
