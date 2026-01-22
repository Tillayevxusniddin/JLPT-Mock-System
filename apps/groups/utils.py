#apps/groups/utils.py
from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied, ValidationError

from apps.groups.models import GroupMembership, GroupMembershipHistory

@transaction.atomic
def remove_student_from_group(user_id, actor, reason="REMOVED"):

    from apps.authentication.models import User
    from apps.core.tenant_utils import with_public_schema
    
    if actor.role != "CENTER_ADMIN":
        raise PermissionDenied("Only CenterAdmin can remove students from groups.")
    
    def get_user():
        try:
            return User.objects.select_for_update().get(id=user_id, center_id=actor.center_id)
        except User.DoesNotExist:
            raise ValidationError(f"User with ID {user_id} not found in your center.")
    
    user = with_public_schema(get_user)
    
    membership = GroupMembership.objects.filter(
        user_id=user.id,
        role_in_group="STUDENT"
    ).select_related('group').first()
    
    if not membership:
        raise ValidationError(f"User '{user.email}' is not in any group.")
    
    GroupMembershipHistory.objects.create(
        user_id=user.id,
        group=membership.group,
        role_in_group="STUDENT",
        joined_at=membership.created_at,
        left_at=timezone.now(),
        left_reason=reason,
        performed_by_id=actor.id
    )
    

    membership.delete()
    
