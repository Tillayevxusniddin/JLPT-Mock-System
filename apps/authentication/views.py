from django.db.models import Prefetch
from rest_framework import generics, status, permissions, viewsets, filters
from rest_framework.response import Response
from rest_framework.views import APIView
from django_filters.rest_framework import DjangoFilterBackend
from apps.authentication.models import User
from apps.authentication.serializers import (
    #serializers
)
from rest_framework_simplejwt.tokens import RefreshToken
from apps.core.permissions import (
    IsCenterAdminOrTeacher
)

from apps.core.throttling import (
    #throttling
)

from apps.authentication.swagger import (

)


class RegisterView(generics.CreateAPIView):
    serializer_class = RegisterSerializer
    permission_classes = [permissions.AllowAny]
    throttle_scope = "auth"

    def create(self, request, *args, **kwargs):
        from django.db import transaction

        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        with transaction.atomic():
            user = serializer.save()

        tokens = RefreshToken.for_user(user)

        #TODO: Agar role student yoki teacher boladigan bolsa registerda token berish kerak emas
        return Response({
            "access": str(tokens.access_token),
            "refresh": str(tokens),
            "user": UserSerializer(user).data,
        }, status=status.HTTP_201_CREATED)

class LoginView(APIView):
    permission_classes = [permissions.AllowAny]
    throttle_scope = "auth"

    def post(self, request):
        serializer = LoginSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        user = data["user"]

        return Response({
            "access": data["access"],
            "refresh": data["refresh"],
            "user": UserSerializer(user).data,
        })

class MeView(generics.RetrieveUpdateAPIView):
    serializer_class = UserSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_object(self):
        from apps.core.tenant_utils import with_public_schema

        user = self.request.user

        if hasattr(user, '_prefetched_objects_cache'):
            # If already prefetched, return as is
            return user

        return with_public_schema(
            lambda: User.objects.select_related('center').get(pk=user.pk)
        )
    
    def update(self, request, *args, **kwargs):
        from django.db import transaction
        
        partial = kwargs.pop('partial', True)  # ALWAYS PARTIAL UPDATE
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        
        with transaction.atomic():
            serializer.save()
        
        return Response(serializer.data)

    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)

    def put(self, request, *args, **kwargs):
        return super().put(request, *args, **kwargs)

    def patch(self, request, *args, **kwargs):
        return super().patch(request, *args, **kwargs)

class LogoutView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        try:
            token = RefreshToken(request.data.get("refresh"))
            token.blacklist()
            return Response({"detail": "Successfully logged out."}, status=status.HTTP_205_RESET_CONTENT)
        except Exception:
            return Response({"detail": "Invalid or expired token."},
                            status=status.HTTP_400_BAD_REQUEST)

class UpdatePasswordView(generics.GenericAPIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = UpdatePasswordSerializer

    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response({"detail": "Password updated successfully."}, status=status.HTTP_200_OK)

class PasswordResetRequestView(generics.CreateAPIView):
    permission_classes = [permissions.AllowAny]
    serializer_class = PasswordResetRequestSerializer

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        result = serializer.save()
        return Response(result, status=status.HTTP_200_OK)

class PasswordResetConfirmView(generics.CreateAPIView):
    permission_classes = [permissions.AllowAny]
    serializer_class = PasswordResetConfirmSerializer

class UserViewSet(viewsets.ModelViewSet):
    permission_classes = [permissions.IsAuthenticated, IsCenterAdminOrTeacher]
    serializer_class = UserManagementSerializer
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['role', 'is_active', 'is_approved']
    search_fields = ['first_name', 'last_name', 'email']
    ordering_fields = ['created_at', 'last_login', 'first_name', 'last_name', 'email']
    ordering = ['-created_at']
    queryset = User.objects.none()
    http_method_names = ['get', 'put', 'patch', 'delete', 'head', 'options'] 

    def get_serializer_class(self):
        if self.action == 'list':
            return UserListSerializer
        return UserManagementSerializer

    def get_queryset(self):
        if getattr(self, 'swagger_fake_view', False):
            return User.objects.none()
        user = self.request.user

        from apps.core.tenant_utils import set_public_schema
        set_public_schema()

        qs = User.objects.filter(center_id=user.center_id).select_related("center")

        if user.role == User.Role.CENTER_ADMIN:
            # Admin sees everyone in their center
            return qs
        elif user.role == User.Role.TEACHER:
            from apps.core.tenant_utils import schema_context
            from apps.groups.models import GroupMembership

            student_user_ids = []
            if user.center_id:
                from apps.centers.models import Center
                from apps.core.tenant_utils import set_public_schema

                set_public_schema()
                try:
                    center = Center.objects.get(id=user.center_id)
                    schema_name = center.schema_name
                except Center.DoesNotExist:
                    schema_name = None

                if schema_name:
                    with schema_context(schema_name):
                        from apps.groups.models import GroupMembership

                        my_teaching_group_ids = list(
                            GroupMembership.objects.filter(
                                user_id=user.id,
                                role_in_group="TEACHER"
                            ).values_list('group_id', flat=True)
                        )

                        if my_teaching_group_ids:
                            student_user_ids = list(
                                GroupMembership.objects.filter(
                                    group_id__in=my_teaching_group_ids,
                                    role_in_group="STUDENT"
                                ).values_list('user_id', flat=True).distinct()
                            )

                    return qs.filter(
                        id__in=student_user_ids if student_user_ids else [],
                        role=User.Role.STUDENT
                    ).distinct()

                return User.objects.none()

class UserAvatarUploadView(generics.UpdateAPIView):
    serializer_class = UserSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_object(self):
        return self.request.user

    def update(self, request, *args, **kwargs):
        user = self.get_object()

        if 'avatar' not in request.FILES:
            return Response(
                {'avatar': ['No avatar file provided.']},
                status=status.HTTP_400_BAD_REQUEST
            )

        if user.avatar:
            try:
                user.avatar.delete(save=False)
            except Exception:
                # Continue even if deletion fails (old file might not exist)
                logger.error(f"Failed to delete avatar for user {user.id}: {str(e)}")
                pass

        user.avatar = request.FILES['avatar']
        user.save(update_fields=['avatar'])
        serializer = self.get_serializer(user)

        return Response(serializer.data, status=status.HTTP_200_OK)


        

    
    





                






        





