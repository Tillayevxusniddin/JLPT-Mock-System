# apps/groups/views.py
"""
Groups app API views. All OpenAPI schemas, examples, and tags are defined in
apps.groups.swagger; views are thin and only apply decorators from that module.

Cross-schema: Groups/memberships live in tenant schema; user details in public schema.
List view batch-fetches all teachers from public schema (teacher_map) to avoid N+1.
"""
from django.db import IntegrityError
from django.db.models import Q
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import mixins, permissions, status, filters, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.response import Response

from apps.authentication.models import User
from apps.authentication.serializers import get_center_avatars_batch, UserListSerializer
from apps.groups.models import GroupMembership as GM
from apps.core.permissions import IsCenterAdmin
from apps.groups.models import Group, GroupMembership
from apps.groups.serializers import (
    BulkGroupMembershipSerializer,
    GroupListSerializer,
    GroupMembershipSerializer,
    GroupSerializer,
)
from apps.groups.swagger import (
    group_membership_viewset_schema,
    group_viewset_schema,
)

class IsCenterAdminOrGroupTeacher(permissions.BasePermission):
    def has_object_permission(self, request, view, obj):
        if request.user.role == User.Role.CENTERADMIN:
            return True
        if request.user.role == User.Role.TEACHER:
            return GroupMembership.objects.filter(
                group=obj, 
                user_id=request.user.id, 
                role_in_group=GM.ROLE_TEACHER
            ).exists()
        return False

@group_viewset_schema
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
                    role=User.Role.CENTERADMIN,
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
        
        if user.role == User.Role.CENTERADMIN:
            return base_qs
        
        if user.role == User.Role.STUDENT:
            try:
                my_group_ids = list(GroupMembership.objects.filter(
                    user_id=user.id, role_in_group=GM.ROLE_STUDENT
                ).values_list('group_id', flat=True))
                return base_qs.filter(id__in=my_group_ids) if my_group_ids else Group.objects.none()
            except Exception:
                return Group.objects.none()
        
        if user.role == User.Role.TEACHER:
            try:
                my_group_ids = list(GroupMembership.objects.filter(
                    user_id=user.id, role_in_group=GM.ROLE_TEACHER
                ).values_list('group_id', flat=True))
                return base_qs.filter(id__in=my_group_ids) if my_group_ids else Group.objects.none()
            except Exception:
                return Group.objects.none()
        
        return Group.objects.none()

    def retrieve(self, request, *args, **kwargs):
        """Get single group with optimized teacher_map to prevent N+1 queries."""
        instance = self.get_object()
        
        # Fetch teacher data in single batch (same optimization as list())
        teacher_map = {}
        teacher_ids = list(
            GroupMembership.objects.filter(
                group_id=instance.id,
                role_in_group=GM.ROLE_TEACHER
            ).values_list('user_id', flat=True)
        )
        
        if teacher_ids:
            from apps.core.tenant_utils import with_public_schema
            from apps.authentication.serializers import SimpleUserSerializer
            
            def fetch_teachers():
                users = User.objects.filter(id__in=teacher_ids)
                return {user.id: SimpleUserSerializer(user).data for user in users}
            
            user_data_map = with_public_schema(fetch_teachers)
            teacher_map[str(instance.id)] = [
                user_data_map[uid] for uid in teacher_ids if uid in user_data_map
            ]
        
        context = self.get_serializer_context()
        context['teacher_map'] = teacher_map
        serializer = self.get_serializer(instance, context=context)
        return Response(serializer.data)

    def list(self, request, *args, **kwargs):
        # Teacher details are batch-fetched from public schema (teacher_map) and
        # passed to GroupListSerializer context; see swagger GROUPS_LIST_DESCRIPTION.
        queryset = self.filter_queryset(self.get_queryset())
        
        # Paginate first
        page = self.paginate_queryset(queryset)
        groups_to_serialize = page if page is not None else queryset
        
        # OPTIMIZATION: Pre-fetch all teachers in one go
        teacher_map = {}
        if groups_to_serialize:
            # Step 1: Collect all teacher IDs from ALL groups (in tenant schema)
            group_ids = [group.id for group in groups_to_serialize]
            teacher_memberships = GroupMembership.objects.filter(
                group_id__in=group_ids,
                role_in_group=GM.ROLE_TEACHER
            ).values('group_id', 'user_id')
            
            # Build mapping: {group_id: [teacher_id1, teacher_id2, ...]}
            group_teacher_ids = {}
            all_teacher_ids = set()
            for membership in teacher_memberships:
                group_id = membership['group_id']
                user_id = membership['user_id']
                if group_id not in group_teacher_ids:
                    group_teacher_ids[group_id] = []
                group_teacher_ids[group_id].append(user_id)
                all_teacher_ids.add(user_id)
            
            # Step 2: Fetch all teacher User objects from PUBLIC schema (ONCE!)
            if all_teacher_ids:
                from apps.core.tenant_utils import with_public_schema
                from apps.authentication.serializers import SimpleUserSerializer
                
                def fetch_all_teachers():
                    users = User.objects.filter(id__in=all_teacher_ids)
                    return {user.id: SimpleUserSerializer(user).data for user in users}
                
                user_data_map = with_public_schema(fetch_all_teachers)
                
                # Step 3: Build final map: {group_id: [serialized_teacher1, serialized_teacher2, ...]}
                for group_id, teacher_ids in group_teacher_ids.items():
                    teacher_map[str(group_id)] = [
                        user_data_map[tid] for tid in teacher_ids if tid in user_data_map
                    ]
        
        context = self.get_serializer_context()
        context["teacher_map"] = teacher_map
        serializer = self.get_serializer(
            groups_to_serialize,
            many=True,
            context=context,
        )
        
        if page is not None:
            return self.get_paginated_response(serializer.data)
        
        return Response(serializer.data)


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
                role=User.Role.CENTERADMIN,
                is_active=True
            ).values_list('id', flat=True)

            member_ids.update(admin_ids)
            return list(User.global_objects.filter(id__in=member_ids).order_by('first_name', 'last_name'))
        
        users_list = with_public_schema(fetch_members)
        
        # Batch-fetch center avatars to avoid N+1 in UserListSerializer
        center_ids = [u.center_id for u in users_list if getattr(u, "center_id", None)]
        center_avatar_map = get_center_avatars_batch(center_ids) if center_ids else {}

        # 3. Pagination
        page = self.paginate_queryset(users_list)
        if page is not None:
            serializer = UserListSerializer(
                page,
                many=True,
                context={"request": request, "center_avatar_map": center_avatar_map},
            )
            return self.get_paginated_response(serializer.data)

        serializer = UserListSerializer(
            users_list,
            many=True,
            context={"request": request, "center_avatar_map": center_avatar_map},
        )
        return Response(serializer.data)

