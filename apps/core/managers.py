# apps/core/managers.py
"""
Soft-delete manager: filters out rows with deleted_at set by default.

Note: Reverse FK accessors (e.g. other_model.my_soft_deleted_fk) still return
soft-deleted instances. Use MyModel.objects.alive() or filter(deleted_at__isnull=True)
when you need to exclude soft-deleted related objects.
"""
from django.db import models
from django.utils import timezone


class SoftDeleteQuerySet(models.QuerySet):
    def delete(self):
        if not hasattr(self.model, "deleted_at"):
            return super().delete()
        return super().update(deleted_at=timezone.now())

    def hard_delete(self):
        return super().delete()

    def alive(self):
        return self.filter(deleted_at__isnull=True)

    def dead(self):
        return self.filter(deleted_at__isnull=False)


class SoftDeleteManager(models.Manager):
    def _base_queryset(self):
        return SoftDeleteQuerySet(self.model, using=self._db)

    def get_queryset(self):
        base = self._base_queryset()
        if hasattr(self.model, "deleted_at"):
            return base.filter(deleted_at__isnull=True)
        return base

    def alive(self):
        """Return queryset with only non-deleted objects."""
        return self.get_queryset().alive()

    def dead(self):
        """Return queryset with only soft-deleted objects."""
        base = self._base_queryset()
        if hasattr(self.model, "deleted_at"):
            return base.filter(deleted_at__isnull=False)
        return base.none()

    def hard_delete(self):
        return self._base_queryset().hard_delete()

