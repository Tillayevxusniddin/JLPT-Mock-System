# apps/mock_tests/permissions.py

from rest_framework import permissions
from rest_framework.exceptions import PermissionDenied
from .models import MockTest, TestSection, QuestionGroup, Question, Quiz, QuizQuestion

class IsMockTestAdminOrTeacherOrReadOnly(permissions.BasePermission):
    """
    Permission class for MockTest and related models.
    
    Rules:
    - OWNER: FORBIDDEN (403) - Cannot access tenant-specific content
    - CENTER_ADMIN: Full access (Create, Read, Update, Delete)
    - TEACHER: 
        * Create: Can create MockTests
        * Read: Can see all MockTests in tenant
        * Update/Delete: Only if created_by_id matches user ID
    - STUDENT & GUEST: Read-only (GET, HEAD, OPTIONS)
    """
    message = "You do not have permission to perform this action."

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False

        user = request.user

        # OWNER is FORBIDDEN from accessing tenant-specific content
        if user.role == "OWNER":
            raise PermissionDenied(
                detail="Owners cannot access tenant-specific mock test content."
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
        For MockTest: Check if user is admin or creator (for teachers).
        For child objects: Check parent MockTest permissions.
        """
        if not request.user or not request.user.is_authenticated:
            return False

        user = request.user

        # OWNER is FORBIDDEN
        if user.role == "OWNER":
            raise PermissionDenied(
                detail="Owners cannot access tenant-specific mock test content."
            )

        # Safe methods - allow for all authenticated users
        if request.method in permissions.SAFE_METHODS:
            return True

        # For write operations, get the parent MockTest
        mock_test = self._get_parent_mock_test(obj)

        # CENTER_ADMIN: Full access
        if user.role == "CENTER_ADMIN":
            return True

        # TEACHER: Check ownership
        if user.role == "TEACHER":
            # For Quiz and QuizQuestion, check their own created_by_id
            from .models import Quiz, QuizQuestion
            if isinstance(obj, (Quiz, QuizQuestion)):
                if not obj.created_by_id:
                    return False
                return obj.created_by_id == user.id
            
            # For MockTest and its children, check MockTest's created_by_id
            if mock_test:
                if not mock_test.created_by_id:
                    return False
                
                # Handle type mismatch: created_by_id is UUIDField but User.id is BigAutoField
                # Compare by converting both to strings or integers
                try:
                    created_by_id = mock_test.created_by_id
                    user_id = user.id
                    
                    # Try direct comparison first
                    if created_by_id == user_id:
                        return True
                    
                    # Try string comparison
                    if str(created_by_id) == str(user_id):
                        return True
                    
                    # Try converting UUID to int if possible
                    if hasattr(created_by_id, '__int__'):
                        if int(created_by_id) == user_id:
                            return True
                    
                    # Try converting int to UUID string representation
                    import uuid
                    try:
                        # If created_by_id is stored as UUID string representation of user.id
                        uuid_from_int = uuid.UUID(int=user_id)
                        if str(created_by_id) == str(uuid_from_int):
                            return True
                    except (ValueError, OverflowError):
                        pass
                    
                    return False
                except (ValueError, TypeError, AttributeError):
                    return False
            
            # If no mock_test and not Quiz/QuizQuestion, deny access
            return False

        return False

    def _get_parent_mock_test(self, obj):
        """
        Get the parent MockTest instance from any child object.
        """
        from .models import MockTest, TestSection, QuestionGroup, Question

        if isinstance(obj, MockTest):
            return obj
        elif isinstance(obj, TestSection):
            return obj.mock_test
        elif isinstance(obj, QuestionGroup):
            return obj.section.mock_test
        elif isinstance(obj, Question):
            return obj.group.section.mock_test
        else:
            # For Quiz and QuizQuestion, they don't have MockTest parent
            # Return None or handle differently
            return None
