# apps/assignments/permissions.py

from rest_framework import permissions
from rest_framework.exceptions import PermissionDenied
from .models import ExamAssignment, HomeworkAssignment


class IsAssignmentManagerOrReadOnly(permissions.BasePermission):
    """
    Permission class for ExamAssignment and HomeworkAssignment models.
    
    Rules:
    - OWNER: FORBIDDEN (403) - Cannot access tenant-specific content
    - CENTER_ADMIN: Full CRUD - Can manage ALL assignments in the tenant
    - TEACHER: Group-Based Management
        * Can fully manage (Update/Delete) assignments that are assigned to
          Groups where this teacher is a TEACHER
    - STUDENT: Read-Only (GET)
        * Can view if assignment is assigned to one of their Groups
        * OR if their User ID is in assigned_user_ids (for Homework)
    - GUEST: Read-Only (GET)
        * Can view ONLY if their User ID is in assigned_user_ids
    """
    message = "You do not have permission to perform this action."

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False

        user = request.user

        # OWNER is FORBIDDEN from accessing tenant-specific content
        if user.role == "OWNER":
            raise PermissionDenied(
                detail="Owners cannot access tenant-specific assignment content."
            )

        # Safe methods (GET, HEAD, OPTIONS) - allow for all authenticated users
        if request.method in permissions.SAFE_METHODS:
            return True

        # Write methods (POST, PUT, PATCH, DELETE)
        # Only CENTER_ADMIN and TEACHER can create/modify
        return user.role in ("CENTER_ADMIN", "TEACHER")

    def has_object_permission(self, request, view, obj):
        """
        Check object-level permissions.
        """
        if not request.user or not request.user.is_authenticated:
            return False

        user = request.user

        # OWNER is FORBIDDEN
        if user.role == "OWNER":
            raise PermissionDenied(
                detail="Owners cannot access tenant-specific assignment content."
            )

        # Safe methods - allow based on queryset filtering (handled in ViewSet)
        if request.method in permissions.SAFE_METHODS:
            return True

        # CENTER_ADMIN: Full access
        if user.role == "CENTER_ADMIN":
            return True

        # TEACHER: Only if assignment is assigned to groups where they teach
        if user.role == "TEACHER":
            from apps.groups.models import GroupMembership
            
            # Get groups where this teacher teaches
            teaching_group_ids = GroupMembership.objects.filter(
                user_id=user.id,
                role_in_group="TEACHER"
            ).values_list('group_id', flat=True)
            
            if not teaching_group_ids:
                return False
            
            # Check if assignment is assigned to any of these groups
            if isinstance(obj, ExamAssignment):
                return obj.assigned_groups.filter(id__in=teaching_group_ids).exists()
            elif isinstance(obj, HomeworkAssignment):
                return obj.assigned_groups.filter(id__in=teaching_group_ids).exists()
            
            return False

        return False
