"""
Audit Models - Audit logging for security and tracking
"""
from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.core.models import TenantBaseModel


class AuditLog(TenantBaseModel):
    """
    Audit trail for important actions
    Tracks who did what and when
    """
    
    class Action(models.TextChoices):
        # User actions
        LOGIN = 'LOGIN', _('User Login')
        LOGOUT = 'LOGOUT', _('User Logout')
        REGISTER = 'REGISTER', _('User Register')
        
        # CRUD operations
        CREATE = 'CREATE', _('Create')
        UPDATE = 'UPDATE', _('Update')
        DELETE = 'DELETE', _('Delete')
        VIEW = 'VIEW', _('View')
        
        # Test operations
        TEST_CREATE = 'TEST_CREATE', _('Test Created')
        TEST_PUBLISH = 'TEST_PUBLISH', _('Test Published')
        TEST_ARCHIVE = 'TEST_ARCHIVE', _('Test Archived')
        
        # Assignment operations
        ASSIGN = 'ASSIGN', _('Assignment Created')
        UNASSIGN = 'UNASSIGN', _('Assignment Removed')
        
        # Attempt operations
        ATTEMPT_START = 'ATTEMPT_START', _('Attempt Started')
        ATTEMPT_SUBMIT = 'ATTEMPT_SUBMIT', _('Attempt Submitted')
        
        # Grading operations
        GRADE = 'GRADE', _('Manual Grading')
        FEEDBACK = 'FEEDBACK', _('Feedback Given')
        
        # Group operations
        GROUP_CREATE = 'GROUP_CREATE', _('Group Created')
        GROUP_ADD_MEMBER = 'GROUP_ADD_MEMBER', _('Member Added to Group')
        GROUP_REMOVE_MEMBER = 'GROUP_REMOVE_MEMBER', _('Member Removed from Group')
        
        # Invitation operations
        INVITATION_CREATE = 'INVITATION_CREATE', _('Invitation Code Created')
        INVITATION_USE = 'INVITATION_USE', _('Invitation Code Used')
        
        # Organization operations
        ORG_CREATE = 'ORG_CREATE', _('Organization Created')
        ORG_UPDATE = 'ORG_UPDATE', _('Organization Updated')
        ORG_SUSPEND = 'ORG_SUSPEND', _('Organization Suspended')
        
        # Other
        EXPORT = 'EXPORT', _('Data Export')
        IMPORT = 'IMPORT', _('Data Import')
    
    # User who performed the action
    user = models.ForeignKey(
        'authentication.User',
        on_delete=models.SET_NULL,
        null=True,
        related_name='audit_logs'
    )
    
    # Action details
    action = models.CharField(
        _('action'),
        max_length=30,
        choices=Action.choices,
        db_index=True
    )
    
    # Resource affected
    resource_type = models.CharField(
        _('resource type'),
        max_length=50,
        help_text=_('e.g., MockTest, Assignment, User')
    )
    resource_id = models.UUIDField(
        _('resource ID'),
        null=True,
        blank=True,
        db_index=True
    )
    
    # Description
    description = models.TextField(
        _('description'),
        help_text=_('Human-readable description of the action')
    )
    
    # Additional data
    metadata = models.JSONField(
        _('metadata'),
        default=dict,
        blank=True,
        help_text=_('Additional context about the action')
    )
    
    # Request info
    ip_address = models.GenericIPAddressField(_('IP address'), null=True, blank=True)
    user_agent = models.TextField(_('user agent'), blank=True)
    
    # Result
    success = models.BooleanField(_('success'), default=True)
    error_message = models.TextField(_('error message'), blank=True)
    
    class Meta:
        db_table = 'audit_logs'
        verbose_name = _('audit log')
        verbose_name_plural = _('audit logs')
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['organization_id', '-created_at']),
            models.Index(fields=['user', '-created_at']),
            models.Index(fields=['action', '-created_at']),
            models.Index(fields=['resource_type', 'resource_id']),
        ]
    
    def __str__(self):
        user_display = self.user.get_full_name() if self.user else 'System'
        return f"{user_display} - {self.get_action_display()} - {self.created_at}"