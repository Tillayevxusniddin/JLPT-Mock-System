# apps/attempts/permissions.py

from rest_framework import permissions
from rest_framework.exceptions import PermissionDenied
from .models import Submission


class IsSubmissionOwnerOrTeacher(permissions.BasePermission):
    """
    Permission class for Submission access.
    
    Rules:
    - OWNER: FORBIDDEN (403) - Cannot access tenant-specific content
    - CENTER_ADMIN: Full access to all submissions
    - TEACHER: Can access submissions for their groups
    - STUDENT: Can only access their own submissions
    - GUEST: Can only access their own submissions
    """
    message = "You do not have permission to perform this action."

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False

        user = request.user

        # OWNER is FORBIDDEN
        if user.role == "OWNER":
            raise PermissionDenied(
                detail="Owners cannot access tenant-specific submission content."
            )

        return True

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
                detail="Owners cannot access tenant-specific submission content."
            )

        # CENTER_ADMIN: Full access
        if user.role == "CENTER_ADMIN":
            return True

        # STUDENT/GUEST: Only their own submissions
        if user.role in ("STUDENT", "GUEST"):
            return obj.user_id == user.id

        # TEACHER: Submissions for their groups
        if user.role == "TEACHER":
            from apps.groups.models import GroupMembership
            
            # Get groups where this teacher teaches
            teaching_group_ids = GroupMembership.objects.filter(
                user_id=user.id,
                role_in_group="TEACHER"
            ).values_list('group_id', flat=True)
            
            if not teaching_group_ids:
                return False
            
            # Check if submission's assignment is assigned to any of these groups
            if obj.exam_assignment:
                return obj.exam_assignment.assigned_groups.filter(
                    id__in=teaching_group_ids
                ).exists()
            elif obj.homework_assignment:
                return obj.homework_assignment.assigned_groups.filter(
                    id__in=teaching_group_ids
                ).exists()
            
            return False

        return False


class CanStartExam(permissions.BasePermission):
    """
    Permission to check if a student can start an exam.
    
    Rules:
    - ExamAssignment.status must be OPEN
    - User must not have already completed the exam
    """
    message = "You cannot start this exam."

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False

        user = request.user

        # Only students can start exams
        if user.role not in ("STUDENT", "GUEST"):
            return False

        # Check exam_assignment_id from request
        exam_assignment_id = request.data.get('exam_assignment_id') or request.query_params.get('exam_assignment_id')
        
        if not exam_assignment_id:
            # Will be validated in the view
            return True

        try:
            from apps.assignments.models import ExamAssignment
            exam_assignment = ExamAssignment.objects.get(id=exam_assignment_id)
        except ExamAssignment.DoesNotExist:
            return False

        # Check if exam is OPEN
        if exam_assignment.status != ExamAssignment.RoomStatus.OPEN:
            raise PermissionDenied(
                detail=f"Exam is not open. Current status: {exam_assignment.status}"
            )

        # Check if user already completed
        completed_submission = Submission.objects.filter(
            user_id=user.id,
            exam_assignment=exam_assignment,
            status__in=[Submission.Status.SUBMITTED, Submission.Status.GRADED]
        ).exists()

        if completed_submission:
            raise PermissionDenied(
                detail="You have already completed this exam. Each exam can only be attempted once."
            )

        return True
