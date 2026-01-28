# apps/notifications/services.py
from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.apps import apps
from django.db import transaction
import logging

logger = logging.getLogger(__name__)


class NotificationService:
    """
    Central service for creating and dispatching notifications.

    Usage (sync-safe):

        NotificationService.send_notification(
            user_id=user.id,
            message="Your submission has been graded.",
            type="SUBMISSION_GRADED",
            link="/homeworks/123/",
            related_ids={"submission_id": submission.id}
        )
    """

    @staticmethod
    def send_notification(user_id, message, type, link=None, related_ids=None):
        """
        Create a Notification row and push it via WebSocket.

        Args:
            user_id (int): Public user ID (from authentication.User)
            message (str): Human-readable message to display
            type (str): One of Notification.NotificationType.*
            link (str|None): Optional URL for frontend navigation
            related_ids (dict): Optional related IDs:
                {
                    "task_id": UUID,
                    "submission_id": UUID,
                    "group_id": UUID,
                    "contact_request_id": UUID,
                }

        Returns:
            Notification instance
        """
        if not user_id:
            logger.warning("send_notification called without user_id")
            return None

        related_ids = related_ids or {}

        Notification = apps.get_model("notifications", "Notification")
        from apps.notifications.serializers import NotificationSerializer  # lazy import

        # Step 1: DB row
        notification = Notification.objects.create(
            user_id=user_id,
            notification_type=type,
            message=message,
            link=link,
            related_task_id=related_ids.get("task_id"),
            related_submission_id=related_ids.get("submission_id"),
            related_group_id=related_ids.get("group_id"),
            related_contact_request_id=related_ids.get("contact_request_id"),
        )

        # Step 2: WebSocket push
        try:
            payload = NotificationSerializer(notification).data
        except Exception as e:
            logger.error("Failed to serialize notification %s: %s", notification.id, e)
            payload = {
                "id": str(notification.id),
                "message": notification.message,
                "notification_type": notification.notification_type,
                "is_read": notification.is_read,
                "link": notification.link,
            }

        channel_layer = get_channel_layer()
        if not channel_layer:
            logger.warning("No channel layer configured; skipping WS dispatch.")
            return notification

        group_name = f"notify_{user_id}"

        try:
            async_to_sync(channel_layer.group_send)(
                group_name,
                {
                    "type": "send_notification",  # mapped to consumer method
                    "message": payload,
                },
            )
        except Exception as e:
            # DB notification is already stored; WS failure should not break flow
            logger.error("Failed to send WS notification to %s: %s", group_name, e)

        return notification

    @staticmethod
    def send_notification_on_commit(user_id, message, type, link=None, related_ids=None):
        """
        Convenience helper: schedule notification after current DB transaction commits.
        Useful in signal handlers to avoid race conditions.
        """
        transaction.on_commit(
            lambda: NotificationService.send_notification(
                user_id=user_id,
                message=message,
                type=type,
                link=link,
                related_ids=related_ids or {},
            )
        )