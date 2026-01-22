#apps/groups/signals.py
from django.db.models.signals import post_save, post_delete
from django.db import transaction
from django.dispatch import receiver
from django.conf import settings
from django.apps import apps
import logging

from apps.groups.models import Group, GroupMembership

logger = logging.getLogger(__name__)


@receiver([post_save, post_delete], sender=GroupMembership)
def update_group_counts(sender, instance: GroupMembership, **kwargs):
    if getattr(settings, 'DISABLE_GROUP_SIGNALS', False):
        return

    try:
        group = instance.group
        
        student_count = GroupMembership.objects.filter(group=group, role_in_group="STUDENT").count()
        teacher_count = GroupMembership.objects.filter(group=group, role_in_group="TEACHER").count()

        group.student_count = student_count
        group.teacher_count = teacher_count
        group.save(update_fields=['student_count', 'teacher_count'])
        
    except Exception as e:
        logger.error(f"Failed to update group counts for group {instance.group_id}: {e}")


@receiver(post_save, sender=GroupMembership)
def notify_user_added_to_group(sender, instance: GroupMembership, created, **kwargs):
    """
    Send notification when user is added to a group.
    
    CRITICAL: This signal is triggered from a Tenant Schema context (GroupMembership is a tenant model).
    Notification creation MUST happen in Public Schema, so we wrap it with with_public_schema.
    """
    if getattr(settings, 'DISABLE_GROUP_SIGNALS', False):
        return
    
    if not created:
        return
    
    try:
        # Cross-schema imports
        from apps.core.tenant_utils import set_public_schema, with_public_schema
        from apps.centers.models import Center
        from apps.authentication.models import User
        from apps.notifications.signals import _create_notification
        Notification = apps.get_model("notifications", "Notification")
        
        group_name = instance.group.name
        group_link = f"/groups/{instance.group.id}" if instance.group.id else None
        user_id = instance.user_id

        # Fetch user info from public schema
        user_info = with_public_schema(
            lambda: list(User.objects.filter(id=user_id).values('center_id', 'email'))
        )
        
        if not user_info:
            logger.warning(f"User {user_id} not found for notification.")
            return
            
        center_id = user_info[0]['center_id']
        if not center_id:
            return
        
        center = with_public_schema(lambda: Center.objects.get(id=center_id))

        # Determine message and notification type based on role
        if instance.role_in_group == "STUDENT":
            msg = f"You have been added to group: {group_name}"
            notif_type = Notification.NotificationType.GROUP_ADDED
        
        elif instance.role_in_group == "TEACHER":
            msg = f"You have been assigned as a teacher to group: {group_name}"
            notif_type = Notification.NotificationType.ASSIGNED_TO_GROUP
        
        else:
            return

        # CRITICAL FIX: Create notification in PUBLIC schema
        # We're currently in TENANT schema context, so we must explicitly switch
        def create_notification_in_public_schema():
            _create_notification(
                center=center,
                user_id=user_id,
                message=msg,
                link=group_link,
                notification_type=notif_type,
                related_group_id=instance.group_id
            )
        
        with_public_schema(create_notification_in_public_schema)
        logger.info(f"✅ Sent group membership notification to user {user_id}")

    except Exception as e:
        logger.error(f"Failed to send group membership notification: {str(e)}", exc_info=True)