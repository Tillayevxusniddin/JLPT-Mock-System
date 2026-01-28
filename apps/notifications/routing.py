#apps/notifications/routing.py
from django.urls import re_path
from apps.notifications.consumers import NotificationConsumer

# WebSocket URL patterns for notifications
# Security Note: No user IDs in URLs to prevent IDOR attacks
# User identity is determined from the session/token, not the URL
websocket_urlpatterns = [
    re_path(r"^ws/notifications/$", NotificationConsumer.as_asgi()),
]