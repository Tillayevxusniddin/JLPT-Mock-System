"""
Invitations Models - Student invitation system
"""
import secrets
import string
from django.db import models
from django.utils.translation import gettext_lazy as _
from django.utils import timezone

from apps.core.models import TenantBaseModel


class InvitationCode(TenantBaseModel):
    """
    Invitation codes for students to join the organization
    """
    
    class Status(models.TextChoices):
        ACTIVE = 'ACTIVE', _('Active')
        EXPIRED = 'EXPIRED', _('Expired')
        EXHAUSTED = 'EXHAUSTED', _('Exhausted')
        CANCELLED = 'CANCELLED', _('Cancelled')
    
    # Code
    code = models.CharField(
        _('invitation code'),
        max_length=20,
        unique=True,
        db_index=True,
        help_text=_('Unique invitation code')
    )
    
    # Creator
    created_by = models.ForeignKey(
        'authentication.User',
        on_delete=models.SET_NULL,
        null=True,
        related_name='created_invitations',
        limit_choices_to={'role__in': ['CENTERADMIN', 'TEACHER']}
    )
    
    # Target group (optional)
    group = models.ForeignKey(
        'groups.Group',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='invitation_codes',
        help_text=_('If specified, students will be auto-assigned to this group')
    )
    
    # Limits
    max_uses = models.PositiveIntegerField(
        _('maximum uses'),
        default=50,
        help_text=_('How many times this code can be used')
    )
    used_count = models.PositiveIntegerField(_('used count'), default=0)
    
    # Validity
    expires_at = models.DateTimeField(
        _('expires at'),
        help_text=_('When this code expires')
    )
    
    status = models.CharField(
        _('status'),
        max_length=20,
        choices=Status.choices,
        default=Status.ACTIVE,
        db_index=True
    )
    
    # Optional metadata
    description = models.TextField(_('description'), blank=True)
    metadata = models.JSONField(_('metadata'), default=dict, blank=True)
    
    class Meta:
        db_table = 'invitation_codes'
        verbose_name = _('invitation code')
        verbose_name_plural = _('invitation codes')
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['code', 'status']),
            models.Index(fields=['organization_id', 'status']),
            models.Index(fields=['expires_at', 'status']),
        ]
    
    def __str__(self):
        return f"{self.code} ({self.used_count}/{self.max_uses})"
    
    @staticmethod
    def generate_code(length=9):
        """Generate a unique invitation code"""
        chars = string.ascii_uppercase + string.digits
        return ''.join(secrets.choice(chars) for _ in range(length))
    
    def is_valid(self):
        """Check if code is still valid"""
        if self.status != self.Status.ACTIVE:
            return False
        if self.used_count >= self.max_uses:
            return False
        if timezone.now() > self.expires_at:
            return False
        return True
    
    def use(self):
        """Increment usage count"""
        self.used_count += 1
        if self.used_count >= self.max_uses:
            self.status = self.Status.EXHAUSTED
        self.save(update_fields=['used_count', 'status', 'updated_at'])
    
    def expire(self):
        """Mark code as expired"""
        self.status = self.Status.EXPIRED
        self.save(update_fields=['status', 'updated_at'])


class InvitationUsage(TenantBaseModel):
    """
    Track who used which invitation code
    """
    invitation_code = models.ForeignKey(
        InvitationCode,
        on_delete=models.CASCADE,
        related_name='usages'
    )
    
    student = models.ForeignKey(
        'authentication.User',
        on_delete=models.CASCADE,
        related_name='invitation_usages',
        limit_choices_to={'role': 'STUDENT'}
    )
    
    used_at = models.DateTimeField(_('used at'), auto_now_add=True)
    
    # Device info
    ip_address = models.GenericIPAddressField(_('IP address'), null=True, blank=True)
    user_agent = models.TextField(_('user agent'), blank=True)
    
    class Meta:
        db_table = 'invitation_usages'
        verbose_name = _('invitation usage')
        verbose_name_plural = _('invitation usages')
        unique_together = [['invitation_code', 'student']]
        indexes = [
            models.Index(fields=['invitation_code', 'used_at']),
            models.Index(fields=['student', 'used_at']),
        ]
    
    def __str__(self):
        return f"{self.student.get_full_name()} used {self.invitation_code.code}"