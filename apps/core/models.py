import uuid
from django.db import models
from django.utils import timezone
from .managers import SoftDeleteManager, GlobalManager

class UUIDModel(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    class Meta:
        abstract = True

class TimeStampedModel(models.Model):
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)
    class Meta:
        abstract = True

class SoftDeleteModel(models.Model):
    deleted_at = models.DateTimeField(null=True, blank=True, db_index=True)
    
    objects = SoftDeleteManager()
    all_objects = GlobalManager()
    
    class Meta:
        abstract = True

    def soft_delete(self):
        self.deleted_at = timezone.now()
        self.save(update_fields=["deleted_at"])

    def restore(self):
        self.deleted_at = None
        self.save(update_fields=["deleted_at"])

class BaseModel(UUIDModel, TimeStampedModel, SoftDeleteModel):
    """
    Loyiha uchun asosiy model. 
    Barcha yangi modellar shundan meros olishi kerak (User va Tenantdan tashqari).
    """
    class Meta:
        abstract = True