# apps/centers/views.py
"""
Centers app API views. OpenAPI schemas live in apps.centers.swagger.
"""
from django.db.models import Prefetch, Q, Count
from django_filters import FilterSet
import django_filters as filters_module
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import generics, permissions, status, filters, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.authentication.models import User
from apps.centers.serializers import (
    CenterAdminCreateSerializer,
    CenterAdminDetailSerializer,
    CenterAdminListSerializer,
    CenterAdminUpdateSerializer,
    CenterSerializer,
    ContactRequestCreateSerializer,
    ContactRequestListSerializer,
    ContactRequestUpdateSerializer,
    GuestListSerializer,
    GuestUpgradeSerializer,
    InvitationApproveSerializer,
    InvitationCreateSerializer,
    InvitationDetailSerializer,
    OwnerCenterListSerializer,
    OwnerCenterSerializer,
)
from apps.centers.swagger import (
    center_admin_center_viewset_schema,
    center_admin_create_schema,
    center_avatar_upload_schema,
    center_create_schema,
    contact_request_create_schema,
    guest_list_schema,
    guest_upgrade_schema,
    invitation_approve_schema,
    invitation_create_schema,
    invitation_list_schema,
    owner_center_admin_viewset_schema,
    owner_center_viewset_schema,
    owner_contact_request_viewset_schema,
)
from apps.core.permissions import IsCenterAdmin, IsOwner
from apps.core.tenant_utils import set_public_schema

try:
    from apps.centers.models import Center, ContactRequest, Invitation
except Exception:  # pragma: no cover
    Center = None
    ContactRequest = None
    Invitation = None


# ---- Invitations (Center Admin) ----


@invitation_create_schema
class InvitationCreateView(generics.CreateAPIView):
    serializer_class = InvitationCreateSerializer
    permission_classes = [permissions.IsAuthenticated, IsCenterAdmin]
    queryset = Invitation.objects.none()

    def get_queryset(self):
        if getattr(self, 'swagger_fake_view', False):
            return Invitation.objects.none()
        return Invitation.objects.filter(center_id=self.request.user.center_id)

    def create(self, request, *args, **kwargs):
        set_public_schema()
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        result = serializer.save()
        
        # Handle single vs list return (bulk create)
        is_list = isinstance(result, list)
        output_serializer = InvitationDetailSerializer(result, many=is_list)
        headers = self.get_success_headers(output_serializer.data)
        return Response(output_serializer.data, status=status.HTTP_201_CREATED, headers=headers)

class InvitationFilter(FilterSet):
    is_used = filters_module.BooleanFilter(method='filter_is_used')
    
    def filter_is_used(self, queryset, name, value):
        if value:
            return queryset.filter(target_user__isnull=False)
        return queryset.filter(target_user__isnull=True)
    
    class Meta:
        model = Invitation
        fields = ['role', 'status']

@invitation_list_schema
class InvitationListView(generics.ListAPIView):
    serializer_class = InvitationDetailSerializer
    permission_classes = [permissions.IsAuthenticated, IsCenterAdmin]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_class = InvitationFilter
    search_fields = ['code']
    ordering_fields = ['created_at', 'expires_at']
    ordering = ['-created_at']
    queryset = Invitation.objects.none()

    def get_queryset(self):
        set_public_schema()
        if getattr(self, 'swagger_fake_view', False):
            return Invitation.objects.none()
        
        user = self.request.user
        return Invitation.objects.filter(center_id=user.center_id).order_by("-created_at")

@invitation_approve_schema
class InvitationApproveView(generics.GenericAPIView):
    serializer_class = InvitationApproveSerializer
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        set_public_schema()
        serializer = self.get_serializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        user_name = f"{user.first_name} {user.last_name}"
        return Response({"detail": f"{user_name} approved by Center Admin."}, status=status.HTTP_200_OK)


# ---- Owner: Centers ----


@center_create_schema
class CenterCreateView(generics.CreateAPIView):
    serializer_class = CenterSerializer
    permission_classes = [permissions.IsAuthenticated, IsOwner]
    
    def create(self, request, *args, **kwargs):
        set_public_schema()
        return super().create(request, *args, **kwargs)

@center_admin_create_schema
class CenterAdminCreateView(generics.GenericAPIView):
    serializer_class = CenterAdminCreateSerializer
    permission_classes = [permissions.IsAuthenticated, IsOwner]

    def post(self, request, center_id):
        from apps.core.tenant_utils import with_public_schema
        try:
            center = with_public_schema(lambda: Center.objects.get(id=center_id))
        except Center.DoesNotExist:
            return Response({"detail": "Center topilmadi."}, status=status.HTTP_404_NOT_FOUND)
            
        serializer = self.get_serializer(data=request.data, context={"request": request, "center": center})
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        return Response({"detail": "CenterAdmin yaratildi.", "user_id": str(user.id)}, status=status.HTTP_201_CREATED)

