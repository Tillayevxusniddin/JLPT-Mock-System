#apps/groups/views.py
from django.apps import apps
from django.db import IntegrityError
from django.db.models import Count, Q
from rest_framework import viewsets, mixins, permissions, status, filters
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.response import Response
from django_filters.rest_framework import DjangoFilterBackend

from apps.groups.models import Group, GroupMembership
from apps.groups.serializers import (
    GroupSerializer,
    GroupListSerializer,
    GroupMembershipSerializer,
    BulkGroupMembershipSerializer,
)
from apps.core.permissions import IsCenterAdmin
from apps.authentication.models import User
from apps.authentication.serializers import UserListSerializer, UserSerializer

from apps.groups.swagger import (
   #TODO: schema add 
)

class IsCenterAdminOrGroupTeacher(permissions.BasePermission):
    def has_object_permission(self, request, view, obj):
        if request.user.role == "CENTER_ADMIN":
            return True
        if request.user.role == "TEACHER":
            return GroupMembership.objects.filter(
                group=obj, 
                user_id=request.user.id, 
                role_in_group="TEACHER"
            ).exists()
        return False



class GroupViewSet(viewsets.ModelViewSet):
    serializer_class = GroupSerializer
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ['name', 'description']
    ordering_fields = ['created_at', 'name']
    ordering = ['-created_at']
    queryset = Group.objects.none()

    def get_serializer_class(self):
        if self.action == 'list':
            return GroupListSerializer
        return GroupSerializer

    def get_serializer_context(self):
        context = super().get_serializer_context()
        if self.action == 'list':
            from apps.core.tenant_utils import with_public_schema
            admin_count = with_public_schema(
                lambda: User.objects.filter(
                    center_id=self.request.user.center_id,
                    role="CENTER_ADMIN",
                    is_active=True
                ).count()
            )
            context['admin_count'] = admin_count
        return context

    def get_permissions(self):
        if self.action in ["create", "destroy"]:
            return [permissions.IsAuthenticated(), IsCenterAdmin()]
        if self.action in ["update", "partial_update"]:
            return [permissions.IsAuthenticated(), IsCenterAdminOrGroupTeacher()]
        return super().get_permissions()

    def get_queryset(self):
        if getattr(self, 'swagger_fake_view', False):
            return Group.objects.none()
        
        user = self.request.user
        if not user.center_id:
            return Group.objects.none()
        
        base_qs = Group.objects.order_by("name")
        
        if user.role == "CENTER_ADMIN":
            return base_qs
        
        if user.role == "STUDENT":
            try:
                my_group_ids = list(GroupMembership.objects.filter(
                    user_id=user.id, role_in_group="STUDENT"
                ).values_list('group_id', flat=True))
                return base_qs.filter(id__in=my_group_ids) if my_group_ids else Group.objects.none()
            except Exception:
                return Group.objects.none()
        
        if user.role == "TEACHER":
            try:
                my_group_ids = list(GroupMembership.objects.filter(
                    user_id=user.id, role_in_group="TEACHER"
                ).values_list('group_id', flat=True))
                return base_qs.filter(id__in=my_group_ids) if my_group_ids else Group.objects.none()
            except Exception:
                return Group.objects.none()
        
        return Group.objects.none()

    def perform_create(self, serializer):
        try:
            serializer.save()
        except IntegrityError as exc:
            self._handle_integrity_error(exc)

    def perform_update(self, serializer):
        try:
            serializer.save()
        except IntegrityError as exc:
            self._handle_integrity_error(exc)

    def _handle_integrity_error(self, exc: IntegrityError):
        message = str(exc).lower()
        if "unique" in message and "name" in message:
            raise ValidationError({"name": "A group with this name already exists."})
        raise ValidationError({"detail": "Database integrity error."})

    @action(detail=True, methods=["get"], url_path="members")
    def members(self, request, pk=None):
        group = self.get_object()

        member_ids = set(
            GroupMembership.objects.filter(group=group)
            .values_list('user_id', flat=True)
        )

        from apps.core.tenant_utils import with_public_schema
        
        def fetch_members():
            admin_ids = User.global_objects.filter(
                center_id=request.user.center_id, 
                role="CENTER_ADMIN", 
                is_active=True
            ).values_list('id', flat=True)

            member_ids.update(admin_ids)
            return list(User.global_objects.filter(id__in=member_ids).order_by('first_name', 'last_name'))
        
        users_list = with_public_schema(fetch_members)
        
        # 3. Pagination
        page = self.paginate_queryset(users_list)
        if page is not None:
            serializer = UserListSerializer(page, many=True, context={'request': request})
            return self.get_paginated_response(serializer.data)
        
        serializer = UserListSerializer(users_list, many=True, context={'request': request})
        return Response(serializer.data)

