"""
Attempts Models - Student test attempts and answers
"""
from django.db import models
from django.utils.translation import gettext_lazy as _
from django.db.models import Q, Sum, Count

from apps.core.models import TenantBaseModel


class Attempt(TenantBaseModel):
    """
    Student's Attempt at a Mock Test
    """
    
    class Status(models.TextChoices):
        NOT_STARTED = 'NOT_STARTED', _('Not Started')
        IN_PROGRESS = 'IN_PROGRESS', _('In Progress')
        SUBMITTED = 'SUBMITTED', _('Submitted')
        GRADED = 'GRADED', _('Graded')
        EXPIRED = 'EXPIRED', _('Expired')
    
    # Assignment
    assignment = models.ForeignKey(
        'assignments.Assignment',
        on_delete=models.CASCADE,
        related_name='attempts'
    )
    
    # Student
    student = models.ForeignKey(
        'authentication.User',
        on_delete=models.CASCADE,
        related_name='attempts',
        limit_choices_to={'role': 'STUDENT'}
    )
    
    # Attempt number (for retakes)
    attempt_number = models.PositiveIntegerField(_('attempt number'), default=1)
    
    # Timing
    started_at = models.DateTimeField(_('started at'), null=True, blank=True)
    submitted_at = models.DateTimeField(_('submitted at'), null=True, blank=True)
    time_spent_seconds = models.PositiveIntegerField(
        _('time spent (seconds)'),
        default=0
    )
    
    # Status
    status = models.CharField(
        _('status'),
        max_length=20,
        choices=Status.choices,
        default=Status.NOT_STARTED,
        db_index=True
    )
    
    # Overall Scores
    total_score = models.PositiveIntegerField(_('total score'), default=0)
    max_score = models.PositiveIntegerField(_('maximum score'), default=180)
    percentage_score = models.DecimalField(
        _('percentage score'),
        max_digits=5,
        decimal_places=2,
        default=0
    )
    passed = models.BooleanField(_('passed'), default=False, db_index=True)
    
    # Mondai-type scores (each out of 60 for standard JLPT)
    moji_goi_score = models.PositiveIntegerField(
        _('vocabulary score'),
        default=0,
        help_text=_('Score for Moji-goi section')
    )
    bunpou_score = models.PositiveIntegerField(
        _('grammar score'),
        default=0,
        help_text=_('Score for Bunpou section')
    )
    dokkai_score = models.PositiveIntegerField(
        _('reading score'),
        default=0,
        help_text=_('Score for Dokkai section')
    )
    choukai_score = models.PositiveIntegerField(
        _('listening score'),
        default=0,
        help_text=_('Score for Choukai section')
    )
    
    # Time tracking per section
    moji_goi_time_seconds = models.PositiveIntegerField(
        _('vocabulary time (seconds)'),
        default=0
    )
    bunpou_time_seconds = models.PositiveIntegerField(
        _('grammar time (seconds)'),
        default=0
    )
    dokkai_time_seconds = models.PositiveIntegerField(
        _('reading time (seconds)'),
        default=0
    )
    choukai_time_seconds = models.PositiveIntegerField(
        _('listening time (seconds)'),
        default=0
    )
    
    # Grading & Feedback
    auto_graded = models.BooleanField(_('auto graded'), default=True)
    reviewed_by = models.ForeignKey(
        'authentication.User',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='reviewed_attempts',
        limit_choices_to={'role__in': ['TEACHER', 'CENTERADMIN']}
    )
    reviewed_at = models.DateTimeField(_('reviewed at'), null=True, blank=True)
    teacher_feedback = models.TextField(_('teacher feedback'), blank=True)
    
    # Answer statistics
    correct_answers = models.PositiveIntegerField(_('correct answers'), default=0)
    total_questions = models.PositiveIntegerField(_('total questions'), default=0)
    
    # Device info
    user_agent = models.TextField(_('user agent'), blank=True)
    ip_address = models.GenericIPAddressField(_('IP address'), null=True, blank=True)
    
    class Meta:
        db_table = 'attempts'
        verbose_name = _('attempt')
        verbose_name_plural = _('attempts')
        ordering = ['-started_at']
        unique_together = [['assignment', 'student', 'attempt_number']]
        indexes = [
            models.Index(fields=['student', 'status']),
            models.Index(fields=['assignment', 'student']),
            models.Index(fields=['status', 'submitted_at']),
            models.Index(fields=['passed', 'submitted_at']),
        ]
    
    def __str__(self):
        return f"Attempt #{self.attempt_number} by {self.student.get_full_name()}"
    
    def calculate_scores(self):
        """Calculate and update all scores"""
        # Get all answers for this attempt
        answers = self.answers.aggregate(
            total=Count('id'),
            correct=Count('id', filter=Q(is_correct=True)),
            points=Sum('points_earned')
        )
        
        self.total_questions = answers['total'] or 0
        self.correct_answers = answers['correct'] or 0
        self.total_score = answers['points'] or 0
        
        # Calculate percentage
        if self.max_score > 0:
            self.percentage_score = (self.total_score / self.max_score) * 100
        
        # Check if passed
        passing_score = self.assignment.mock_test.passing_score
        self.passed = self.total_score >= passing_score
        
        # Calculate section scores
        self._calculate_section_scores()
        
        self.save(update_fields=[
            'total_questions', 'correct_answers', 'total_score',
            'percentage_score', 'passed',
            'moji_goi_score', 'bunpou_score', 'dokkai_score', 'choukai_score',
            'updated_at'
        ])
    
    def _calculate_section_scores(self):
        """Calculate scores for each mondai type"""
        from apps.mock_tests.models import Mondai
        
        # Moji-goi
        self.moji_goi_score = self.answers.filter(
            question__mondai__mondai_type=Mondai.MondaiType.MOJI_GOI,
            is_correct=True
        ).aggregate(Sum('points_earned'))['points_earned__sum'] or 0
        
        # Bunpou
        self.bunpou_score = self.answers.filter(
            question__mondai__mondai_type=Mondai.MondaiType.BUNPOU,
            is_correct=True
        ).aggregate(Sum('points_earned'))['points_earned__sum'] or 0
        
        # Dokkai
        self.dokkai_score = self.answers.filter(
            question__mondai__mondai_type=Mondai.MondaiType.DOKKAI,
            is_correct=True
        ).aggregate(Sum('points_earned'))['points_earned__sum'] or 0
        
        # Choukai
        self.choukai_score = self.answers.filter(
            question__mondai__mondai_type=Mondai.MondaiType.CHOUKAI,
            is_correct=True
        ).aggregate(Sum('points_earned'))['points_earned__sum'] or 0