@group_membership_viewset_schema
class GroupMembershipViewSet(
    mixins.CreateModelMixin,
    mixins.DestroyModelMixin,
    mixins.ListModelMixin,
    viewsets.GenericViewSet,
):
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

        if user.role == User.Role.CENTERADMIN:
            authorized_qs = base_qs
            
        elif user.role == User.Role.TEACHER:
            my_teaching_groups = GroupMembership.objects.filter(
                user_id=user.id, role_in_group=GM.ROLE_TEACHER
            ).values_list('group_id', flat=True)
            authorized_qs = base_qs.filter(group_id__in=my_teaching_groups)
            
        elif user.role == User.Role.STUDENT:
            my_group_ids = GroupMembership.objects.filter(
                user_id=user.id, role_in_group=GM.ROLE_STUDENT
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
        from apps.groups.utils import record_membership_removal_and_delete

        instance: GroupMembership = self.get_object()
        record_membership_removal_and_delete(instance, reason="REMOVED")
        role_label = "Student" if instance.role_in_group == GM.ROLE_STUDENT else "Teacher"
        return Response(
            {"message": f"{role_label} removed from group."},
            status=status.HTTP_200_OK,
        )

    @action(detail=False, methods=['post'], url_path='bulk-add')
    def bulk_add(self, request):
        serializer = BulkGroupMembershipSerializer(
            data=request.data,
            context={'request': request}
        )
        serializer.is_valid(raise_exception=True)
        result = serializer.save()
        return Response(result, status=status.HTTP_201_CREATED)