"""
Groups Models - Student groups and memberships
"""
from django.db import models
from django.utils.translation import gettext_lazy as _
from django.core.exceptions import ValidationError

from apps.core.models import TenantBaseModel


class Group(TenantBaseModel):
    """
    Student Group (e.g., N3 Evening Group, N5 Beginners)
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
    
    # Teachers assigned to this group
    teachers = models.ManyToManyField(
        'authentication.User',
        through='GroupTeacher',
        related_name='teaching_groups',
        limit_choices_to={'role': 'TEACHER'}
    )
    
    # Settings
    max_students = models.PositiveIntegerField(_('max students'), default=30)
    is_active = models.BooleanField(_('active'), default=True, db_index=True)
    
    # Schedule info (optional)
    schedule = models.JSONField(_('schedule'), default=dict, blank=True)
    
    # Stats (cached)
    student_count = models.PositiveIntegerField(_('student count'), default=0)
    
    class Meta:
        db_table = 'groups'
        verbose_name = _('group')
        verbose_name_plural = _('groups')
        ordering = ['level', 'name']
        indexes = [
            models.Index(fields=['organization_id', 'level']),
            models.Index(fields=['organization_id', 'is_active']),
        ]
    
    def __str__(self):
        return f"{self.name} ({self.level})"
    
    def clean(self):
        if self.student_count > self.max_students:
            raise ValidationError(_('Student count exceeds maximum limit'))


class GroupTeacher(TenantBaseModel):
    """
    Teacher assignment to groups
    """
    group = models.ForeignKey(Group, on_delete=models.CASCADE, related_name='teacher_assignments')
    teacher = models.ForeignKey(
        'authentication.User',
        on_delete=models.CASCADE,
        related_name='group_assignments',
        limit_choices_to={'role': 'TEACHER'}
    )
    
    is_primary = models.BooleanField(_('primary teacher'), default=False)
    assigned_at = models.DateTimeField(_('assigned at'), auto_now_add=True)
    
    class Meta:
        db_table = 'group_teachers'
        verbose_name = _('group teacher')
        verbose_name_plural = _('group teachers')
        unique_together = [['group', 'teacher']]
        indexes = [
            models.Index(fields=['group', 'teacher']),
            models.Index(fields=['teacher', 'is_primary']),
        ]
    
    def __str__(self):
        return f"{self.teacher.get_full_name()} -> {self.group.name}"


class GroupMembership(TenantBaseModel):
    """
    Student membership in groups
    """
    
    class Status(models.TextChoices):
        ACTIVE = 'ACTIVE', _('Active')
        INACTIVE = 'INACTIVE', _('Inactive')
        GRADUATED = 'GRADUATED', _('Graduated')
        DROPPED = 'DROPPED', _('Dropped')
    
    group = models.ForeignKey(Group, on_delete=models.CASCADE, related_name='memberships')
    student = models.ForeignKey(
        'authentication.User',
        on_delete=models.CASCADE,
        related_name='group_memberships',
        limit_choices_to={'role': 'STUDENT'}
    )
    
    status = models.CharField(
        _('status'),
        max_length=20,
        choices=Status.choices,
        default=Status.ACTIVE,
        db_index=True
    )
    
    joined_at = models.DateTimeField(_('joined at'), auto_now_add=True)
    left_at = models.DateTimeField(_('left at'), null=True, blank=True)
    
    # Performance tracking
    attendance_rate = models.DecimalField(
        _('attendance rate'),
        max_digits=5,
        decimal_places=2,
        default=0
    )
    average_score = models.DecimalField(
        _('average score'),
        max_digits=5,
        decimal_places=2,
        default=0
    )
    
    class Meta:
        db_table = 'group_memberships'
        verbose_name = _('group membership')
        verbose_name_plural = _('group memberships')
        unique_together = [['group', 'student']]
        indexes = [
            models.Index(fields=['group', 'status']),
            models.Index(fields=['student', 'status']),
        ]
    
    def __str__(self):
        return f"{self.student.get_full_name()} in {self.group.name}"