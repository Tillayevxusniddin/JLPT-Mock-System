from django.db.models.signals import pre_migrate
import uuid
from django.db import models
from django.utils import timezone
from apps.core.managers import SoftDeleteManager

class UUIDModel(models.Model):
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    class Meta:
        abstract = True

class TimeStampedModel(models.Model):

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True

class SoftDeleteModel(models.Model):
    
    deleted_at = models.DateTimeField(null=True, blank=True, db_index=True)

    class Meta:
        abstract = True

    @property
    def is_deleted(self):
        return self.deleted_at is not None
    
    def soft_delete(self):
        if not self.deleted_at:
            self.deleted_at = timezone.now()
            self.save(update_fields=["deleted_at"])
        return self
        
    def restore(self):
        if self.deleted_at:
            self.deleted_at = None
            self.save(update_fields=["deleted_at"])
        return self

class BaseModel(UUIDModel, TimeStampedModel, SoftDeleteModel):
    
    class Meta:
        abstract = True

    HARD_DELETE = False
    objects = SoftDeleteManager()
    all_objects = models.Manager()

    def delete(self, using=None, keep_parents=False):
        if self.HARD_DELETE:
            return super().delete(using=using, keep_parents=keep_parents)
        return self.soft_delete()

    def hard_delete(self, using=None, keep_parents=False):
        return super().delete(using=using, keep_parents=keep_parents)

class PublicBaseModel(UUIDModel, TimeStampedModel, SoftDeleteModel):

    class Meta:
        abstract = True
    
    HARD_DELETE = False
    objects = SoftDeleteManager()
    all_objects = models.Manager()

    def delete(self, using=None, keep_parents=False):
        if getattr(self, "HARD_DELETE", False):
            return super().delete(using=using, keep_parents=keep_parents)
        return self.soft_delete()

    def hard_delete(self, using=None, keep_parents=False):
        return super().delete(using=using, keep_parents=keep_parents)

class TenantBaseModel(UUIDModel, TimeStampedModel, SoftDeleteModel):

    class Meta:
        abstract = True

    HARD_DELETE = False
    objects = SoftDeleteManager()
    all_objects = models.Manager()

    def delete(self, using=None, keep_parents=False):
        if getattr(self, "HARD_DELETE", False):
            return super().delete(using=using, keep_parents=keep_parents)
        return self.soft_delete()
    
    def hard_delete(self, using=None, keep_parents=False):
        return super().delete(using=using, keep_parents=keep_parents)