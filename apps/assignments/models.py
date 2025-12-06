"""
Assignments Models - Assigning tests to students (Tenant Schema)
"""
from django.db import models
from django.utils.translation import gettext_lazy as _
from django.core.exceptions import ValidationError
from django.utils import timezone

from apps.core.models import TenantBaseModel

class Assignment(TenantBaseModel):
    """
    Imtihon yoki Quizni guruhga/talabaga tayinlash.
    """
    
    class AssignmentType(models.TextChoices):
        GROUP = 'GROUP', _('Group Assignment')
        INDIVIDUAL = 'INDIVIDUAL', _('Individual Assignment')

    class Status(models.TextChoices):
        SCHEDULED = 'SCHEDULED', _('Scheduled') # Rejalashtirilgan
        IN_PROGRESS = 'IN_PROGRESS', _('In Progress (Started)') # O'qituvchi start bosdi
        COMPLETED = 'COMPLETED', _('Completed') # Tugadi
        CANCELLED = 'CANCELLED', _('Cancelled') # Bekor qilindi

    # --- CONTENT (Nima topshiriladi?) ---
    # MockTest (Foreign Key Tenant ichida bo'lgani uchun ishlaydi)
    mock_test = models.ForeignKey(
        'mock_tests.MockTest',
        on_delete=models.CASCADE,
        related_name='assignments',
        null=True, blank=True
    )
    
    # YANGI: Quiz (Foreign Key Tenant ichida)
    quiz = models.ForeignKey(
        'mock_tests.Quiz',
        on_delete=models.CASCADE,
        related_name='assignments',
        null=True, blank=True
    )

    # --- TARGET (Kimga?) ---
    assignment_type = models.CharField(max_length=20, choices=AssignmentType.choices, db_index=True)
    
    # Group (Tenant ichida bo'lgani uchun FK ishlaydi)
    group = models.ForeignKey(
        'groups.Group',
        on_delete=models.CASCADE,
        null=True, blank=True,
        related_name='assignments'
    )
    
    # Student (Public Schemada bo'lgani uchun UUID ishlatamiz!)
    student_id = models.UUIDField(null=True, blank=True, db_index=True)
    
    # Creator (Public Schemada bo'lgani uchun UUID!)
    assigned_by_id = models.UUIDField(null=True, blank=True)

    # --- DETAILS ---
    title = models.CharField(max_length=255, blank=True, help_text=_("Custom title (e.g. 'N5 Final Exam')"))
    instructions = models.TextField(blank=True)
    
    # --- TIMING ---
    # Rejalashtirilgan vaqt (O'quvchiga ko'rinadi: "9:00 da bo'ladi")
    scheduled_start = models.DateTimeField(_('scheduled start'))
    
    # Haqiqiy boshlangan vaqt (O'qituvchi tugmani bosganda yoziladi)
    actual_start = models.DateTimeField(_('actual start'), null=True, blank=True)
    
    # Tugash muddati (Deadline)
    deadline = models.DateTimeField(_('deadline'), null=True, blank=True)
    
    # Status
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.SCHEDULED, db_index=True)

    # --- SETTINGS ---
    allow_retake = models.BooleanField(default=False)
    max_attempts = models.PositiveIntegerField(default=1)
    
    show_score_immediately = models.BooleanField(default=False) 
    show_answers_after_submit = models.BooleanField(default=False)
    
    randomize_questions = models.BooleanField(default=False)
    
    # --- STATS (Denormalization) ---
    total_assigned_students = models.PositiveIntegerField(default=0)
    submitted_count = models.PositiveIntegerField(default=0)
    average_score = models.DecimalField(max_digits=5, decimal_places=2, default=0)

    class Meta:
        db_table = 'assignments'
        ordering = ['-scheduled_start']
        indexes = [
            models.Index(fields=['status', 'scheduled_start']),
        ]

    def __str__(self):
        # Nomini aniqlash (Mock yoki Quiz)
        content_name = "Unknown"
        if self.mock_test:
            content_name = self.mock_test.title
        elif self.quiz:
            content_name = f"Quiz: {self.quiz.title}"
            
        target = self.group.name if self.group else "Student"
        return f"{content_name} → {target} ({self.status})"

    def clean(self):
        # 1. Target validation (Guruh yoki Student)
        if self.assignment_type == self.AssignmentType.GROUP and not self.group:
            raise ValidationError("Group assignment must have a group.")
        if self.assignment_type == self.AssignmentType.INDIVIDUAL and not self.student_id:
            raise ValidationError("Individual assignment must have a student_id.")
            
        # 2. Content validation (MockTest yoki Quiz - XOR logic)
        if not self.mock_test and not self.quiz:
            raise ValidationError("Assignment must have either a MockTest or a Quiz.")
        
        if self.mock_test and self.quiz:
            raise ValidationError("Assignment cannot have both MockTest and Quiz.")

    def start_exam(self):
        """O'qituvchi imtihonni boshlaganda chaqiriladi"""
        if self.status == self.Status.SCHEDULED:
            self.status = self.Status.IN_PROGRESS
            self.actual_start = timezone.now()
            self.save()
            
    def close_exam(self):
        """Imtihonni tugatish"""
        self.status = self.Status.COMPLETED
        self.save()