@owner_center_viewset_schema
class OwnerCenterViewSet(viewsets.ModelViewSet):
    permission_classes = [permissions.IsAuthenticated, IsOwner]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    # Changed from is_active to status
    filterset_fields = ['status', 'is_active']
    search_fields = ['name', 'description', 'address', 'email']
    ordering_fields = ['created_at', 'name']
    ordering = ['-created_at']

    def get_serializer_class(self):
        if self.action == 'list':
            return OwnerCenterListSerializer
        return OwnerCenterSerializer

    def get_queryset(self):
        set_public_schema()
        if getattr(self, 'swagger_fake_view', False):
            return Center.objects.none()
        
        if self.action == "list":
            return (
                Center.objects.all()
                .annotate(
                    teacher_count=Count("user_set", filter=Q(user_set__role="TEACHER"))
                )
                .prefetch_related(
                    Prefetch(
                        "user_set",
                        User.objects.filter(role="CENTER_ADMIN").only(
                            "id", "email", "first_name", "last_name", "center_id"
                        ),
                        to_attr="center_admins",
                    )
                )
                .order_by("-created_at")
            )
        return Center.objects.all().order_by("created_at")

    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    def retrieve(self, request, *args, **kwargs):
        return super().retrieve(request, *args, **kwargs)

    def create(self, request, *args, **kwargs):
        return super().create(request, *args, **kwargs)

    def update(self, request, *args, **kwargs):
        return super().update(request, *args, **kwargs)

    def partial_update(self, request, *args, **kwargs):
        return super().partial_update(request, *args, **kwargs)

    def destroy(self, request, *args, **kwargs):
        """
        HARD DELETE center.
        Triggers async task to remove Schema, Users, and Data.
        """
        center = self.get_object()
        center_id = center.id
        center_name = center.name
        
        # Yangi HARD DELETE taskni chaqirish
        from apps.centers.tasks import hard_delete_center
        hard_delete_center.delay(center_id=center_id)
        
        return Response({
            "status": "deletion_queued",
            "message": f"Center '{center_name}' is being permanently deleted. Users and Schema will be removed shortly.",
            "center_id": center_id
        }, status=status.HTTP_202_ACCEPTED)

    def perform_destroy(self, instance):
        pass

    @action(detail=True, methods=['post'])
    def suspend(self, request, pk=None):
        center = self.get_object()
        center.status = Center.Status.SUSPENDED
        center.is_active = False
        center.save(update_fields=['status', 'is_active', 'updated_at'])
        return Response({"status": "center suspended"}, status=status.HTTP_200_OK)

    @action(detail=True, methods=['post'])
    def activate(self, request, pk=None):
        center = self.get_object()
        center.status = Center.Status.ACTIVE
        center.is_active = True
        center.save(update_fields=['status', 'is_active', 'updated_at'])
        return Response({"status": "center activated"}, status=status.HTTP_200_OK)


