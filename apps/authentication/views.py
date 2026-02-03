# apps/authentication/views.py
"""
Authentication API views for multi-tenant JLPT system.

- Auth endpoints use throttle_scope; Axes tracks login failures.
- OpenAPI schemas are defined in apps.authentication.swagger; views are thin.
"""
import logging

from django.db import transaction
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import generics, permissions, status, viewsets, filters
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.exceptions import InvalidToken, TokenError
from rest_framework_simplejwt.tokens import RefreshToken

from apps.authentication.models import User
from apps.authentication.serializers import (
    get_center_avatars_batch,
    LoginSerializer,
    LogoutRequestSerializer,
    PasswordResetConfirmSerializer,
    PasswordResetRequestSerializer,
    RegisterSerializer,
    UpdatePasswordSerializer,
    UserCreateSerializer,
    UserListSerializer,
    UserManagementSerializer,
    UserSerializer,
)
from apps.authentication.swagger import (
    avatar_upload_schema,
    login_schema,
    logout_schema,
    me_schema_view,
    password_reset_confirm_schema,
    password_reset_request_schema,
    register_schema,
    update_password_schema,
    user_viewset_schema,
)
from apps.core.permissions import IsCenterAdminOrTeacher

logger = logging.getLogger(__name__)


@register_schema
class RegisterView(generics.CreateAPIView):
    serializer_class = RegisterSerializer
    permission_classes = [permissions.AllowAny]
    throttle_scope = "auth"

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        with transaction.atomic():
            user = serializer.save()
        return Response(
            {
                "detail": "Registration successful. Please wait for center administrator approval.",
                "email": user.email,
                "role": user.role,
            },
            status=status.HTTP_201_CREATED,
        )


@login_schema
class LoginView(APIView):
    permission_classes = [permissions.AllowAny]
    throttle_scope = "auth"

    def post(self, request):
        serializer = LoginSerializer(
            data=request.data,
            context={"request": request},
        )
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        user = data["user"]
        return Response({
            "access": data["access"],
            "refresh": data["refresh"],
            "user": UserSerializer(user).data,
        })


@me_schema_view
class MeView(generics.RetrieveUpdateAPIView):
    serializer_class = UserSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_object(self):
        from apps.core.tenant_utils import with_public_schema

        user = self.request.user
        if hasattr(user, "_prefetched_objects_cache"):
            return user
        return with_public_schema(
            lambda: User.objects.select_related("center").get(pk=user.pk)
        )

    def update(self, request, *args, **kwargs):
        partial = kwargs.pop("partial", True)
        instance = self.get_object()
        serializer = self.get_serializer(
            instance,
            data=request.data,
            partial=partial,
        )
        serializer.is_valid(raise_exception=True)
        with transaction.atomic():
            serializer.save()
        return Response(serializer.data)


@logout_schema
class LogoutView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        refresh = request.data.get("refresh")
        if not refresh:
            return Response(
                {"detail": "Refresh token is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            token = RefreshToken(refresh)
            token.blacklist()
            return Response(
                {"detail": "Successfully logged out."},
                status=status.HTTP_205_RESET_CONTENT,
            )
        except (TokenError, InvalidToken, Exception):
            return Response(
                {"detail": "Invalid or expired token."},
                status=status.HTTP_400_BAD_REQUEST,
            )


@update_password_schema
class UpdatePasswordView(generics.GenericAPIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = UpdatePasswordSerializer

    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(
            {"detail": "Password updated successfully."},
            status=status.HTTP_200_OK,
        )


@password_reset_request_schema
class PasswordResetRequestView(generics.CreateAPIView):
    permission_classes = [permissions.AllowAny]
    serializer_class = PasswordResetRequestSerializer
    throttle_scope = "password_reset"

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        result = serializer.save()
        return Response(result, status=status.HTTP_200_OK)


@password_reset_confirm_schema
class PasswordResetConfirmView(generics.CreateAPIView):
    permission_classes = [permissions.AllowAny]
    serializer_class = PasswordResetConfirmSerializer
    throttle_scope = "password_reset"


@user_viewset_schema
class UserViewSet(viewsets.ModelViewSet):
    permission_classes = [permissions.IsAuthenticated, IsCenterAdminOrTeacher]
    serializer_class = UserManagementSerializer
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ["role", "is_active", "is_approved"]
    search_fields = ["first_name", "last_name", "email"]
    ordering_fields = ["created_at", "last_login", "first_name", "last_name", "email"]
    ordering = ["-created_at"]
    queryset = User.objects.none()
    http_method_names = ["get", "post", "put", "patch", "delete", "head", "options"]

    def get_serializer_class(self):
        if self.action == "create":
            return UserCreateSerializer
        if self.action == "list":
            return UserListSerializer
        return UserManagementSerializer

    def list(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())
        page = self.paginate_queryset(queryset)
        if page is not None:
            users = list(page)
        else:
            users = list(queryset)
        center_ids = [u.center_id for u in users if getattr(u, "center_id", None)]
        center_avatar_map = get_center_avatars_batch(center_ids) if center_ids else {}
        serializer = self.get_serializer(
            page if page is not None else users,
            many=True,
            context={
                **self.get_serializer_context(),
                "center_avatar_map": center_avatar_map,
            },
        )
        if page is not None:
            return self.get_paginated_response(serializer.data)
        return Response(serializer.data)

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return User.objects.none()
        user = self.request.user
        if not user.center_id:
            return User.objects.none()
        from apps.core.tenant_utils import set_public_schema

        set_public_schema()
        qs = User.objects.filter(center_id=user.center_id).select_related("center")
        if user.role == User.Role.CENTER_ADMIN:
            return qs
        if user.role == User.Role.TEACHER:
            from apps.centers.models import Center
            from apps.core.tenant_utils import schema_context
            from apps.groups.models import GroupMembership

            student_user_ids = []
            try:
                center = Center.objects.get(id=user.center_id)
                schema_name = center.schema_name
                if schema_name:
                    with schema_context(schema_name):
                        my_teaching_group_ids = list(
                            GroupMembership.objects.filter(
                                user_id=user.id,
                                role_in_group="TEACHER",
                            ).values_list("group_id", flat=True)
                        )
                        if my_teaching_group_ids:
                            student_user_ids = list(
                                GroupMembership.objects.filter(
                                    group_id__in=my_teaching_group_ids,
                                    role_in_group="STUDENT",
                                ).values_list("user_id", flat=True).distinct()
                            )
            except Exception:
                return User.objects.none()
            return qs.filter(
                id__in=student_user_ids or [],
                role__in=[User.Role.STUDENT, User.Role.GUEST],
            ).distinct()
        return User.objects.none()

    def check_permissions(self, request):
        super().check_permissions(request)
        if request.user.role == User.Role.TEACHER and self.action not in ("list", "retrieve"):
            from rest_framework.exceptions import PermissionDenied
            raise PermissionDenied("Teachers are only allowed to view students.")


@avatar_upload_schema
class UserAvatarUploadView(generics.UpdateAPIView):
    serializer_class = UserSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_object(self):
        return self.request.user

    def update(self, request, *args, **kwargs):
        user = self.get_object()
        if "avatar" not in request.FILES:
            return Response(
                {"avatar": ["No avatar file provided."]},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if user.avatar:
            try:
                user.avatar.delete(save=False)
            except Exception as e:
                logger.exception("Failed to delete avatar for user %s: %s", user.id, e)
        user.avatar = request.FILES["avatar"]
        user.save(update_fields=["avatar"])
        serializer = self.get_serializer(user)
        return Response(serializer.data, status=status.HTTP_200_OK)
