"""
Assignments Models - Assigning tests to students
"""
from django.db import models
from django.utils.translation import gettext_lazy as _
from django.core.exceptions import ValidationError

from apps.core.models import TenantBaseModel


class Assignment(TenantBaseModel):
    """
    Assignment of Mock Test to Students or Groups
    Teacher assigns test to either:
    1. Entire group
    2. Individual student
    """
    
    class AssignmentType(models.TextChoices):
        GROUP = 'GROUP', _('Group Assignment')
        INDIVIDUAL = 'INDIVIDUAL', _('Individual Assignment')
    
    # Test to assign
    mock_test = models.ForeignKey(
        'mock_tests.MockTest',
        on_delete=models.CASCADE,
        related_name='assignments'
    )
    
    # Assignment type
    assignment_type = models.CharField(
        _('assignment type'),
        max_length=20,
        choices=AssignmentType.choices,
        db_index=True
    )
    
    # Target (either group or student)
    group = models.ForeignKey(
        'groups.Group',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='assignments'
    )
    student = models.ForeignKey(
        'authentication.User',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='individual_assignments',
        limit_choices_to={'role': 'STUDENT'}
    )
    
    # Assignment details
    title = models.CharField(
        _('assignment title'),
        max_length=255,
        blank=True,
        help_text=_('Custom title for this assignment')
    )
    instructions = models.TextField(
        _('instructions'),
        blank=True,
        help_text=_('Additional instructions for students')
    )
    
    # Creator
    assigned_by = models.ForeignKey(
        'authentication.User',
        on_delete=models.SET_NULL,
        null=True,
        related_name='created_assignments',
        limit_choices_to={'role__in': ['TEACHER', 'CENTERADMIN']}
    )
    
    # Timing
    start_date = models.DateTimeField(_('start date'))
    due_date = models.DateTimeField(_('due date'))
    
    # Settings
    allow_retake = models.BooleanField(
        _('allow retake'),
        default=False,
        help_text=_('Can students retake this test?')
    )
    max_attempts = models.PositiveIntegerField(
        _('maximum attempts'),
        default=1,
        help_text=_('How many times can students attempt this test')
    )
    
    show_answers_after_submit = models.BooleanField(
        _('show answers after submit'),
        default=True
    )
    show_score_immediately = models.BooleanField(
        _('show score immediately'),
        default=True
    )
    
    randomize_questions = models.BooleanField(
        _('randomize questions'),
        default=False,
        help_text=_('Shuffle question order')
    )
    randomize_choices = models.BooleanField(
        _('randomize choices'),
        default=False,
        help_text=_('Shuffle answer choices')
    )
    
    # Statistics (cached)
    total_students = models.PositiveIntegerField(_('total students'), default=0)
    submitted_count = models.PositiveIntegerField(_('submitted count'), default=0)
    average_score = models.DecimalField(
        _('average score'),
        max_digits=5,
        decimal_places=2,
        default=0
    )
    pass_rate = models.DecimalField(
        _('pass rate'),
        max_digits=5,
        decimal_places=2,
        default=0
    )
    
    # Status
    is_active = models.BooleanField(_('active'), default=True, db_index=True)
    
    class Meta:
        db_table = 'assignments'
        verbose_name = _('assignment')
        verbose_name_plural = _('assignments')
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['organization_id', 'is_active']),
            models.Index(fields=['group', 'start_date']),
            models.Index(fields=['student', 'start_date']),
            models.Index(fields=['assigned_by', 'created_at']),
            models.Index(fields=['due_date']),
        ]
    
    def __str__(self):
        if self.assignment_type == self.AssignmentType.GROUP:
            target = f"Group: {self.group.name}"
        else:
            target = f"Student: {self.student.get_full_name()}"
        return f"{self.mock_test.title} → {target}"
    
    def clean(self):
        """Validate assignment"""
        super().clean()
        
        # Validate dates
        if self.start_date and self.due_date:
            if self.due_date <= self.start_date:
                raise ValidationError(_('Due date must be after start date'))
        
        # Validate assignment target
        if self.assignment_type == self.AssignmentType.GROUP:
            if not self.group or self.student:
                raise ValidationError(
                    _('Group assignment must have a group and no student')
                )
        elif self.assignment_type == self.AssignmentType.INDIVIDUAL:
            if self.group or not self.student:
                raise ValidationError(
                    _('Individual assignment must have a student and no group')
                )
    
    def get_assigned_students(self):
        """Get list of student IDs this assignment applies to"""
        if self.assignment_type == self.AssignmentType.GROUP:
            return list(
                self.group.memberships
                .filter(status='ACTIVE')
                .values_list('student_id', flat=True)
            )
        else:
            return [self.student.id]