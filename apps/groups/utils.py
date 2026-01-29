# apps/groups/utils.py
"""
Group membership utilities. History is recorded when a student is removed or moved.
"""
from django.db import transaction
from django.utils import timezone

from rest_framework.exceptions import PermissionDenied, ValidationError

from apps.groups.models import GroupMembership, GroupMembershipHistory


@transaction.atomic
def remove_student_from_group(user_id, actor, reason="REMOVED", group_id=None):
    """
    Remove a student from a group and record in GroupMembershipHistory.

    Args:
        user_id: Public User id.
        actor: Request user (must be CENTER_ADMIN).
        reason: REMOVED | MOVED | LEFT.
        group_id: If provided, remove from this group only; otherwise first STUDENT membership.
    """
    from apps.authentication.models import User
    from apps.core.tenant_utils import with_public_schema

    if actor.role != "CENTER_ADMIN":
        raise PermissionDenied("Only CenterAdmin can remove students from groups.")

    def get_user():
        try:
            return User.objects.select_for_update().get(id=user_id, center_id=actor.center_id)
        except User.DoesNotExist:
            raise ValidationError("User not found in your center.")

    user = with_public_schema(get_user)

    qs = GroupMembership.objects.filter(
        user_id=user.id,
        role_in_group="STUDENT",
    ).select_related("group")
    if group_id is not None:
        qs = qs.filter(group_id=group_id)
    membership = qs.first()

    if not membership:
        raise ValidationError("User is not a student in this group.")

    GroupMembershipHistory.objects.create(
        user_id=user.id,
        group=membership.group,
        role_in_group="STUDENT",
        joined_at=membership.created_at,
        left_at=timezone.now(),
        left_reason=reason,
    )
    membership.delete()

