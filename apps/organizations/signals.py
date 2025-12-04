from django.db.models.signals import post_save
from django.dispatch import receiver
from .models import Organization
from .services import create_organization_schema

@receiver(post_save, sender=Organization)
def on_organization_created(sender, instance, created, **kwargs):
    if created:
        # Yangi organization yaratildi -> Schema yaratamiz
        create_organization_schema(instance.schema_name)