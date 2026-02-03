# apps/notifications/signals.py
"""
Notification triggers. All handlers run in tenant context (signals from tenant models).
Every trigger uses transaction.on_commit() so the real-time push happens only after the
DB transaction commits (atomic; no race where we notify before data is saved).
Debounce: one notification per (user, type, related_id) via batch check before sending.
Notification model lives in tenant schema; no with_public_schema needed here.

_create_notification: Shared helper for centers/groups (and any caller) to create
a notification in a tenant schema and push via WebSocket. When center is None
(Owner / platform-wide), only pushes to WebSocket (no DB row; Notification is tenant-scoped).
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


def _push_to_websocket(user_id, payload):
    """Send a notification payload to the user's WebSocket group (notify_{user_id})."""
    from asgiref.sync import async_to_sync
    from channels.layers import get_channel_layer
    channel_layer = get_channel_layer()
    if not channel_layer:
        logger.warning("No channel layer configured; skipping WS push.")
        return
    group_name = f"notify_{user_id}"
    try:
        async_to_sync(channel_layer.group_send)(
            group_name,
            {"type": "send_notification", "message": payload},
        )
    except Exception as e:
        logger.error("Failed to push notification to %s: %s", group_name, e)


def _create_notification(
    center,
    user_id,
    message,
    notification_type,
    link=None,
    related_task_id=None,
    related_submission_id=None,
    related_group_id=None,
    related_contact_request_id=None,
):
    """
    Create a notification and push via WebSocket.

    When center is not None: switch to center's tenant schema, create Notification
    row, serialize, and push. When center is None (Owner / platform-wide): push
    only (no DB row; Notification model is tenant-scoped). Returns the
    Notification instance when created, else None.
    """
    if not user_id:
        logger.warning("_create_notification called without user_id")
        return None

    Notification = _get_notification_model()

    if center is not None:
        # Tenant notification: create row in tenant schema, then push
        schema_name = getattr(center, "schema_name", None)
        if not schema_name:
            logger.warning("_create_notification: center has no schema_name, push-only")
            payload = {
                "id": None,
                "user_id": user_id,
                "notification_type": notification_type,
                "message": message,
                "is_read": False,
                "link": link or "",
                "related_task_id": str(related_task_id) if related_task_id else None,
                "related_submission_id": str(related_submission_id) if related_submission_id else None,
                "related_group_id": str(related_group_id) if related_group_id else None,
                "related_contact_request_id": str(related_contact_request_id) if related_contact_request_id else None,
                "created_at": None,
                "updated_at": None,
            }
            _push_to_websocket(user_id, payload)
            return None

        from apps.core.tenant_utils import schema_context
        from apps.notifications.serializers import NotificationSerializer

        with schema_context(schema_name):
            notification = Notification.objects.create(
                user_id=user_id,
                notification_type=notification_type,
                message=message,
                link=link,
                related_task_id=related_task_id,
                related_submission_id=related_submission_id,
                related_group_id=related_group_id,
                related_contact_request_id=related_contact_request_id,
            )
            payload = NotificationSerializer(notification).data
        _push_to_websocket(user_id, payload)
        return notification

    # Owner (platform-wide): push only; no tenant schema to store in
    payload = {
        "id": None,
        "user_id": user_id,
        "notification_type": notification_type,
        "message": message,
        "is_read": False,
        "link": link or "",
        "related_task_id": str(related_task_id) if related_task_id else None,
        "related_submission_id": str(related_submission_id) if related_submission_id else None,
        "related_group_id": str(related_group_id) if related_group_id else None,
        "related_contact_request_id": str(related_contact_request_id) if related_contact_request_id else None,
        "created_at": None,
        "updated_at": None,
    }
    _push_to_websocket(user_id, payload)
    return None


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