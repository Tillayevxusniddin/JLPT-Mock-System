# apps/materials/signals.py
"""
Signals for the materials app.

post_delete: On hard delete of a Material, remove the physical file from storage (S3/filesystem)
to avoid orphaned files.
"""
from django.db.models.signals import post_delete
from django.dispatch import receiver

from .models import Material


@receiver(post_delete, sender=Material)
def delete_material_file_on_hard_delete(sender, instance, **kwargs):
    """
    When a Material is hard-deleted, delete its file from storage (S3 or default).
    Soft-delete does not trigger post_delete, so this runs only on actual DB delete.
    """
    if instance.file:
        try:
            instance.file.delete(save=False)
        except Exception:
            pass
