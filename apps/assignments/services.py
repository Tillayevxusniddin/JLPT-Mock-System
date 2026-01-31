# apps/assignments/services.py

from django.core.exceptions import ValidationError
from apps.mock_tests.models import MockTest


def validate_assignment_payload(mock_test, group_ids=None, user_ids=None):
    """
    Validate assignment payload before creation/update.
    
    Args:
        mock_test: MockTest instance (required)
        group_ids: List of Group UUIDs (optional)
        user_ids: List of User IDs (integers, optional, for Homework only)
        
    Raises:
        ValidationError: If validation fails
        
    Returns:
        dict: Validated data with user_ids verified
    """
    # Ensure mock_test is provided
    if not mock_test:
        raise ValidationError("MockTest is required for assignments.")
    
    # Ensure mock_test status is PUBLISHED
    if mock_test.status != MockTest.Status.PUBLISHED:
        raise ValidationError(
            "Only PUBLISHED mock tests can be assigned. "
            f"Current status: {mock_test.status}"
        )
    
    # Ensure mock_test is not deleted
    if mock_test.deleted_at is not None:
        raise ValidationError("Deleted mock tests cannot be assigned.")
    
    # Ensure at least one Group OR one User is assigned
    if not group_ids and not user_ids:
        raise ValidationError(
            "At least one group or one user must be assigned."
        )
    
    # Validate user_ids if provided (cross-schema validation)
    validated_user_ids = []
    if user_ids:
        if not isinstance(user_ids, list):
            raise ValidationError("assigned_user_ids must be a list.")
        
        if not all(isinstance(uid, int) for uid in user_ids):
            raise ValidationError("All user IDs must be integers.")
        
        # Cross-schema validation: Verify users exist in Public Schema
        from apps.core.tenant_utils import with_public_schema
        from apps.authentication.models import User
        
        def fetch_users():
            return User.objects.filter(id__in=user_ids).values_list('id', flat=True)
        
        existing_user_ids = set(with_public_schema(fetch_users))
        
        # Check if all provided user_ids exist
        missing_user_ids = set(user_ids) - existing_user_ids
        if missing_user_ids:
            raise ValidationError(
                f"The following user IDs do not exist: {list(missing_user_ids)}"
            )
        
        # Verify users belong to the current tenant (Center)
        # Get current tenant's center_id from request context
        # This will be handled in the serializer/view where we have access to request.user
        validated_user_ids = list(existing_user_ids)
    
    # Validate group_ids if provided
    validated_group_ids = []
    if group_ids:
        if not isinstance(group_ids, list):
            raise ValidationError("assigned_group_ids must be a list.")
        
        from apps.groups.models import Group
        
        # Verify groups exist in tenant schema
        existing_groups = Group.objects.filter(id__in=group_ids)
        existing_group_ids = set(existing_groups.values_list('id', flat=True))
        
        missing_group_ids = set(group_ids) - existing_group_ids
        if missing_group_ids:
            raise ValidationError(
                f"The following group IDs do not exist: {list(missing_group_ids)}"
            )
        
        validated_group_ids = list(existing_group_ids)
    
    return {
        'mock_test': mock_test,
        'group_ids': validated_group_ids,
        'user_ids': validated_user_ids
    }


def validate_user_ids_belong_to_tenant(user_ids, tenant_center_id):
    """
    Validate that all user_ids exist in the **Public Schema** (User table) and
    belong to the **Current Center** (User.center_id == tenant_center_id).
    Raises ValidationError if any ID is missing or belongs to another center.
    """
    if not user_ids:
        return
    if not isinstance(user_ids, (list, tuple)):
        raise ValidationError("assigned_user_ids must be a list of integers.")
    user_ids = [int(uid) for uid in user_ids if uid is not None]
    if not user_ids:
        return

    from apps.core.tenant_utils import with_public_schema
    from apps.authentication.models import User

    def fetch_valid_ids():
        return set(
            User.objects.filter(
                id__in=user_ids,
                center_id=tenant_center_id,
            )
            .values_list("id", flat=True)
        )

    valid_ids = with_public_schema(fetch_valid_ids)
    invalid_ids = set(user_ids) - valid_ids
    if invalid_ids:
        raise ValidationError(
            f"The following user IDs do not belong to this center: {sorted(invalid_ids)}"
        )
