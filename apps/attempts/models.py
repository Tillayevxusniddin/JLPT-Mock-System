# apps/attempts/models.py

from django.db import models
from django.utils.translation import gettext_lazy as _
from django.core.validators import MinValueValidator, MaxValueValidator
from decimal import Decimal
from apps.core.models import TenantBaseModel


class Submission(TenantBaseModel):
    """
    Submission model for exam and homework attempts.
    
    Represents a student's attempt at a MockTest through an ExamAssignment or HomeworkAssignment.
    """
    class Status(models.TextChoices):
        STARTED = 'STARTED', _('Started')
        SUBMITTED = 'SUBMITTED', _('Submitted')
        GRADED = 'GRADED', _('Graded')

    user_id = models.BigIntegerField(
        db_index=True,
        help_text="Public User ID (from authentication.User)"
    )
    
    exam_assignment = models.ForeignKey(
        "assignments.ExamAssignment",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="submissions",
        help_text="FK to ExamAssignment (nullable, mutually exclusive with homework_assignment)"
    )
    
    homework_assignment = models.ForeignKey(
        "assignments.HomeworkAssignment",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="submissions",
        help_text="FK to HomeworkAssignment (nullable, mutually exclusive with exam_assignment)"
    )
    
    # For homework submissions, link to specific MockTest or Quiz
    mock_test = models.ForeignKey(
        "mock_tests.MockTest",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="submissions",
        help_text="FK to MockTest (for homework submissions, mutually exclusive with quiz)"
    )
    
    quiz = models.ForeignKey(
        "mock_tests.Quiz",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="submissions",
        help_text="FK to Quiz (for homework submissions, mutually exclusive with mock_test)"
    )
    
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.STARTED,
        db_index=True
    )
    
    started_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When the student started the exam"
    )
    
    completed_at = models.DateTimeField(
        null=True,
        blank=True,
        db_index=True,
        help_text="When the student submitted the exam"
    )
    
    score = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal('0.00'))],
        help_text="Total score acquired (0-180 for JLPT)"
    )
    
    # JSONField structure: {"question_uuid": selected_option_index}
    # Example: {"550e8400-e29b-41d4-a716-446655440000": 2, "660e8400-e29b-41d4-a716-446655440001": 0}
    # where the key is the Question.id (UUID) and value is the 0-based index of the selected option
    answers = models.JSONField(
        default=dict,
        blank=True,
        help_text="Student's raw answers snapshot: {question_uuid: selected_option_index}"
    )
    
    # JSONField structure for detailed grading results
    # Example:
    # {
    #   "total_score": 95.5,
    #   "sections": {
    #     "section_uuid_1": {
    #       "section_name": "Vocabulary",
    #       "section_type": "VOCAB",
    #       "score": 25.5,
    #       "max_score": 60,
    #       "questions": {
    #         "question_uuid_1": {"correct": true, "score": 1.0},
    #         "question_uuid_2": {"correct": false, "score": 0.0}
    #       }
    #     }
    #   },
    #   "jlpt_result": {
    #     "level": "N2",
    #     "total_score": 95.5,
    #     "pass_mark": 90,
    #     "passed": true,
    #     "section_results": {
    #       "language_knowledge": {"score": 25.5, "min_required": 19, "passed": true},
    #       "reading": {"score": 35.0, "min_required": 19, "passed": true},
    #       "listening": {"score": 35.0, "min_required": 19, "passed": true}
    #     }
    #   }
    # }
    results = models.JSONField(
        default=dict,
        blank=True,
        help_text="Detailed grading result with section breakdown and JLPT pass/fail logic"
    )
    
    # JSONField structure: Complete snapshot of MockTest/Quiz at time of submission
    # This preserves the exact state of the test (including correct answers) for historical integrity
    # Structure matches the full serialized MockTest/Quiz with all nested data
    # Example for MockTest:
    # {
    #   "resource_type": "mock_test",
    #   "id": "uuid",
    #   "title": "...",
    #   "level": "N2",
    #   "sections": [
    #     {
    #       "id": "uuid",
    #       "name": "Vocabulary",
    #       "question_groups": [
    #         {
    #           "id": "uuid",
    #           "questions": [
    #             {
    #               "id": "uuid",
    #               "text": "...",
    #               "options": [{"id": 1, "text": "...", "is_correct": true}, ...],
    #               "correct_option_index": 0,
    #               "score": 1
    #             }
    #           ]
    #         }
    #       ]
    #     }
    #   ]
    # }
    # Example for Quiz:
    # {
    #   "resource_type": "quiz",
    #   "id": "uuid",
    #   "title": "...",
    #   "questions": [
    #     {
    #       "id": "uuid",
    #       "text": "...",
    #       "options": [{"id": 1, "text": "...", "is_correct": true}, ...],
    #       "correct_option_index": 0,
    #       "points": 1
    #     }
    #   ]
    # }
    snapshot = models.JSONField(
        default=dict,
        blank=True,
        help_text="Complete snapshot of MockTest/Quiz structure (including correct answers) at time of grading. Preserves historical integrity."
    )

    class Meta:
        db_table = 'submissions'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['user_id', 'status']),
            models.Index(fields=['exam_assignment', 'user_id']),
            models.Index(fields=['homework_assignment', 'user_id']),
            models.Index(fields=['homework_assignment', 'mock_test', 'user_id']),
            models.Index(fields=['homework_assignment', 'quiz', 'user_id']),
            models.Index(fields=['status', 'completed_at']),
        ]
        constraints = [
            # Ensure only one of exam_assignment or homework_assignment is set
            models.CheckConstraint(
                check=(
                    models.Q(exam_assignment__isnull=False, homework_assignment__isnull=True) |
                    models.Q(exam_assignment__isnull=True, homework_assignment__isnull=False)
                ),
                name='submission_exactly_one_assignment'
            ),
            # For homework: ensure only one of mock_test or quiz is set
            models.CheckConstraint(
                check=(
                    models.Q(homework_assignment__isnull=True) |  # Not homework, no constraint
                    models.Q(
                        homework_assignment__isnull=False,
                        mock_test__isnull=False,
                        quiz__isnull=True
                    ) |  # Homework with MockTest
                    models.Q(
                        homework_assignment__isnull=False,
                        mock_test__isnull=True,
                        quiz__isnull=False
                    )  # Homework with Quiz
                ),
                name='submission_homework_exactly_one_resource'
            ),
            # Ensure one attempt per user per exam assignment
            models.UniqueConstraint(
                fields=['user_id', 'exam_assignment'],
                condition=models.Q(exam_assignment__isnull=False),
                name='unique_user_exam_assignment'
            ),
            # Ensure one attempt per user per homework item (homework_assignment + mock_test/quiz)
            models.UniqueConstraint(
                fields=['user_id', 'homework_assignment', 'mock_test'],
                condition=models.Q(homework_assignment__isnull=False, mock_test__isnull=False),
                name='unique_user_homework_mocktest'
            ),
            models.UniqueConstraint(
                fields=['user_id', 'homework_assignment', 'quiz'],
                condition=models.Q(homework_assignment__isnull=False, quiz__isnull=False),
                name='unique_user_homework_quiz'
            ),
        ]

    def __str__(self):
        assignment_type = "Exam" if self.exam_assignment else "Homework"
        assignment_id = self.exam_assignment_id if self.exam_assignment else self.homework_assignment_id
        return f"Submission {self.id} - User {self.user_id} - {assignment_type} {assignment_id} ({self.status})"

    @property
    def assignment(self):
        """Get the assignment (exam or homework) associated with this submission."""
        return self.exam_assignment or self.homework_assignment

    @property
    def resource(self):
        """Get the resource (MockTest or Quiz) associated with this submission."""
        if self.exam_assignment and self.exam_assignment.mock_test:
            return self.exam_assignment.mock_test
        elif self.mock_test:
            return self.mock_test
        elif self.quiz:
            return self.quiz
        return None
    
    @property
    def resource_type(self):
        """Get the type of resource: 'mock_test' or 'quiz'."""
        if self.exam_assignment and self.exam_assignment.mock_test:
            return 'mock_test'
        elif self.mock_test:
            return 'mock_test'
        elif self.quiz:
            return 'quiz'
        return None
