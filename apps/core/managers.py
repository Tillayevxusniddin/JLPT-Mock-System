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
    
    def get_queryset(self):
        base = SoftDeleteQuerySet(self.model, using=self._db)
        if hasattr(self.model, "deleted_at"):
            return base.filter(deleted_at__isnull=True)
        return base

    def hard_delete(self):
        return self.get_queryset().hard_delete()
    