@owner_center_admin_viewset_schema
class OwnerCenterAdminViewSet(viewsets.ModelViewSet):
    permission_classes = [permissions.IsAuthenticated, IsOwner]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['is_active', 'is_approved', 'center']
    # Updated to first_name/last_name
    search_fields = ['first_name', 'last_name', 'email']
    ordering_fields = ['created_at', 'last_login']
    ordering = ['-created_at']
    
    def get_queryset(self):
        if getattr(self, 'swagger_fake_view', False):
            return User.objects.none()
        
        return User.global_objects.filter(
            role="CENTER_ADMIN",
            deleted_at__isnull=True
        ).select_related('center').order_by("-created_at")

    def get_serializer_class(self):
        if self.action == 'list':
            return CenterAdminListSerializer
        elif self.action in ['create']:
            return CenterAdminCreateSerializer
        elif self.action in ['update', 'partial_update']:
            return CenterAdminUpdateSerializer
        return CenterAdminDetailSerializer
    
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)
    
    def create(self, request, *args, **kwargs):
        """Create a new CenterAdmin user."""
        from apps.core.tenant_utils import with_public_schema
        
        center_id = request.data.get('center_id') or request.data.get('center')
        if not center_id:
            return Response({"detail": "center_id is required."}, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            center = with_public_schema(lambda: Center.objects.get(id=center_id))
        except Center.DoesNotExist:
            return Response({"detail": "Center not found."}, status=status.HTTP_404_NOT_FOUND)
        
        serializer = self.get_serializer(data=request.data, context={"request": request, "center": center})
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        
        output_serializer = CenterAdminDetailSerializer(user, context={"request": request})
        return Response(output_serializer.data, status=status.HTTP_201_CREATED)
    
    def retrieve(self, request, *args, **kwargs):
        return super().retrieve(request, *args, **kwargs)

    def update(self, request, *args, **kwargs):
        return super().update(request, *args, **kwargs)

    def partial_update(self, request, *args, **kwargs):
        return super().partial_update(request, *args, **kwargs)

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        self.perform_destroy(instance)
        return Response({"message": "Center admin deleted."}, status=status.HTTP_200_OK)
    
    def perform_destroy(self, instance):
        instance.soft_delete()


# ---- Center Admin: My Center ----


@center_admin_center_viewset_schema
class CenterAdminCenterViewSet(viewsets.ModelViewSet):
    permission_classes = [permissions.IsAuthenticated, IsCenterAdmin]
    serializer_class = CenterSerializer
    http_method_names = ['get', 'put', 'patch'] 
    
    def get_queryset(self):
        if getattr(self, 'swagger_fake_view', False):
            return Center.objects.none()
        return Center.objects.filter(id=self.request.user.center_id)
    
    def get_object(self):
        set_public_schema()
        return Center.objects.get(id=self.request.user.center_id)
    
    def retrieve(self, request, *args, **kwargs):
        return super().retrieve(request, *args, **kwargs)
    
    def update(self, request, *args, **kwargs):
        return super().update(request, *args, **kwargs)
    
    def partial_update(self, request, *args, **kwargs):
        return super().partial_update(request, *args, **kwargs)


@center_avatar_upload_schema
class CenterAvatarUploadView(generics.UpdateAPIView):
    serializer_class = CenterSerializer
    permission_classes = [permissions.IsAuthenticated, IsCenterAdmin]
    
    def get_object(self):
        set_public_schema()
        user = self.request.user
        if not user.center_id:
            from rest_framework.exceptions import NotFound
            raise NotFound("You are not associated with any center.")
        return Center.objects.get(id=user.center_id)
    
    def update(self, request, *args, **kwargs):
        center = self.get_object()
        if 'avatar' not in request.FILES:
            return Response({'avatar': ['No avatar file provided.']}, status=status.HTTP_400_BAD_REQUEST)
        
        if center.avatar:
            try: center.avatar.delete(save=False)
            except: pass
        
        center.avatar = request.FILES['avatar']
        center.save(update_fields=['avatar', 'updated_at'])
        return Response(self.get_serializer(center).data, status=status.HTTP_200_OK)


# ---- Public: Contact ----


@contact_request_create_schema
class ContactRequestCreateView(generics.CreateAPIView):
    serializer_class = ContactRequestCreateSerializer
    permission_classes = [permissions.AllowAny]

@owner_contact_request_viewset_schema
class OwnerContactRequestViewSet(viewsets.ModelViewSet):
    permission_classes = [permissions.IsAuthenticated, IsOwner]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['status']
    search_fields = ['full_name', 'phone_number', 'message', 'center_name']
    ordering_fields = ['created_at', 'status']
    ordering = ['-created_at']
    http_method_names = ['get', 'patch', 'delete', 'head', 'options']
    
    def get_serializer_class(self):
        if self.action == 'list':
            return ContactRequestListSerializer
        elif self.action in ['update', 'partial_update']:
            return ContactRequestUpdateSerializer
        return ContactRequestListSerializer
    
    def get_queryset(self):
        if getattr(self, 'swagger_fake_view', False):
            return ContactRequest.objects.none()
        return ContactRequest.objects.filter(deleted_at__isnull=True).order_by('-created_at')
    
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)
    
    def retrieve(self, request, *args, **kwargs):
        return super().retrieve(request, *args, **kwargs)
    
    def update(self, request, *args, **kwargs):
        return super().update(request, *args, **kwargs)
    
    def partial_update(self, request, *args, **kwargs):
        return super().partial_update(request, *args, **kwargs)
    
    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        self.perform_destroy(instance)
        return Response({"message": "Contact request deleted."}, status=status.HTTP_200_OK)
    
    def perform_destroy(self, instance):
        instance.soft_delete()


# ---- Center Admin: Guests ----


@guest_list_schema
class GuestListView(generics.ListAPIView):
    serializer_class = GuestListSerializer
    permission_classes = [permissions.IsAuthenticated, IsCenterAdmin]
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ['email', 'first_name', 'last_name']
    ordering_fields = ['created_at', 'email']
    ordering = ['-created_at']
    
    def get_queryset(self):
        set_public_schema()
        if getattr(self, 'swagger_fake_view', False):
            return User.objects.none()
        
        user = self.request.user
        return User.objects.filter(center_id=user.center_id, role="GUEST").order_by("-created_at")



@guest_upgrade_schema
class GuestUpgradeView(generics.GenericAPIView):
    serializer_class = GuestUpgradeSerializer
    permission_classes = [permissions.IsAuthenticated, IsCenterAdmin]
    
    def post(self, request):
        set_public_schema()
        serializer = self.get_serializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        
        from apps.authentication.serializers import UserSerializer
        user_name = f"{user.first_name} {user.last_name}"
        return Response({
            "detail": f"Guest user '{user_name}' has been upgraded to STUDENT.",
            "user": UserSerializer(user).data
        }, status=status.HTTP_200_OK)