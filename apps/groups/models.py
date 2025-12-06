"""
Groups Models - Tenant Schema
"""
from django.db import models
from django.utils.translation import gettext_lazy as _
from django.core.exceptions import ValidationError
from apps.core.models import TenantBaseModel 

class Group(TenantBaseModel):
    """
    Student Group (Tenant Schema ichida)
    """
    
    # Basic Info
    name = models.CharField(_('group name'), max_length=255)
    description = models.TextField(_('description'), blank=True)
    
    # JLPT Level
    level = models.CharField(
        _('JLPT level'),
        max_length=2,
        choices=[
            ('N5', 'N5 - Beginner'),
            ('N4', 'N4 - Elementary'),
            ('N3', 'N3 - Intermediate'),
            ('N2', 'N2 - Upper Intermediate'),
            ('N1', 'N1 - Advanced'),
        ],
        db_index=True
    )
    
    # Settings
    max_students = models.PositiveIntegerField(_('max students'), default=30)
    is_active = models.BooleanField(_('active'), default=True, db_index=True)
    
    # Stats (denormalization for performance)
    student_count = models.PositiveIntegerField(_('student count'), default=0)
    
    class Meta:
        db_table = 'groups'
        ordering = ['level', 'name']
        # Tenant ichida unique bo'lishi kerak
        constraints = [
            models.UniqueConstraint(fields=['name', 'level'], name='unique_group_name_level')
        ]
    
    def __str__(self):
        return f"{self.name} ({self.level})"

class GroupTeacher(TenantBaseModel):
    """
    Teacher assignment to groups.
    User ID (UUID) saqlanadi, FK emas.
    """
    group = models.ForeignKey(Group, on_delete=models.CASCADE, related_name='teacher_assignments')
    
    # MUHIM: ForeignKey o'rniga UUIDField
    teacher_id = models.UUIDField(_('teacher user id'), db_index=True)
    
    is_primary = models.BooleanField(_('primary teacher'), default=False)
    assigned_at = models.DateTimeField(_('assigned at'), auto_now_add=True)
    
    class Meta:
        db_table = 'group_teachers'
        unique_together = [['group', 'teacher_id']]
        
    def __str__(self):
        return f"Teacher {self.teacher_id} -> {self.group.name}"

class GroupMembership(TenantBaseModel):
    """
    Student membership in groups.
    User ID (UUID) saqlanadi, FK emas.
    """
    class Status(models.TextChoices):
        ACTIVE = 'ACTIVE', _('Active')
        INACTIVE = 'INACTIVE', _('Inactive')
        GRADUATED = 'GRADUATED', _('Graduated')
        DROPPED = 'DROPPED', _('Dropped')
    
    group = models.ForeignKey(Group, on_delete=models.CASCADE, related_name='memberships')
    
    # MUHIM: ForeignKey o'rniga UUIDField
    student_id = models.UUIDField(_('student user id'), db_index=True)
    
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.ACTIVE,
        db_index=True
    )
    
    joined_at = models.DateTimeField(auto_now_add=True)
    left_at = models.DateTimeField(null=True, blank=True)
    
    # Performance tracking (optional)
    attendance_rate = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    average_score = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    
    class Meta:
        db_table = 'group_memberships'
        unique_together = [['group', 'student_id']]
        
    def __str__(self):
        return f"Student {self.student_id} in {self.group.name}"