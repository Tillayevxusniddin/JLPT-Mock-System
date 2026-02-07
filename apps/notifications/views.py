# apps/notifications/views.py
"""
Thin ViewSet for notifications. WebSocket flow, CRUD, and examples
are documented in apps/notifications/swagger.py.
"""
from django.utils import timezone
from rest_framework import viewsets, permissions, status, mixins
from rest_framework.decorators import action
from rest_framework.response import Response

from .models import Notification
from .serializers import NotificationSerializer
from .swagger import notification_viewset_schema


@notification_viewset_schema
class NotificationViewSet(
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.UpdateModelMixin,
    viewsets.GenericViewSet,
):
    serializer_class = NotificationSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return Notification.objects.none()
        user = self.request.user
        if not user or not user.is_authenticated:
            return Notification.objects.none()
        return Notification.objects.filter(user_id=user.id).order_by("-created_at")

    def update(self, request, *args, **kwargs):
        return self.partial_update(request, *args, **kwargs)

    def partial_update(self, request, *args, **kwargs):
        instance = self.get_object()
        allowed = {"is_read"}
        if not isinstance(request.data, dict) or not allowed.intersection(request.data):
            return Response(
                {"detail": "Only 'is_read' field can be updated."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if set(request.data.keys()) - allowed:
            return Response(
                {"detail": "Only 'is_read' field can be updated."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        instance.is_read = bool(request.data.get("is_read"))
        instance.save(update_fields=["is_read", "updated_at"])
        return Response(self.get_serializer(instance).data)

    @action(detail=False, methods=["post"], url_path="mark-all-read")
    def mark_all_read(self, request):
        if not request.user or not request.user.is_authenticated:
            return Response(
                {"detail": "Authentication required."},
                status=status.HTTP_401_UNAUTHORIZED,
            )
        qs = self.get_queryset().filter(is_read=False)
        updated = qs.update(is_read=True, updated_at=timezone.now())
        return Response({"updated": updated}, status=status.HTTP_200_OK)