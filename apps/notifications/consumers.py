# apps/notifications/consumers.py
"""
WebSocket consumer for real-time notifications.

Security & isolation (master-level):
- User identity comes ONLY from JWTAuthMiddleware (scope["user"]). No user IDs in URL or path.
- Group name is server-controlled: notify_{user_id}. A user can only be added to their own
  channel; they cannot subscribe to another user's or another tenant's channel.
- Authentication handshake: JWT via query param ?token=<access> or header Authorization: Bearer <access>.
"""
import json
import logging
from channels.generic.websocket import AsyncWebsocketConsumer
from django.contrib.auth.models import AnonymousUser

logger = logging.getLogger(__name__)


class NotificationConsumer(AsyncWebsocketConsumer):
    """
    Real-time notifications over WebSocket.
    Each user is added only to their personal group (notify_{user_id}) derived from scope["user"].
    """

    async def connect(self):
        user = self.scope.get("user")
        if user is None or isinstance(user, AnonymousUser):
            logger.warning("NotificationConsumer: connection rejected (no user or anonymous)")
            await self.close(code=4401)
            return
        if not getattr(user, "is_authenticated", False):
            logger.warning("NotificationConsumer: connection rejected (user not authenticated)")
            await self.close(code=4401)
            return
        user_id = getattr(user, "id", None)
        if user_id is None:
            logger.warning("NotificationConsumer: connection rejected (user has no id)")
            await self.close(code=4401)
            return
        # Server-controlled group name; no client input. Ensures isolation.
        self.group_name = f"notify_{user_id}"
        try:
            await self.channel_layer.group_add(self.group_name, self.channel_name)
            await self.accept()
            logger.debug("NotificationConsumer: user %s connected to %s", user_id, self.group_name)
        except Exception as e:
            logger.exception("NotificationConsumer: failed to add user %s to group: %s", user_id, e)
            try:
                await self.close(code=1011)
            except Exception:
                pass

    async def disconnect(self, close_code):
        if hasattr(self, "group_name"):
            try:
                await self.channel_layer.group_discard(self.group_name, self.channel_name)
            except Exception as e:
                logger.warning("NotificationConsumer: group_discard failed: %s", e)

    async def send_notification(self, event):
        """
        Send notification payload to the WebSocket client.
        event["message"] = dict (serialized notification). Do not leak internal keys.
        """
        message = event.get("message")
        if message is None:
            logger.warning("NotificationConsumer: send_notification called with no message")
            return
        try:
            if not isinstance(message, dict):
                message = {"message": str(message), "notification_type": "ANNOUNCEMENT"}
            await self.send(text_data=json.dumps(message))
        except TypeError as e:
            logger.warning("NotificationConsumer: JSON serialization failed: %s", e)
            try:
                await self.send(text_data=json.dumps({"error": "invalid_payload"}))
            except Exception:
                pass
        except Exception as e:
            logger.warning("NotificationConsumer: send failed: %s", e)
