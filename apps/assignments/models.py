# apps/assignments/models.py
from django.db import models
from django.utils.translation import gettext_lazy as _
from django.core.exceptions import ValidationError
from django.contrib.postgres.fields import ArrayField
from apps.core.models import TenantBaseModel

class ExamAssignment(TenantBaseModel):
    class RoomStatus(models.TextChoices):
        OPEN = 'OPEN', ('Open')
        CLOSED = 'CLOSED', ('Closed')

    title = models.CharField(max_length=255)
    description = models.TextField(blank=True)

    mock_test = models.ForeignKey(
        "mock_tests.MockTest", 
        on_delete=models.SET_NULL,
        null=True, related_name="exam_assignments",
        help_text="mock_test should be required field in the serializer"
    )

    status = models.CharField(
        max_length=20, 
        choices=RoomStatus.choices, 
        default=RoomStatus.CLOSED,
        help_text="Teacher/CenterAdmin controls this. 'OPEN' means students can see their assignments in exam roompage"
    )

    estimated_start_time = models.DateTimeField(
        null=True, 
        blank=True,
        help_text="Informational start time. Does not automatically open the exam."
    )

    assigned_groups = models.ManyToManyField("groups.Group", blank=True, related_name="exam_tasks"
    )

    is_published = models.BooleanField(
        default=False, 
        help_text="If False, student sees 'Submitted'. If True, student sees scores."
    )

    created_by_id = models.BigIntegerField(
        null=True, blank=True, db_index=True
    )

    class Meta:
        db_table = 'exam_assignments'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['status', 'created_at']),
        ]

    def __str__(self):
        return f"[Exam] {self.title} ({self.status})"

    def clean(self):
        # NOTE: M2M validation (assigned_groups) moved to Serializer
        if not self.title:
            raise ValidationError("Title is required.")
        
        # LOGIC FIX: Only PUBLISHED tests can be assigned
        if self.mock_test:
            if self.mock_test.status != "PUBLISHED":
                raise ValidationError("Only PUBLISHED mock tests can be assigned.")
            
            if self.mock_test.deleted_at is not None:
                raise ValidationError("Deleted mock_test cannot be assigned.")

    @property
    def created_by(self):
        """
        Get User object from public schema by created_by_id.
        Returns None if created_by_id is not set or user doesn't exist.
        """
        if self.created_by_id:
            try:
                from apps.core.tenant_utils import get_public_user_by_id
                return get_public_user_by_id(self.created_by_id)
            except Exception:
                return None
        return None

    
    
class HomeworkAssignment(TenantBaseModel):
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    deadline = models.DateTimeField()

    mock_test = models.ForeignKey(
        "mock_tests.MockTest", 
        on_delete=models.SET_NULL,
        null=True, 
        related_name="homework_assignments",
        help_text="mock_test should be required field in the serializer"
    )
    
    created_by_id = models.BigIntegerField(
        null=True, blank=True, db_index=True
    )
    assigned_groups = models.ManyToManyField(
        "groups.Group", 
        blank=True, 
        related_name="assigned_homework_tasks"
    )
    assigned_user_ids = ArrayField(
        models.BigIntegerField(),
        blank=True,
        default=list,
        help_text="List of User IDs (Guests/Students) assigned individually"
    )
    show_results_immediately = models.BooleanField(default=True)

    class Meta:
        ordering = ['-deadline']
        indexes = [
            models.Index(fields=['deadline', 'created_at']),
        ]
        db_table = 'homework_assignments'

    def __str__(self):
        return f"[Homework] {self.title} (Due: {self.deadline.date()})"

    def clean(self):
        if not self.title:
            raise ValidationError("Title is required.")
            
        # LOGIC FIX: Only PUBLISHED tests
        if self.mock_test:
            if self.mock_test.status != "PUBLISHED":
                raise ValidationError("Only PUBLISHED mock tests can be assigned.")
            
            if self.mock_test.deleted_at is not None:
                raise ValidationError("Deleted mock_test cannot be assigned.")

    @property
    def created_by(self):
        if self.created_by_id:
            try:
                from apps.core.tenant_utils import get_public_user_by_id
                return get_public_user_by_id(self.created_by_id)
            except Exception:
                return None
        return None