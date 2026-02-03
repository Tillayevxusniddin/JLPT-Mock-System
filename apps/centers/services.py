# apps/centers/services.py

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.apps import apps
from apps.centers.models import Invitation
from apps.authentication.models import User
from apps.core.tenant_utils import schema_context
import logging

logger = logging.getLogger(__name__)

@transaction.atomic
def approve_invitation(invitation: Invitation, approver: User) -> User:
    try:
        invitation = Invitation.objects.select_related('center').select_for_update().get(id=invitation.id)
    except Invitation.DoesNotExist:
        raise ValidationError("Invitation not found.")

    if invitation.status != "PENDING":
        raise ValidationError("This invitation has already been processed.")
    if invitation.is_expired:
        raise ValidationError("Invitation has expired.")

    try:
        target = User.objects.select_for_update().get(id=invitation.target_user_id)
    except User.DoesNotExist:
        raise ValidationError("User associated with this invitation not found.")

    if approver.center_id != invitation.center_id:
        raise PermissionDenied("Invitation does not belong to this center.")
    
    if approver.role != User.Role.CENTERADMIN:
        raise PermissionDenied("Only CENTER_ADMIN can approve invitations.")

    target.center = invitation.center
    role = invitation.role
    is_guest = invitation.is_guest
    migrating_guest_to_student = role == User.Role.STUDENT and target.role == User.Role.GUEST

    # Handle GUEST→STUDENT upgrade first (approving a guest invitation for STUDENT)
    if migrating_guest_to_student:
        target.role = User.Role.STUDENT
        logger.info("Upgrading GUEST user %s to STUDENT.", target.id)
    elif is_guest:
        target.role = User.Role.GUEST
    elif role == User.Role.GUEST:
        target.role = User.Role.GUEST
    elif role == User.Role.STUDENT:
        target.role = User.Role.STUDENT
    elif role == User.Role.TEACHER:
        target.role = User.Role.TEACHER

    target.is_approved = True
    target.save(update_fields=["center", "role", "is_approved", "updated_at"])

    invitation.status = "APPROVED"
    invitation.approved_by = approver
    invitation.save(update_fields=["status", "approved_by"])

    
    def trigger_tenant_actions():
        """
        Handle post-approval actions that may involve tenant schemas.
        
        CRITICAL: Notification creation moved OUTSIDE schema_context to prevent
        TenantRouter from blocking writes to public schema tables.
        """
        if not invitation.center or not invitation.center.schema_name:
            return

        # Step 1: Handle tenant-specific logic (inside tenant schema)
        try:
            with schema_context(invitation.center.schema_name):
                if migrating_guest_to_student:
                    try:
                        Submission = apps.get_model("submissions", "Submission")
                        count = Submission.objects.filter(user_id=target.id).count()
                        logger.info(f"Migrated user {target.id} with {count} submissions in schema {invitation.center.schema_name}.")
                    except LookupError:
                        logger.debug("Submission model not found, skipping migration count")
                        pass
        except Exception as e:
            logger.error(f"Error in tenant schema actions for invitation {invitation.id}: {e}", exc_info=True)
        
        # Step 2: Notify user (notification is created in center's tenant schema by _create_notification)
        try:
            from apps.notifications.signals import _create_notification
            Notification = apps.get_model("notifications", "Notification")

            msg = f"Your account has been approved! Welcome to {invitation.center.name}."
            _create_notification(
                center=invitation.center,
                user_id=target.id,
                message=msg,
                notification_type=Notification.NotificationType.INVITATION_APPROVED,
            )
            logger.info(f"✅ Sent approval notification to user {target.id}")
        except Exception as e:
            logger.error(f"Failed to send approval notification: {e}", exc_info=True)

    transaction.on_commit(trigger_tenant_actions)

    
    return target