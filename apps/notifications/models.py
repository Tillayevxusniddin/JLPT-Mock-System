#apps/notifications/models.py
from django.db import models
from apps.core.models import TenantBaseModel


class Notification(TenantBaseModel):
    """
    Notification model for real-time user notifications.
    
    Multi-tenant isolation:
    - Inherits from TenantBaseModel (lives in tenant schema)
    - NO center field (schema provides isolation)
    - All notifications are strictly scoped to the tenant
    """
    
    class NotificationType(models.TextChoices):
        # Student notifications
        TASK_ASSIGNED = "TASK_ASSIGNED", "Task Assigned"  # Homework assigned
        EXAM_OPENED = "EXAM_OPENED", "Exam Room Opened"  # Exam status -> OPEN
        SUBMISSION_GRADED = "SUBMISSION_GRADED", "Submission Graded"  # Homework auto/manual graded
        EXAM_PUBLISHED = "EXAM_PUBLISHED", "Exam Results Published"  # Exam results released
        DEADLINE_APPROACHING = "DEADLINE_APPROACHING", "Deadline Approaching"
        DEADLINE_MISSED = "DEADLINE_MISSED", "Deadline Missed"
        
        # Teacher notifications
        NEW_SUBMISSION = "NEW_SUBMISSION", "New Submission"  # Student submitted homework
        REVIEW_OVERDUE = "REVIEW_OVERDUE", "Review Overdue"  # Homework waiting grading > 48h
        
        # General notifications
        INVITATION_APPROVED = "INVITATION_APPROVED", "Invitation Approved"
        GROUP_ADDED = "GROUP_ADDED", "Added to Group"
        ASSIGNED_TO_GROUP = "ASSIGNED_TO_GROUP", "Assigned to Group"
        ASSIGNED_TO_TASK = "ASSIGNED_TO_TASK", "Assigned to Task"
        STUDENT_APPROVED = "STUDENT_APPROVED", "Student Approved"
        PENDING_APPROVAL = "PENDING_APPROVAL", "User Waiting for Approval"
        CONTACT_REQUEST = "CONTACT_REQUEST", "Contact Request Received"
        ANNOUNCEMENT = "ANNOUNCEMENT", "Announcement"
    
    # Cross-schema FK replacement: User is in Public schema
    user_id = models.BigIntegerField(db_index=True)
    
    notification_type = models.CharField(
        max_length=50,
        choices=NotificationType.choices,
        default=NotificationType.ANNOUNCEMENT,
        db_index=True,
        help_text="Type of notification for filtering and display"
    )
    message = models.TextField()
    is_read = models.BooleanField(default=False, db_index=True)
    link = models.URLField(null=True, blank=True, help_text="Optional link to related resource (e.g., /tasks/{id})")
    
    # Optional: Store related object IDs for frontend navigation
    related_task_id = models.UUIDField(null=True, blank=True, db_index=True)
    related_submission_id = models.UUIDField(null=True, blank=True, db_index=True)
    related_group_id = models.UUIDField(null=True, blank=True, db_index=True)
    related_contact_request_id = models.UUIDField(null=True, blank=True, db_index=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            # Index for unread notifications query
            models.Index(fields=['user_id', 'is_read', '-created_at']),
            # Index for notification type filtering
            models.Index(fields=['user_id', 'notification_type', '-created_at']),
        ]

    def __str__(self) -> str:  # pragma: no cover
        return f"Notification to {self.user_id}: {self.message[:40]}"

    @property
    def user(self):
        """Fetch the User object from the public schema."""
        if self.user_id:
            from apps.accounts.models import User
            from apps.core.tenant_utils import with_public_schema
            try:
                return with_public_schema(lambda: User.objects.get(id=self.user_id))
            except User.DoesNotExist:
                return None
        return None