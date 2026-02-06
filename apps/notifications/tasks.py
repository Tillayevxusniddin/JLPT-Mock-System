# apps/notifications/tasks.py
"""
Celery periodic task: check upcoming homework deadlines and send DEADLINE_APPROACHING.

Multi-tenant: Iterates all active centers (public), switches to tenant schema per center,
finds homeworks with deadline in the next 24h, identifies students who have NOT yet
submitted (no GRADED submission), then sends DEADLINE_APPROACHING with batch debounce
(no duplicate alert per (user, homework) pair).
"""
from datetime import timedelta
import logging

from celery import shared_task
from django.apps import apps
from django.db import models
from django.utils import timezone
from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer

from apps.core.tenant_utils import schema_context
from apps.notifications.services import NotificationService

logger = logging.getLogger(__name__)


def _send_deadline_alerts(hw, pending_user_ids: set, Notification, results: dict) -> None:
    """
    Send DEADLINE_APPROACHING to pending users. Batch debounce: skip users who already
    have a DEADLINE_APPROACHING notification for this (user, homework) pair.
    """
    already_sent = set(
        Notification.objects.filter(
            user_id__in=pending_user_ids,
            notification_type=Notification.NotificationType.DEADLINE_APPROACHING,
            related_task_id=hw.id,
        ).values_list("user_id", flat=True)
    )
    due_str = hw.deadline.astimezone().strftime("%Y-%m-%d %H:%M")
    link = f"/homeworks/{hw.id}/"
    for uid in pending_user_ids - already_sent:
        NotificationService.send_notification(
            user_id=uid,
            message=f"Homework '{hw.title}' is due by {due_str}.",
            type=Notification.NotificationType.DEADLINE_APPROACHING,
            link=link,
            related_ids={"task_id": hw.id},
        )
        results["notifications_sent"] += 1


@shared_task
def dispatch_ws_notification(user_id: int, payload: dict) -> None:
    """
    Fan-out WebSocket dispatch. Runs in Celery worker to avoid blocking request threads.
    """
    channel_layer = get_channel_layer()
    if not channel_layer:
        logger.warning("No channel layer configured; skipping WS dispatch.")
        return
    group_name = f"notify_{user_id}"
    try:
        async_to_sync(channel_layer.group_send)(
            group_name,
            {"type": "send_notification", "message": payload},
        )
    except Exception as e:
        logger.error("Failed to send WS notification to %s: %s", group_name, e)


@shared_task(bind=True, max_retries=3)
def check_upcoming_deadlines(self) -> dict:
    Center = apps.get_model("centers", "Center")
    HomeworkAssignment = apps.get_model("assignments", "HomeworkAssignment")
    Submission = apps.get_model("attempts", "Submission")
    Notification = apps.get_model("notifications", "Notification")
    GroupMembership = apps.get_model("groups", "GroupMembership")

    now = timezone.now()
    window_end = now + timedelta(hours=24)
    results = {"centers_checked": 0, "homeworks_scanned": 0, "notifications_sent": 0}

    # Active centers with tenant schema (public schema query)
    active_centers = Center.objects.filter(
        status=Center.Status.ACTIVE,
        schema_name__isnull=False,
    ).exclude(schema_name="")

    for center in active_centers:
        results["centers_checked"] += 1
        try:
            with schema_context(center.schema_name):
                homeworks = HomeworkAssignment.objects.filter(
                    deadline__gt=now,
                    deadline__lte=window_end,
                )
                for hw in homeworks:
                    results["homeworks_scanned"] += 1
                    group_ids = list(hw.assigned_groups.values_list("id", flat=True))
                    group_student_ids = set(
                        GroupMembership.objects.filter(
                            group_id__in=group_ids,
                            role_in_group="STUDENT",
                        ).values_list("user_id", flat=True)
                    )
                    explicit_user_ids = set(hw.assigned_user_ids or [])
                    target_user_ids = group_student_ids | explicit_user_ids
                    if not target_user_ids:
                        continue
                    # Students who have already submitted (GRADED = final state)
                    submitted_user_ids = set(
                        Submission.objects.filter(
                            homework_assignment=hw,
                            status=Submission.Status.GRADED,
                        ).values_list("user_id", flat=True)
                    )
                    pending_user_ids = target_user_ids - submitted_user_ids
                    if not pending_user_ids:
                        continue
                    _send_deadline_alerts(hw, pending_user_ids, Notification, results)
        except Exception as e:
            logger.error(
                "Error checking deadlines for center %s (%s): %s",
                center.id,
                center.schema_name,
                e,
                exc_info=True,
            )
    logger.info("check_upcoming_deadlines results: %s", results)
    return results


