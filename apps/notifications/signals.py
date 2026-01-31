# apps/notifications/signals.py
"""
Notification triggers. All handlers run in tenant context (signals from tenant models).
Every trigger uses transaction.on_commit() so the real-time push happens only after the
DB transaction commits (atomic; no race where we notify before data is saved).
Debounce: one notification per (user, type, related_id) via batch check before sending.
Notification model lives in tenant schema; no with_public_schema needed here.
"""
import logging
from django.apps import apps
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.db import transaction

from apps.notifications.services import NotificationService

logger = logging.getLogger(__name__)


def _get_notification_model():
    return apps.get_model("notifications", "Notification")


# ---------------------------------------------------------------------------
# Exam Assignment: status -> OPEN
# ---------------------------------------------------------------------------

@receiver(post_save, sender=apps.get_model("assignments", "ExamAssignment"))
def exam_assignment_opened_handler(sender, instance, created, **kwargs):
    if instance.status != instance.RoomStatus.OPEN:
        return
    Notification = _get_notification_model()
    GroupMembership = apps.get_model("groups", "GroupMembership")
    group_ids = list(instance.assigned_groups.values_list("id", flat=True))
    if not group_ids:
        return
    student_user_ids = set(
        GroupMembership.objects.filter(
            group_id__in=group_ids,
            role_in_group="STUDENT",
        ).values_list("user_id", flat=True)
    )
    if not student_user_ids:
        return
    exam_id = instance.id
    title = instance.title
    link = f"/exams/{instance.id}/"

    def _notify():
        already = set(
            Notification.objects.filter(
                user_id__in=student_user_ids,
                notification_type=Notification.NotificationType.EXAM_OPENED,
                related_task_id=exam_id,
            ).values_list("user_id", flat=True)
        )
        for user_id in student_user_ids - already:
            NotificationService.send_notification(
                user_id=user_id,
                message=f"Exam '{title}' is now open.",
                type=Notification.NotificationType.EXAM_OPENED,
                link=link,
                related_ids={"task_id": exam_id},
            )

    transaction.on_commit(_notify)


# ---------------------------------------------------------------------------
# Homework Assigned: HomeworkAssignment.assigned_groups / assigned_user_ids
# ---------------------------------------------------------------------------

@receiver(post_save, sender=apps.get_model("assignments", "HomeworkAssignment"))
def homework_assigned_handler(sender, instance, created, **kwargs):
    Notification = _get_notification_model()
    GroupMembership = apps.get_model("groups", "GroupMembership")
    group_ids = list(instance.assigned_groups.values_list("id", flat=True))
    group_student_ids = GroupMembership.objects.filter(
        group_id__in=group_ids,
        role_in_group="STUDENT",
    ).values_list("user_id", flat=True)
    explicit_user_ids = instance.assigned_user_ids or []
    target_user_ids = set(group_student_ids) | set(explicit_user_ids)
    if not target_user_ids:
        return
    hw_id = instance.id
    title = instance.title
    link = f"/homeworks/{instance.id}/"

    def _notify():
        already = set(
            Notification.objects.filter(
                user_id__in=target_user_ids,
                notification_type=Notification.NotificationType.TASK_ASSIGNED,
                related_task_id=hw_id,
            ).values_list("user_id", flat=True)
        )
        for user_id in target_user_ids - already:
            NotificationService.send_notification(
                user_id=user_id,
                message=f"New homework '{title}' has been assigned to you.",
                type=Notification.NotificationType.TASK_ASSIGNED,
                link=link,
                related_ids={"task_id": hw_id},
            )

    transaction.on_commit(_notify)


# ---------------------------------------------------------------------------
# Submission Graded
# ---------------------------------------------------------------------------

@receiver(post_save, sender=apps.get_model("attempts", "Submission"))
def submission_graded_handler(sender, instance, created, update_fields=None, **kwargs):
    if instance.status != instance.Status.GRADED:
        return
    if not created and update_fields is not None and "status" not in update_fields:
        return
    Notification = _get_notification_model()
    user_id = instance.user_id
    submission_id = instance.id

    def _notify():
        if Notification.objects.filter(
            user_id=user_id,
            notification_type=Notification.NotificationType.SUBMISSION_GRADED,
            related_submission_id=submission_id,
        ).exists():
            return
        if instance.homework_assignment:
            title = instance.homework_assignment.title
            message = f"Your homework submission for '{title}' has been graded."
            link = f"/homeworks/{instance.homework_assignment.id}/results/"
        elif instance.exam_assignment:
            title = instance.exam_assignment.title
            message = f"Your exam submission for '{title}' has been graded."
            link = f"/exams/{instance.exam_assignment.id}/results/"
        else:
            message = "Your submission has been graded."
            link = None
        NotificationService.send_notification(
            user_id=user_id,
            message=message,
            type=Notification.NotificationType.SUBMISSION_GRADED,
            link=link,
            related_ids={"submission_id": submission_id},
        )

    transaction.on_commit(_notify)


# ---------------------------------------------------------------------------
# Group Added (GroupMembership created)
# ---------------------------------------------------------------------------

@receiver(post_save, sender=apps.get_model("groups", "GroupMembership"))
def group_membership_created_handler(sender, instance, created, **kwargs):
    if not created:
        return
    Notification = _get_notification_model()
    group = instance.group
    user_id = instance.user_id
    group_id = group.id
    group_name = group.name
    role = instance.role_in_group.capitalize()
    link = f"/groups/{group_id}/"
    message = f"You have been added to group '{group_name}' as {role}."

    def _notify():
        if Notification.objects.filter(
            user_id=user_id,
            notification_type=Notification.NotificationType.GROUP_ADDED,
            related_group_id=group_id,
        ).exists():
            return
        NotificationService.send_notification(
            user_id=user_id,
            message=message,
            type=Notification.NotificationType.GROUP_ADDED,
            link=link,
            related_ids={"group_id": group_id},
        )

    transaction.on_commit(_notify)