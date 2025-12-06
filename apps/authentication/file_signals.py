"""
File cleanup signals for User model
Automatically delete old files when avatar is updated or user is deleted
"""
import os
import logging
from django.db.models.signals import pre_save, pre_delete
from django.dispatch import receiver
from django.core.files.storage import default_storage
from django.contrib.auth import get_user_model
logger = logging.getLogger(__name__)

User = get_user_model()


def delete_file_if_exists(file_path):
    """Helper function to safely delete a file"""
    if file_path and default_storage.exists(file_path):
        try:
            default_storage.delete(file_path)
        except Exception as e:
            print(f"Error deleting file {file_path}: {e}")
            logger.error(f"Error deleting file {file_path}: {e}")


@receiver(pre_save, sender=User)
def delete_old_avatar_on_update(sender, instance, **kwargs):
    """
    Delete old avatar file when user updates their avatar
    """
    if not instance.pk:
        return  # New instance, no old file to delete
    
    try:
        old_instance = User.objects.get(pk=instance.pk)
    except User.DoesNotExist:
        return  # Instance doesn't exist yet
    
    # Check if avatar field has changed
    old_avatar = old_instance.avatar
    new_avatar = instance.avatar
    
    # If avatar has changed and old one exists, delete it
    if old_avatar and old_avatar != new_avatar:
        delete_file_if_exists(old_avatar.name)


@receiver(pre_delete, sender=User)
def delete_avatar_on_user_delete(sender, instance, **kwargs):
    """
    Delete avatar file when user is deleted
    """
    if instance.avatar:
        delete_file_if_exists(instance.avatar.name)
