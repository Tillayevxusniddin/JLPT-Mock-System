"""
File cleanup signals for Organization model
Automatically delete old files when logo is updated or organization is deleted
"""
import os
from django.db.models.signals import pre_save, pre_delete
from django.dispatch import receiver
from django.core.files.storage import default_storage
from apps.organizations.models import Organization


def delete_file_if_exists(file_path):
    """Helper function to safely delete a file"""
    if file_path and default_storage.exists(file_path):
        try:
            default_storage.delete(file_path)
        except Exception as e:
            # Log error but don't raise to avoid blocking the main operation
            print(f"Error deleting file {file_path}: {e}")


@receiver(pre_save, sender=Organization)
def delete_old_logo_on_update(sender, instance, **kwargs):
    """
    Delete old logo file when organization updates their logo
    """
    if not instance.pk:
        return  # New instance, no old file to delete
    
    try:
        old_instance = Organization.objects.get(pk=instance.pk)
    except Organization.DoesNotExist:
        return  # Instance doesn't exist yet
    
    # Check if logo field has changed
    old_logo = old_instance.logo
    new_logo = instance.logo
    
    # If logo has changed and old one exists, delete it
    if old_logo and old_logo != new_logo:
        delete_file_if_exists(old_logo.name)


@receiver(pre_delete, sender=Organization)
def delete_logo_on_organization_delete(sender, instance, **kwargs):
    """
    Delete logo file when organization is deleted
    """
    if instance.logo:
        delete_file_if_exists(instance.logo.name)
