import pytest
from datetime import timedelta
from django.db import transaction
from django.utils import timezone

from apps.notifications.models import Notification
from apps.attempts.models import Submission
from apps.assignments.models import HomeworkAssignment


@pytest.mark.django_db(transaction=True)
def test_task_assigned_signal(teacher_user, group_a, mock_test_basic, approved_student, mock_dispatch_ws, tenant_schema):
    hw = HomeworkAssignment.objects.create(
        title="Homework New",
        description="HW",
        deadline=timezone.now() + timedelta(days=7),
        created_by_id=teacher_user.id,
        show_results_immediately=True,
        assigned_user_ids=[approved_student.id],
    )
    hw.assigned_groups.set([group_a.id])
    hw.mock_tests.set([mock_test_basic.id])

    notification = Notification.objects.filter(
        user_id=approved_student.id,
        notification_type=Notification.NotificationType.TASK_ASSIGNED,
        related_task_id=hw.id,
    ).first()

    assert notification is not None
    assert mock_dispatch_ws


@pytest.mark.django_db(transaction=True)
def test_submission_graded_signal(exam_assignment, approved_student, mock_dispatch_ws, tenant_schema):
    submission = Submission.objects.create(
        user_id=approved_student.id,
        exam_assignment=exam_assignment,
        status=Submission.Status.STARTED,
    )

    submission.status = Submission.Status.GRADED
    submission.save(update_fields=["status"])

    notification = Notification.objects.filter(
        user_id=approved_student.id,
        notification_type=Notification.NotificationType.SUBMISSION_GRADED,
        related_submission_id=submission.id,
    ).first()

    assert notification is not None
    assert mock_dispatch_ws
