#apps/centers/signals.py
from django.db.models.signals import post_save
from django.db import transaction
from django.dispatch import receiver
from django.apps import apps
import logging

logger = logging.getLogger(__name__)


@receiver(post_save, sender="centers.Center")
def run_migrations_for_new_center(sender, instance, created, **kwargs):
    if not created:
        return
    
    if not instance.schema_name:
        logger.warning(f"Center {instance.id} created without schema_name, skipping schema creation")
        return
    
    try:
        instance.create_schema()
        logger.info(f"✅ Created schema: {instance.schema_name}")
    except Exception as e:
        logger.error(
            f"❌ Failed to create schema {instance.schema_name}: {str(e)}",
            exc_info=True,
            extra={'center_id': instance.id, 'schema_name': instance.schema_name}
        )
        return

    # CRITICAL FIX: Defer Celery task until transaction commits
    # This prevents DoesNotExist errors when worker picks up task before commit
    def queue_migrations():
        from apps.centers.tasks import run_tenant_migrations
        try:
            task_result = run_tenant_migrations.delay(instance.schema_name)
            logger.info(
                f"✅ Queued migrations for new center: {instance.schema_name} "
                f"(task_id: {task_result.id})",
                extra={
                    'center_id': instance.id,
                    'center_name': instance.name,
                    'schema_name': instance.schema_name,
                    'task_id': task_result.id
                }
            )
        except Exception as e:
            logger.error(
                f"❌ Failed to queue migrations for {instance.schema_name}: {str(e)}",
                exc_info=True,
                extra={
                    'center_id': instance.id,
                    'center_name': instance.name,
                    'schema_name': instance.schema_name
                }
            )
    
    # Schedule task AFTER transaction commits
    transaction.on_commit(queue_migrations)



@receiver(post_save, sender="centers.ContactRequest")
@transaction.atomic
def notify_owner_on_contact_request(sender, instance, created, **kwargs):
    """
    Notify Owner when a new contact request is created.
    """
    if not created:
        return
    
    from apps.notifications.signals import _create_notification
    Notification = apps.get_model("notifications", "Notification")
    # YANGILANDI: accounts -> authentication
    User = apps.get_model("authentication", "User")
    
    # Find all Owner users
    owner_users = User.objects.filter(role="OWNER", is_active=True)
    
    if not owner_users.exists():
        return
    
    # Create notification for each Owner
    msg = f"New contact request from {instance.full_name} for center: {instance.center_name}"
    contact_link = f"/owner/contact-requests/{instance.id}" if instance.id else None
    
    for owner in owner_users:
        _create_notification(
            center=None,  # Owner notifications are platform-wide
            user_id=owner.id,
            message=msg,
            link=contact_link,
            notification_type=Notification.NotificationType.CONTACT_REQUEST,
            related_contact_request_id=instance.id
        )