"""
Core Models - Base models for multi-tenancy
"""
import uuid
from django.db import models
from django.utils.translation import gettext_lazy as _


class TimeStampedModel(models.Model):
    """
    Abstract base model with created_at and updated_at fields
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(_('created at'), auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(_('updated at'), auto_now=True)
    
    class Meta:
        abstract = True
        ordering = ['-created_at']


class TenantBaseModel(TimeStampedModel):
    """
    Base model for all tenant-specific models
    Automatically filters by organization
    """
    # Organization ID - har bir model organizatsiyaga tegishli
    organization_id = models.UUIDField(
        _('organization'),
        db_index=True,
        help_text=_('Organization this record belongs to')
    )
    
    # Soft delete
    is_deleted = models.BooleanField(_('is deleted'), default=False, db_index=True)
    deleted_at = models.DateTimeField(_('deleted at'), null=True, blank=True)
    
    class Meta:
        abstract = True
    
    def soft_delete(self):
        """Soft delete the record"""
        from django.utils import timezone
        self.is_deleted = True
        self.deleted_at = timezone.now()
        self.save(update_fields=['is_deleted', 'deleted_at', 'updated_at'])
    
    def restore(self):
        """Restore soft-deleted record"""
        self.is_deleted = False
        self.deleted_at = None
        self.save(update_fields=['is_deleted', 'deleted_at', 'updated_at'])