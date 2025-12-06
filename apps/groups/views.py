from rest_framework import viewsets, status, permissions
from rest_framework.decorators import action
from rest_framework.response import Response
from django.shortcuts import get_object_or_404
from django.contrib.auth import get_user_model

from apps.core.throttling import GroupOperationThrottle
from .models import Group, GroupTeacher, GroupMembership
from .serializers import (
    GroupListSerializer, GroupDetailSerializer, 
    GroupCreateSerializer, AddMemberSerializer
)

User = get_user_model()

class IsCenterAdminOrReadOnly(permissions.BasePermission):
    """
    DEPRECATED: Use GroupPermission instead.
    This permission class has security flaws.
    """
    def has_permission(self, request, view):
        if request.method in permissions.SAFE_METHODS:
            return True
        return request.user.role == 'CENTERADMIN'


class GroupPermission(permissions.BasePermission):
    """
    ✅ Secure permission class for Group operations with proper tenant isolation.
    
    Rules:
    - OWNER: No access to tenant data (only manages organizations)
    - CENTERADMIN: Full access (create, update, delete groups)
    - TEACHER: Read access to assigned groups only
    - STUDENT: Read access to enrolled groups only
    """
    
    def has_permission(self, request, view):
        """Check view-level permissions"""
        user = request.user
        
        # ✅ OWNER should never access tenant data
        if user.role == 'OWNER':
            return False
        
        # ✅ Authenticated users can list/retrieve
        if view.action in ['list', 'retrieve']:
            return True
        
        # ✅ Only CENTERADMIN can create/update/delete
        if view.action in ['create', 'update', 'partial_update', 'destroy', 'add_member', 'remove_member']:
            return user.role == 'CENTERADMIN'
        
        return False
    
    def has_object_permission(self, request, view, obj):
        """Check object-level permissions for specific group"""
        user = request.user
        
        # ✅ OWNER should never access tenant objects
        if user.role == 'OWNER':
            return False
        
        # ✅ CENTERADMIN has full access
        if user.role == 'CENTERADMIN':
            return True
        
        # ✅ TEACHER can only view groups they teach
        if user.role == 'TEACHER':
            return obj.teacher_assignments.filter(teacher_id=user.id).exists()
        
        # ✅ STUDENT can only view groups they're enrolled in
        if user.role == 'STUDENT':
            return obj.memberships.filter(student_id=user.id, status='ACTIVE').exists()
        
        return False

class GroupViewSet(viewsets.ModelViewSet):
    """
    Guruhlarni boshqarish (Tenant Schema ichida)
    
    ✅ Uses GroupPermission for proper tenant isolation and role-based access
    ✅ Rate limited to prevent abuse (100 operations/hour)
    """
    permission_classes = [permissions.IsAuthenticated, GroupPermission]
    throttle_classes = [GroupOperationThrottle]
    
    def get_queryset(self):
        # Har bir user faqat o'ziga aloqador guruhlarni ko'radi
        user = self.request.user
        
        if user.role == 'CENTERADMIN':
            return Group.objects.all()
        
        if user.role == 'TEACHER':
            # Teacher faqat o'zi dars beradigan guruhlarni ko'radi
            return Group.objects.filter(teacher_assignments__teacher_id=user.id)
            
        if user.role == 'STUDENT':
            # Student faqat o'zi o'qiydigan guruhlarni ko'radi
            return Group.objects.filter(memberships__student_id=user.id, memberships__status='ACTIVE')
            
        return Group.objects.none()

    def get_serializer_class(self):
        if self.action == 'list':
            return GroupListSerializer
        if self.action in ['create', 'update', 'partial_update']:
            return GroupCreateSerializer
        return GroupDetailSerializer

    @action(detail=True, methods=['post'], permission_classes=[permissions.IsAuthenticated, GroupPermission])
    def add_member(self, request, pk=None):
        """
        Guruhga a'zo qo'shish (Teacher yoki Student)
        
        ✅ Capacity validation for students
        ✅ Row-level locking to prevent race conditions
        ✅ Proper feedback for duplicate additions
        """
        from django.db import transaction
        
        # Lock the group row to prevent race conditions
        with transaction.atomic():
            group = Group.objects.select_for_update().get(pk=pk)
            serializer = AddMemberSerializer(data=request.data, context={'request': request})
            
            if not serializer.is_valid():
                return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
            
            user_id = serializer.validated_data['user_id']
            role = serializer.validated_data['role']
            
            if role == 'TEACHER':
                teacher, created = GroupTeacher.objects.get_or_create(
                    group=group, 
                    teacher_id=user_id,
                    defaults={'is_primary': serializer.validated_data.get('is_primary', False)}
                )
                
                if not created:
                    return Response(
                        {'status': 'Teacher already assigned to this group'},
                        status=status.HTTP_200_OK
                    )
                
                return Response({'status': 'Teacher added successfully'}, status=status.HTTP_201_CREATED)
                
            else:  # STUDENT
                # ✅ Check capacity before adding student
                if group.student_count >= group.max_students:
                    return Response(
                        {'error': f'Group capacity reached. Maximum students: {group.max_students}'},
                        status=status.HTTP_400_BAD_REQUEST
                    )
                
                membership, created = GroupMembership.objects.get_or_create(
                    group=group, 
                    student_id=user_id
                )
                
                if not created:
                    return Response(
                        {'status': 'Student already in this group'},
                        status=status.HTTP_200_OK
                    )
                
                # Update cached student count
                group.student_count = group.memberships.filter(status='ACTIVE').count()
                group.save()
                
                return Response({'status': 'Student added successfully'}, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['post'], permission_classes=[permissions.IsAuthenticated, GroupPermission])
    def remove_member(self, request, pk=None):
        """Guruhdan a'zoni chiqarish"""
        group = self.get_object()
        user_id = request.data.get('user_id')
        
        # Teacher o'chirish
        deleted_teacher, _ = GroupTeacher.objects.filter(group=group, teacher_id=user_id).delete()
        
        # Student o'chirish
        deleted_student, _ = GroupMembership.objects.filter(group=group, student_id=user_id).delete()
        
        if deleted_student:
            group.student_count = group.memberships.filter(status='ACTIVE').count()
            group.save()
            
        if deleted_teacher or deleted_student:
            return Response({'status': 'Member removed'}, status=status.HTTP_200_OK)
            
        return Response({'error': 'Member not found'}, status=status.HTTP_404_NOT_FOUND)