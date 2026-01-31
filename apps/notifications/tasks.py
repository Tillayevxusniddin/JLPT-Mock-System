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
from django.utils import timezone

from apps.core.tenant_utils import schema_context
from apps.notifications.services import NotificationService

logger = logging.getLogger(__name__)


def _send_deadline_alerts(hw, pending_user_ids, Notification, results):
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


@shared_task(bind=True, max_retries=3)
def check_upcoming_deadlines(self):
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