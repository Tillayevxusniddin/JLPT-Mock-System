# apps/notifications/serializers.py
"""
Notification serializers. Lightweight: no nested user object (avoids N+1).
Notifications are filtered by request.user.id in the view; no per-row user lookup.
Documented in apps/notifications/swagger.py.
"""
from rest_framework import serializers
from .models import Notification


class NotificationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Notification
        fields = [
            "id",
            "user_id",
            "notification_type",
            "message",
            "is_read",
            "link",
            "related_task_id",
            "related_submission_id",
            "related_group_id",
            "related_contact_request_id",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id", "user_id", "notification_type", "message", "link",
            "related_task_id", "related_submission_id", "related_group_id",
            "related_contact_request_id", "created_at", "updated_at",
        ]