class GroupMembershipViewSet(mixins.CreateModelMixin,
                             mixins.DestroyModelMixin,
                             mixins.ListModelMixin,
                             viewsets.GenericViewSet):
    serializer_class = GroupMembershipSerializer
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_fields = ['role_in_group', 'group']
    ordering_fields = ['created_at', 'role_in_group']
    ordering = ['-created_at']
    queryset = GroupMembership.objects.none()

    def get_permissions(self):
        if self.action in ["create", "destroy"]:
            return [permissions.IsAuthenticated(), IsCenterAdmin()]
        return super().get_permissions()

    def get_queryset(self):
        if getattr(self, 'swagger_fake_view', False):
            return GroupMembership.objects.none()

        user = self.request.user
        base_qs = GroupMembership.objects.all()

        if user.role == "CENTER_ADMIN":
            authorized_qs = base_qs
            
        elif user.role == "TEACHER":
            my_teaching_groups = GroupMembership.objects.filter(
                user_id=user.id, role_in_group="TEACHER"
            ).values_list('group_id', flat=True)
            authorized_qs = base_qs.filter(group_id__in=my_teaching_groups)
            
        elif user.role == "STUDENT":
            my_group_ids = GroupMembership.objects.filter(
                user_id=user.id, role_in_group="STUDENT"
            ).values_list("group_id", flat=True)
            authorized_qs = base_qs.filter(group_id__in=my_group_ids) if my_group_ids else base_qs.none()
            
        else:
            return GroupMembership.objects.none()

        from uuid import UUID
        group_id = self.request.query_params.get('group_id')
        user_id = self.request.query_params.get('user_id')
        role_in_group = self.request.query_params.get('role_in_group')

        if group_id:
            try:
                UUID(group_id)
                authorized_qs = authorized_qs.filter(group_id=group_id)
            except ValueError: return GroupMembership.objects.none()

        if user_id:
            try:
                int(user_id)
                authorized_qs = authorized_qs.filter(user_id=user_id)
            except ValueError: return GroupMembership.objects.none()

        if role_in_group:
            authorized_qs = authorized_qs.filter(role_in_group=role_in_group)

        return authorized_qs.order_by('-created_at')

    def destroy(self, request, *args, **kwargs):
        instance: GroupMembership = self.get_object()

        if instance.role_in_group == "STUDENT":
            from apps.groups.utils import remove_student_from_group
            remove_student_from_group(instance.user_id, request.user, reason="REMOVED")
            return Response({"message": "Student removed."}, status=status.HTTP_200_OK)
        
        if instance.role_in_group == "TEACHER":
            instance.delete()
            return Response({"message": "Teacher removed form group."}, status=status.HTTP_200_OK)

        return Response({"detail": "Invalid role."}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=False, methods=['post'], url_path='bulk-add')
    def bulk_add(self, request):
        serializer = BulkGroupMembershipSerializer(
            data=request.data,
            context={'request': request}
        )
        serializer.is_valid(raise_exception=True)
        result = serializer.save()
        return Response(result, status=status.HTTP_201_CREATED)