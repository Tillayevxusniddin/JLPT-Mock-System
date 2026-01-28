# apps/notifications/signals.py
import logging
from django.apps import apps
from django.db.models.signals import post_save, m2m_changed
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
    """
    When an ExamAssignment is OPENED, notify all students in assigned groups.

    Debounce: For each (user, exam) pair, only one EXAM_OPENED notification.
    """
    Notification = _get_notification_model()

    # Only when status is OPEN
    if instance.status != instance.RoomStatus.OPEN:
        return

    # Determine target users: students in assigned groups
    GroupMembership = apps.get_model("groups", "GroupMembership")
    group_ids = list(instance.assigned_groups.values_list("id", flat=True))

    if not group_ids:
        return

    student_user_ids = GroupMembership.objects.filter(
        group_id__in=group_ids,
        role_in_group="STUDENT",
    ).values_list("user_id", flat=True)

    student_user_ids = set(student_user_ids)

    def _notify():
        for user_id in student_user_ids:
            # Debounce: skip if already notified for this exam
            if Notification.objects.filter(
                user_id=user_id,
                notification_type=Notification.NotificationType.EXAM_OPENED,
                related_task_id=instance.id,
            ).exists():
                continue

            message = f"Exam '{instance.title}' is now open."
            link = f"/exams/{instance.id}/"
            NotificationService.send_notification(
                user_id=user_id,
                message=message,
                type=Notification.NotificationType.EXAM_OPENED,
                link=link,
                related_ids={"task_id": instance.id},
            )

    transaction.on_commit(_notify)


# ---------------------------------------------------------------------------
# Homework Assigned: HomeworkAssignment.assigned_groups / assigned_user_ids
# ---------------------------------------------------------------------------

@receiver(post_save, sender=apps.get_model("assignments", "HomeworkAssignment"))
def homework_assigned_handler(sender, instance, created, **kwargs):
    """
    Notify students when homework is assigned.

    Trigger: post_save on HomeworkAssignment.
    - Uses assigned_groups and assigned_user_ids.
    - Debounced per (user, homework) pair via TASK_ASSIGNED + related_task_id.
    """
    Notification = _get_notification_model()
    GroupMembership = apps.get_model("groups", "GroupMembership")

    # Target users from groups
    group_ids = list(instance.assigned_groups.values_list("id", flat=True))
    group_student_ids = GroupMembership.objects.filter(
        group_id__in=group_ids,
        role_in_group="STUDENT",
    ).values_list("user_id", flat=True)

    # Target users explicitly assigned (ArrayField on HomeworkAssignment)
    explicit_user_ids = instance.assigned_user_ids or []

    target_user_ids = set(group_student_ids) | set(explicit_user_ids)
    if not target_user_ids:
        return

    def _notify():
        for user_id in target_user_ids:
            # Debounce: skip if we already have TASK_ASSIGNED for this homework
            if Notification.objects.filter(
                user_id=user_id,
                notification_type=Notification.NotificationType.TASK_ASSIGNED,
                related_task_id=instance.id,
            ).exists():
                continue

            message = f"New homework '{instance.title}' has been assigned to you."
            link = f"/homeworks/{instance.id}/"
            NotificationService.send_notification(
                user_id=user_id,
                message=message,
                type=Notification.NotificationType.TASK_ASSIGNED,
                link=link,
                related_ids={"task_id": instance.id},
            )

    transaction.on_commit(_notify)


# ---------------------------------------------------------------------------
# Submission Graded
# ---------------------------------------------------------------------------

@receiver(post_save, sender=apps.get_model("attempts", "Submission"))
def submission_graded_handler(sender, instance, created, update_fields=None, **kwargs):
    """
    When a Submission becomes GRADED, notify the student.

    Debounce: One SUBMISSION_GRADED notification per submission.
    """
    Notification = _get_notification_model()

    # Only act when status is GRADED
    if instance.status != instance.Status.GRADED:
        return

    # If update_fields is present and status wasn't updated, ignore
    if not created and update_fields is not None and "status" not in update_fields:
        return

    def _notify():
        # Debounce: one per (user, submission)
        if Notification.objects.filter(
            user_id=instance.user_id,
            notification_type=Notification.NotificationType.SUBMISSION_GRADED,
            related_submission_id=instance.id,
        ).exists():
            return

        # Build message based on context
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
            user_id=instance.user_id,
            message=message,
            type=Notification.NotificationType.SUBMISSION_GRADED,
            link=link,
            related_ids={"submission_id": instance.id},
        )

    transaction.on_commit(_notify)


# ---------------------------------------------------------------------------
# Group Added (GroupMembership created)
# ---------------------------------------------------------------------------

@receiver(post_save, sender=apps.get_model("groups", "GroupMembership"))
def group_membership_created_handler(sender, instance, created, **kwargs):
    """
    Notify user when they are added to a group.

    Covers both students and teachers.
    Debounce: One GROUP_ADDED per (user, group).
    """
    if not created:
        return

    Notification = _get_notification_model()
    group = instance.group
    user_id = instance.user_id

    def _notify():
        if Notification.objects.filter(
            user_id=user_id,
            notification_type=Notification.NotificationType.GROUP_ADDED,
            related_group_id=group.id,
        ).exists():
            return

        role = instance.role_in_group.capitalize()
        message = f"You have been added to group '{group.name}' as {role}."
        link = f"/groups/{group.id}/"

        NotificationService.send_notification(
            user_id=user_id,
            message=message,
            type=Notification.NotificationType.GROUP_ADDED,
            link=link,
            related_ids={"group_id": group.id},
        )

    transaction.on_commit(_notify)