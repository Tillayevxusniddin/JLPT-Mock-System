# apps/assignments/views.py

from rest_framework import viewsets
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from django.db.models import Q, Prefetch
from .models import ExamAssignment, HomeworkAssignment
from .serializers import ExamAssignmentSerializer, HomeworkAssignmentSerializer
from .permissions import IsAssignmentManagerOrReadOnly
from apps.groups.models import GroupMembership


class ExamAssignmentViewSet(viewsets.ModelViewSet):
    """
    ViewSet for ExamAssignment model.
    
    Queryset Filtering:
    - Admin: Return all
    - Teacher: Return assignments where assigned_groups matches any group the teacher teaches
    - Student: Return assignments linked to their groups
    - Guest: No access (empty queryset)
    """
    serializer_class = ExamAssignmentSerializer
    permission_classes = [IsAuthenticated, IsAssignmentManagerOrReadOnly]
    queryset = ExamAssignment.objects.all()

    def get_queryset(self):
        """Filter queryset based on user role and group membership."""
        if getattr(self, 'swagger_fake_view', False):
            return ExamAssignment.objects.none()
        
        user = self.request.user
        queryset = ExamAssignment.objects.select_related('mock_test').prefetch_related(
            'assigned_groups'
        ).order_by('-created_at')
        
        # CENTER_ADMIN: See all assignments
        if user.role == "CENTER_ADMIN":
            return queryset
        
        # TEACHER: See assignments assigned to groups where they teach
        if user.role == "TEACHER":
            teaching_group_ids = GroupMembership.objects.filter(
                user_id=user.id,
                role_in_group="TEACHER"
            ).values_list('group_id', flat=True)
            
            if teaching_group_ids:
                return queryset.filter(assigned_groups__id__in=teaching_group_ids).distinct()
            else:
                return ExamAssignment.objects.none()
        
        # STUDENT: See assignments assigned to their groups
        if user.role == "STUDENT":
            student_group_ids = GroupMembership.objects.filter(
                user_id=user.id,
                role_in_group="STUDENT"
            ).values_list('group_id', flat=True)
            
            if student_group_ids:
                return queryset.filter(assigned_groups__id__in=student_group_ids).distinct()
            else:
                return ExamAssignment.objects.none()
        
        # GUEST: No access to ExamAssignments
        return ExamAssignment.objects.none()

    def list(self, request, *args, **kwargs):
        """
        Optimized list endpoint to fix N+1 schema switching for 'created_by' field.
        """
        queryset = self.filter_queryset(self.get_queryset())
        page = self.paginate_queryset(queryset)
        
        assignments = page if page is not None else queryset
        
        # Optimize N+1 for created_by
        user_ids = set()
        for assignment in assignments:
            if assignment.created_by_id:
                user_ids.add(assignment.created_by_id)
        
        user_map = {}
        if user_ids:
            from apps.core.tenant_utils import with_public_schema
            from apps.authentication.models import User
            
            def fetch_users():
                return {u.id: u for u in User.objects.filter(id__in=user_ids)}
            
            user_map = with_public_schema(fetch_users)
        
        serializer = self.get_serializer(
            assignments,
            many=True,
            context={'request': request, 'user_map': user_map}
        )
        
        if page is not None:
            return self.get_paginated_response(serializer.data)
        
        return Response(serializer.data)

    def perform_create(self, serializer):
        """Set created_by_id on create."""
        serializer.save(created_by_id=self.request.user.id)


class HomeworkAssignmentViewSet(viewsets.ModelViewSet):
    """
    ViewSet for HomeworkAssignment model.
    
    Queryset Filtering:
    - Admin: Return all
    - Teacher: Return assignments where assigned_groups matches any group the teacher teaches
    - Student: Return assignments linked to their groups OR assignments linked to their User ID
    - Guest: Return assignments linked to their User ID (via assigned_user_ids ArrayField)
    """
    serializer_class = HomeworkAssignmentSerializer
    permission_classes = [IsAuthenticated, IsAssignmentManagerOrReadOnly]
    queryset = HomeworkAssignment.objects.all()

    def get_queryset(self):
        """Filter queryset based on user role and group membership."""
        if getattr(self, 'swagger_fake_view', False):
            return HomeworkAssignment.objects.none()
        
        user = self.request.user
        queryset = HomeworkAssignment.objects.select_related('mock_test').prefetch_related(
            'assigned_groups'
        ).order_by('-deadline')
        
        # CENTER_ADMIN: See all assignments
        if user.role == "CENTER_ADMIN":
            return queryset
        
        # TEACHER: See assignments assigned to groups where they teach
        if user.role == "TEACHER":
            teaching_group_ids = GroupMembership.objects.filter(
                user_id=user.id,
                role_in_group="TEACHER"
            ).values_list('group_id', flat=True)
            
            if teaching_group_ids:
                return queryset.filter(assigned_groups__id__in=teaching_group_ids).distinct()
            else:
                return HomeworkAssignment.objects.none()
        
        # STUDENT: See assignments assigned to their groups OR their User ID
        if user.role == "STUDENT":
            student_group_ids = GroupMembership.objects.filter(
                user_id=user.id,
                role_in_group="STUDENT"
            ).values_list('group_id', flat=True)
            
            # Build query: groups OR user_id in assigned_user_ids
            query = Q()
            
            if student_group_ids:
                query |= Q(assigned_groups__id__in=student_group_ids)
            
            # Check if user_id is in assigned_user_ids ArrayField
            # PostgreSQL ArrayField lookup: contains operator
            query |= Q(assigned_user_ids__contains=[user.id])
            
            if query:
                return queryset.filter(query).distinct()
            else:
                return HomeworkAssignment.objects.none()
        
        # GUEST: See ONLY assignments where their User ID is in assigned_user_ids
        if user.role == "GUEST":
            # PostgreSQL ArrayField lookup: contains operator
            return queryset.filter(assigned_user_ids__contains=[user.id])
        
        return HomeworkAssignment.objects.none()

    def list(self, request, *args, **kwargs):
        """
        Optimized list endpoint to fix N+1 schema switching for 'created_by' field.
        """
        queryset = self.filter_queryset(self.get_queryset())
        page = self.paginate_queryset(queryset)
        
        assignments = page if page is not None else queryset
        
        # Optimize N+1 for created_by
        user_ids = set()
        for assignment in assignments:
            if assignment.created_by_id:
                user_ids.add(assignment.created_by_id)
        
        user_map = {}
        if user_ids:
            from apps.core.tenant_utils import with_public_schema
            from apps.authentication.models import User
            
            def fetch_users():
                return {u.id: u for u in User.objects.filter(id__in=user_ids)}
            
            user_map = with_public_schema(fetch_users)
        
        serializer = self.get_serializer(
            assignments,
            many=True,
            context={'request': request, 'user_map': user_map}
        )
        
        if page is not None:
            return self.get_paginated_response(serializer.data)
        
        return Response(serializer.data)

    def perform_create(self, serializer):
        """Set created_by_id on create."""
        serializer.save(created_by_id=self.request.user.id)