@shared_task(bind=True, max_retries=3)
def check_review_overdue(self) -> dict:
    """
    Send REVIEW_OVERDUE notifications to teachers for submissions pending > 48h.
    Multi-tenant iteration across active centers.
    """
    Center = apps.get_model("centers", "Center")
    Submission = apps.get_model("attempts", "Submission")
    Notification = apps.get_model("notifications", "Notification")
    GroupMembership = apps.get_model("groups", "GroupMembership")

    now = timezone.now()
    overdue_before = now - timedelta(hours=48)
    results = {"centers_checked": 0, "overdue_submissions": 0, "notifications_sent": 0}

    active_centers = Center.objects.filter(
        status=Center.Status.ACTIVE,
        schema_name__isnull=False,
    ).exclude(schema_name="")

    for center in active_centers:
        results["centers_checked"] += 1
        try:
            with schema_context(center.schema_name):
                overdue_qs = Submission.objects.filter(
                    status=Submission.Status.SUBMITTED,
                    created_at__lte=overdue_before,
                ).select_related("exam_assignment", "homework_assignment")
                for sub in overdue_qs:
                    results["overdue_submissions"] += 1
                    group_ids = []
                    if sub.exam_assignment_id:
                        group_ids = list(sub.exam_assignment.assigned_groups.values_list("id", flat=True))
                    elif sub.homework_assignment_id:
                        group_ids = list(sub.homework_assignment.assigned_groups.values_list("id", flat=True))
                    if not group_ids:
                        continue
                    teacher_ids = set(
                        GroupMembership.objects.filter(
                            group_id__in=group_ids,
                            role_in_group="TEACHER",
                        ).values_list("user_id", flat=True)
                    )
                    if not teacher_ids:
                        continue
                    already = set(
                        Notification.objects.filter(
                            user_id__in=teacher_ids,
                            notification_type=Notification.NotificationType.REVIEW_OVERDUE,
                            related_submission_id=sub.id,
                        ).values_list("user_id", flat=True)
                    )
                    for uid in teacher_ids - already:
                        NotificationService.send_notification(
                            user_id=uid,
                            message="A submission has been awaiting review for over 48 hours.",
                            type=Notification.NotificationType.REVIEW_OVERDUE,
                            link=None,
                            related_ids={"submission_id": sub.id},
                        )
                        results["notifications_sent"] += 1
        except Exception as e:
            logger.error(
                "Error checking overdue reviews for center %s (%s): %s",
                center.id,
                center.schema_name,
                e,
                exc_info=True,
            )
    logger.info("check_review_overdue results: %s", results)
    return results


@shared_task(bind=True, max_retries=3)
def check_exam_closing_soon(self) -> dict:
    """
    Send EXAM_CLOSING_SOON notifications 1 hour before exam room closes.
    Exam close time is estimated_start_time + sum(section.duration) minutes.
    """
    Center = apps.get_model("centers", "Center")
    ExamAssignment = apps.get_model("assignments", "ExamAssignment")
    TestSection = apps.get_model("mock_tests", "TestSection")
    Notification = apps.get_model("notifications", "Notification")
    GroupMembership = apps.get_model("groups", "GroupMembership")

    now = timezone.now()
    window_end = now + timedelta(hours=1)
    results = {"centers_checked": 0, "exams_scanned": 0, "notifications_sent": 0}

    active_centers = Center.objects.filter(
        status=Center.Status.ACTIVE,
        schema_name__isnull=False,
    ).exclude(schema_name="")

    for center in active_centers:
        results["centers_checked"] += 1
        try:
            with schema_context(center.schema_name):
                exams = ExamAssignment.objects.filter(
                    status=ExamAssignment.RoomStatus.OPEN,
                    estimated_start_time__isnull=False,
                ).select_related("mock_test")
                for exam in exams:
                    results["exams_scanned"] += 1
                    if not exam.mock_test_id:
                        continue
                    total_minutes = (
                        TestSection.objects.filter(mock_test_id=exam.mock_test_id)
                        .aggregate(total=models.Sum("duration"))
                        .get("total")
                    )
                    if not total_minutes:
                        continue
                    close_time = exam.estimated_start_time + timedelta(minutes=int(total_minutes))
                    if not (now <= close_time <= window_end):
                        continue
                    group_ids = list(exam.assigned_groups.values_list("id", flat=True))
                    if not group_ids:
                        continue
                    student_ids = set(
                        GroupMembership.objects.filter(
                            group_id__in=group_ids,
                            role_in_group="STUDENT",
                        ).values_list("user_id", flat=True)
                    )
                    if not student_ids:
                        continue
                    already = set(
                        Notification.objects.filter(
                            user_id__in=student_ids,
                            notification_type=Notification.NotificationType.EXAM_CLOSING_SOON,
                            related_task_id=exam.id,
                        ).values_list("user_id", flat=True)
                    )
                    for uid in student_ids - already:
                        NotificationService.send_notification(
                            user_id=uid,
                            message=f"Exam '{exam.title}' will close in 1 hour.",
                            type=Notification.NotificationType.EXAM_CLOSING_SOON,
                            link=f"/exams/{exam.id}/",
                            related_ids={"task_id": exam.id},
                        )
                        results["notifications_sent"] += 1
        except Exception as e:
            logger.error(
                "Error checking exam closing soon for center %s (%s): %s",
                center.id,
                center.schema_name,
                e,
                exc_info=True,
            )
    logger.info("check_exam_closing_soon results: %s", results)
    return results