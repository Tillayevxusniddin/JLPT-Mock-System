# apps/notifications/tasks.py
from datetime import timedelta
import logging

from celery import shared_task
from django.apps import apps
from django.utils import timezone
from django.db import transaction

from apps.core.tenant_utils import schema_context
from apps.notifications.services import NotificationService

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=3)
def check_upcoming_deadlines(self):
    """
    Periodic task to remind students of upcoming homework deadlines.

    Logic:
    - Iterate over all active centers (public schema)
    - For each tenant schema:
        - Find HomeworkAssignments with deadline in the next 24 hours
        - For each homework:
            - Determine assigned students (groups + assigned_user_ids)
            - Exclude students who already submitted (Submission exists)
            - For remaining students:
                - Send DEADLINE_APPROACHING notification
                - Debounce per (user, homework) using Notification table
    """
    Center = apps.get_model("centers", "Center")
    HomeworkAssignment = apps.get_model("assignments", "HomeworkAssignment")
    Submission = apps.get_model("attempts", "Submission")
    Notification = apps.get_model("notifications", "Notification")
    GroupMembership = apps.get_model("groups", "GroupMembership")

    now = timezone.now()
    window_end = now + timedelta(hours=24)

    results = {"centers_checked": 0, "homeworks_scanned": 0, "notifications_sent": 0}

    # Work in public schema for centers
    active_centers = Center.objects.filter(is_active=True, deleted_at__isnull=True)

    for center in active_centers:
        if not center.schema_name:
            continue

        results["centers_checked"] += 1

        try:
            with schema_context(center.schema_name):
                # Find homeworks with upcoming deadlines
                homeworks = HomeworkAssignment.objects.filter(
                    deadline__gt=now,
                    deadline__lte=window_end,
                )

                for hw in homeworks:
                    results["homeworks_scanned"] += 1

                    # Determine all target students: from groups + assigned_user_ids
                    group_ids = list(hw.assigned_groups.values_list("id", flat=True))
                    group_student_ids = GroupMembership.objects.filter(
                        group_id__in=group_ids,
                        role_in_group="STUDENT",
                    ).values_list("user_id", flat=True)

                    explicit_user_ids = hw.assigned_user_ids or []
                    target_user_ids = set(group_student_ids) | set(explicit_user_ids)

                    if not target_user_ids:
                        continue

                    # Students who already submitted (any status other than STARTED)
                    submitted_user_ids = set(
                        Submission.objects.filter(
                            homework_assignment=hw,
                            status__in=[
                                Submission.Status.SUBMITTED,
                                Submission.Status.GRADED,
                            ],
                        ).values_list("user_id", flat=True)
                    )

                    # Students still pending
                    pending_user_ids = target_user_ids - submitted_user_ids
                    if not pending_user_ids:
                        continue

                    def _notify_homework(hw_obj, pending_ids):
                        for uid in pending_ids:
                            # Debounce: one DEADLINE_APPROACHING per (user, homework)
                            if Notification.objects.filter(
                                user_id=uid,
                                notification_type=Notification.NotificationType.DEADLINE_APPROACHING,
                                related_task_id=hw_obj.id,
                            ).exists():
                                continue

                            message = (
                                f"Homework '{hw_obj.title}' is due by "
                                f"{hw_obj.deadline.astimezone().strftime('%Y-%m-%d %H:%M')}."
                            )
                            link = f"/homeworks/{hw_obj.id}/"

                            NotificationService.send_notification(
                                user_id=uid,
                                message=message,
                                type=Notification.NotificationType.DEADLINE_APPROACHING,
                                link=link,
                                related_ids={"task_id": hw_obj.id},
                            )
                            results["notifications_sent"] += 1

                    transaction.on_commit(
                        lambda hw_obj=hw, ids=pending_user_ids: _notify_homework(
                            hw_obj, ids
                        )
                    )

        except Exception as e:
            logger.error(
                "Error while checking homework deadlines for center %s: %s",
                center.id,
                e,
                exc_info=True,
            )
            # Do not fail entire task for a single tenant

    logger.info("check_upcoming_deadlines results: %s", results)
    return results