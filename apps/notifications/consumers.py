#apps/notifications/consumers.py
import json
from channels.generic.websocket import AsyncWebsocketConsumer
from django.contrib.auth.models import AnonymousUser


class NotificationConsumer(AsyncWebsocketConsumer):
    """
    WebSocket consumer for real-time notifications.
    
    Security: Each user gets a strictly personal notification channel.
    No user IDs in URL to prevent IDOR attacks.
    
    Schema Compliance:
    - User context is provided by TenantASGIMiddleware (via scope)
    - Notifications are pushed to this consumer from signals (which handle schema context)
    - This consumer just relays messages, so it's schema-agnostic
    """

    async def connect(self):
        """
        Handle WebSocket connection.
        
        Security Critical:
        - Only authenticated users can connect
        - Each user gets a personal group: notify_{user.id}
        - No cross-tenant notification access possible
        """
        user = self.scope.get("user")
        
        # Strictly reject unauthenticated connections
        if user is None or isinstance(user, AnonymousUser) or not user.is_authenticated:
            await self.close()
            return
        
        # Create strictly personal group name (no cross-user access possible)
        self.group_name = f"notify_{user.id}"
        
        try:
            # Add this connection to the user's personal notification group
            await self.channel_layer.group_add(
                self.group_name,
                self.channel_name
            )
            
            # Accept the WebSocket connection
            await self.accept()
        except Exception as e:
            # Log error and close connection
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"Failed to establish notification WebSocket for user {user.id}: {str(e)}")
            await self.close()

    async def disconnect(self, close_code):
        """
        Handle WebSocket disconnection.
        Remove the connection from the user's personal group.
        """
        if hasattr(self, 'group_name'):
            await self.channel_layer.group_discard(
                self.group_name,
                self.channel_name
            )

    async def send_notification(self, event):
        """
        Handler method to send notifications to the WebSocket.
        
        Called when a notification is sent to the user's personal group.
        The message is extracted from the event and sent to the client.
        
        Args:
            event (dict): Event data containing the notification message
        """
        try:
            message = event.get("message", {})
            
            # Send the notification to the WebSocket client
            await self.send(text_data=json.dumps(message))
        except Exception as e:
            # Log error but don't crash - connection might be closed
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"Failed to send notification via WebSocket: {str(e)}")