class Answer(TenantBaseModel):
    """
    Student's Answer to a Question
    """
    
    # Attempt
    attempt = models.ForeignKey(
        Attempt,
        on_delete=models.CASCADE,
        related_name='answers'
    )
    
    # Question
    question = models.ForeignKey(
        'mock_tests.Question',
        on_delete=models.CASCADE,
        related_name='student_answers'
    )
    
    # Selected choice (1, 2, 3, or 4)
    selected_choice = models.ForeignKey(
        'mock_tests.Choice',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='selected_by'
    )
    
    # Grading
    is_correct = models.BooleanField(_('correct'), default=False, db_index=True)
    points_earned = models.PositiveIntegerField(_('points earned'), default=0)
    max_points = models.PositiveIntegerField(_('maximum points'), default=1)
    
    # Timing
    answered_at = models.DateTimeField(_('answered at'), auto_now_add=True)
    time_spent_seconds = models.PositiveIntegerField(
        _('time spent (seconds)'),
        default=0
    )
    
    # Flags
    is_marked_for_review = models.BooleanField(
        _('marked for review'),
        default=False,
        help_text=_('Student flagged this question to review later')
    )
    is_skipped = models.BooleanField(
        _('skipped'),
        default=False,
        help_text=_('Student skipped this question')
    )
    
    class Meta:
        db_table = 'answers'
        verbose_name = _('answer')
        verbose_name_plural = _('answers')
        ordering = ['attempt', 'question__order']
        unique_together = [['attempt', 'question']]
        indexes = [
            models.Index(fields=['attempt', 'is_correct']),
            models.Index(fields=['question', 'is_correct']),
        ]
    
    def __str__(self):
        return f"Answer to Q{self.question.question_number}"
    
    def grade(self):
        """Auto-grade the answer"""
        if self.selected_choice:
            self.is_correct = self.selected_choice.is_correct
            self.points_earned = self.max_points if self.is_correct else 0
            self.save(update_fields=['is_correct', 'points_earned', 'updated_at'])
        else:
            # No answer selected
            self.is_correct = False
            self.points_earned = 0
            self.is_skipped = True
            self.save(update_fields=['is_correct', 'points_earned', 'is_skipped', 'updated_at'])