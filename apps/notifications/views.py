# apps/notifications/views.py
from django.utils import timezone
from rest_framework import viewsets, permissions, status
from rest_framework.decorators import action
from rest_framework.response import Response

from .models import Notification
from .serializers import NotificationSerializer


class NotificationViewSet(viewsets.ReadOnlyModelViewSet):
    """
    API for user notifications.

    - list/retrieve: read-only
    - partial_update: allow toggling is_read
    - mark_all_read: mark all unread as read

    Tenant isolation:
    - Notifications table is tenant-scoped (TenantBaseModel)
    - Queryset is filtered by request.user.id
    """

    serializer_class = NotificationSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return Notification.objects.none()

        user = self.request.user
        if not user or not user.is_authenticated:
            return Notification.objects.none()

        return (
            Notification.objects.filter(user_id=user.id)
            .order_by("-created_at")
        )

    def update(self, request, *args, **kwargs):
        """
        Restrict full update to is_read only (behaves like partial update).
        """
        return self.partial_update(request, *args, **kwargs)

    def partial_update(self, request, *args, **kwargs):
        """
        Allow patching is_read flag only.

        Example:
            PATCH /api/notifications/{id}/
            {"is_read": true}
        """
        instance = self.get_object()
        if "is_read" not in request.data:
            return Response(
                {"detail": "Only 'is_read' field can be updated."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        instance.is_read = bool(request.data.get("is_read"))
        # Optionally track read timestamp via updated_at
        instance.save(update_fields=["is_read", "updated_at"])
        serializer = self.get_serializer(instance)
        return Response(serializer.data)

    @action(detail=False, methods=["post"], url_path="mark-all-read")
    def mark_all_read(self, request):
        """
        Mark all unread notifications for the current user as read.

        POST /api/notifications/mark-all-read/
        """
        user = request.user
        if not user or not user.is_authenticated:
            return Response(
                {"detail": "Authentication required."},
                status=status.HTTP_401_UNAUTHORIZED,
            )

        qs = self.get_queryset().filter(is_read=False)
        updated = qs.update(is_read=True, updated_at=timezone.now())
        return Response(
            {"updated": updated},
            status=status.HTTP_200_OK,
        )