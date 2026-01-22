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
    
    if approver.role != "CENTER_ADMIN":
        raise PermissionDenied("Only CENTER_ADMIN can approve invitations.")

    target.center = invitation.center
    role = invitation.role
    is_guest = invitation.is_guest
    
    migrating_guest_to_student = (role == "STUDENT" and target.role == "GUEST")

    if is_guest:
        target.role = "GUEST"
    elif role == "GUEST":
        target.role = "GUEST"
    elif migrating_guest_to_student:
        target.role = "STUDENT"
        logger.info(f"Upgrading GUEST user {target.id} to STUDENT.")
    elif role == "STUDENT":
        target.role = "STUDENT"
    elif role == "TEACHER":
        target.role = "TEACHER"

    target.is_approved = True
    target.save(update_fields=["center", "role", "is_approved", "updated_at"])

    invitation.status = "APPROVED"
    invitation.approved_by = approver
    invitation.save(update_fields=["status", "approved_by"])

    
    def trigger_tenant_actions():
        if not invitation.center or not invitation.center.schema_name:
            return

        try:
            with schema_context(invitation.center.schema_name):
                if migrating_guest_to_student:
                    try:
                        Submission = apps.get_model("submissions", "Submission")
                        count = Submission.objects.filter(user_id=target.id).count()
                        logger.info(f"Migrated user {target.id} with {count} submissions in schema {invitation.center.schema_name}.")
                    except LookupError:
                        pass 
                try:
                    from apps.notifications.signals import _create_notification
                    Notification = apps.get_model("notifications", "Notification")
                    
                    msg = f"Your account has been approved! Welcome to {invitation.center.name}."
                    _create_notification(
                        center=invitation.center,
                        user_id=target.id,
                        message=msg,
                        notification_type=Notification.NotificationType.INVITATION_APPROVED
                    )
                except Exception as e:
                    logger.error(f"Failed to send approval notification: {e}")

        except Exception as e:
            logger.error(f"Error in tenant actions for invitation {invitation.id}: {e}", exc_info=True)
    transaction.on_commit(trigger_tenant_actions)
    
    return target