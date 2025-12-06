import logging
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.conf import settings
from .models import Organization
from .services import create_organization_schema

logger = logging.getLogger(__name__)

@receiver(post_save, sender=Organization)
def on_organization_created(sender, instance, created, **kwargs):
    """
    Create tenant schema when Organization is created.
    
    In DEBUG mode: Runs synchronously for easier testing
    In PRODUCTION mode: Should use Celery for async execution (TODO: implement)
    """
    if created:
        logger.info(f"Organization created: {instance.name} ({instance.schema_name})")
        
        # For now, run synchronously in all environments
        # TODO: Implement Celery task for production:
        # if not settings.DEBUG:
        #     from apps.organizations.tasks import create_schema_async
        #     create_schema_async.delay(instance.schema_name)
        # else:
        #     create_organization_schema(instance.schema_name)
        
        try:
            success = create_organization_schema(instance.schema_name)
            if not success:
                logger.error(
                    f"Failed to create schema for organization {instance.name}. "
                    f"Organization status set to SUSPENDED."
                )
        except Exception as e:
            logger.critical(
                f"Exception creating schema for {instance.name}: {e}. "
                f"Organization may be in inconsistent state!"
            )