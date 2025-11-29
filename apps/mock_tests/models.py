"""
Mock Tests Models - JLPT Mock Test System (SIMPLIFIED)
Structure: Level -> Mondai -> Question
"""
from django.db import models
from django.utils.translation import gettext_lazy as _
from django.core.validators import MinValueValidator, MaxValueValidator

from apps.core.models import TenantBaseModel


class MockTest(TenantBaseModel):
    """
    JLPT Mock Test
    Container for all mondais
    """
    
    class Status(models.TextChoices):
        DRAFT = 'DRAFT', _('Draft')
        PUBLISHED = 'PUBLISHED', _('Published')
        ARCHIVED = 'ARCHIVED', _('Archived')
    
    # Basic Info
    title = models.CharField(_('test title'), max_length=255)
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
    
    # Creator
    created_by = models.ForeignKey(
        'authentication.User',
        on_delete=models.SET_NULL,
        null=True,
        related_name='created_tests',
        limit_choices_to={'role__in': ['TEACHER', 'CENTERADMIN']}
    )
    
    # Status
    status = models.CharField(
        _('status'),
        max_length=20,
        choices=Status.choices,
        default=Status.DRAFT,
        db_index=True
    )
    
    # Timing (in minutes)
    total_duration_minutes = models.PositiveIntegerField(
        _('total duration (minutes)'),
        help_text=_('Total test duration based on JLPT standards')
    )
    
    # Scoring
    passing_score = models.PositiveIntegerField(
        _('passing score'),
        default=100,
        validators=[MinValueValidator(0), MaxValueValidator(180)],
        help_text=_('Minimum score to pass (out of 180)')
    )
    
    # Cached counts
    total_mondais = models.PositiveIntegerField(_('total mondais'), default=0)
    total_questions = models.PositiveIntegerField(_('total questions'), default=0)
    
    # Instructions
    instructions = models.TextField(_('instructions'), blank=True)
    
    class Meta:
        db_table = 'mock_tests'
        verbose_name = _('mock test')
        verbose_name_plural = _('mock tests')
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['organization_id', 'level', 'status']),
            models.Index(fields=['created_by', 'status']),
        ]
    
    def __str__(self):
        return f"{self.title} ({self.level})"


class Mondai(TenantBaseModel):
    """
    Mondai (問題) - Question Set/Section
    Groups similar questions together
    Examples: 
    - N5 Dokkai Mondai 1 (Reading)
    - N5 Choukai Mondai 2 (Listening)
    - N4 Moji-goi Mondai 1 (Vocabulary)
    """
    
    class MondaiType(models.TextChoices):
        MOJI_GOI = 'MOJI_GOI', _('Moji-goi (文字・語彙) - Vocabulary')
        BUNPOU = 'BUNPOU', _('Bunpou (文法) - Grammar')
        DOKKAI = 'DOKKAI', _('Dokkai (読解) - Reading')
        CHOUKAI = 'CHOUKAI', _('Choukai (聴解) - Listening')
    
    # Parent test
    mock_test = models.ForeignKey(
        MockTest,
        on_delete=models.CASCADE,
        related_name='mondais'
    )
    
    # Basic Info
    mondai_number = models.PositiveIntegerField(
        _('mondai number'),
        help_text=_('Mondai 1, Mondai 2, etc.')
    )
    title = models.CharField(
        _('title'),
        max_length=255,
        help_text=_('e.g., "Mondai 1: Kanji Reading"')
    )
    
    # Type
    mondai_type = models.CharField(
        _('mondai type'),
        max_length=20,
        choices=MondaiType.choices,
        db_index=True
    )
    
    # Instructions
    instructions = models.TextField(
        _('instructions'),
        help_text=_('Instructions for this mondai in Japanese/English')
    )
    
    # Shared content (for passages or audio that applies to multiple questions)
    shared_passage = models.TextField(
        _('shared passage'),
        blank=True,
        help_text=_('Text passage shared by all questions in this mondai')
    )
    shared_image = models.ImageField(
        _('shared image'),
        upload_to='mondais/images/%Y/%m/',
        blank=True,
        null=True
    )
    shared_audio = models.FileField(
        _('shared audio'),
        upload_to='mondais/audio/%Y/%m/',
        blank=True,
        null=True,
        help_text=_('Audio file for listening mondai')
    )
    
    # Duration for this mondai (optional)
    duration_minutes = models.PositiveIntegerField(
        _('duration (minutes)'),
        null=True,
        blank=True,
        help_text=_('Time allocated for this mondai')
    )
    
    # Order
    order = models.PositiveIntegerField(_('order'), default=0)
    
    # Cached count
    question_count = models.PositiveIntegerField(_('question count'), default=0)
    
    class Meta:
        db_table = 'mondais'
        verbose_name = _('mondai')
        verbose_name_plural = _('mondais')
        ordering = ['mock_test', 'order', 'mondai_number']
        unique_together = [['mock_test', 'mondai_number']]
        indexes = [
            models.Index(fields=['mock_test', 'order']),
            models.Index(fields=['mondai_type']),
        ]
    
    def __str__(self):
        return f"{self.title} - {self.get_mondai_type_display()}"


class Question(TenantBaseModel):
    """
    Individual Question
    Simple 4-choice multiple choice question
    """
    
    # Parent mondai
    mondai = models.ForeignKey(
        Mondai,
        on_delete=models.CASCADE,
        related_name='questions'
    )
    
    # Question number
    question_number = models.PositiveIntegerField(
        _('question number'),
        help_text=_('Question 1, 2, 3... within this mondai')
    )
    
    # Question content
    question_text = models.TextField(
        _('question text'),
        help_text=_('The main question text')
    )
    question_html = models.TextField(
        _('question HTML'),
        blank=True,
        help_text=_('HTML version with furigana using <ruby> tags')
    )
    
    # Optional image
    question_image = models.ImageField(
        _('question image'),
        upload_to='questions/images/%Y/%m/',
        blank=True,
        null=True
    )
    
    # For listening questions - individual audio
    audio_file = models.FileField(
        _('audio file'),
        upload_to='questions/audio/%Y/%m/',
        blank=True,
        null=True,
        help_text=_('Audio for this specific question')
    )
    
    # Individual passage (if not using shared_passage)
    passage_text = models.TextField(
        _('passage text'),
        blank=True,
        help_text=_('Individual passage for this question only')
    )
    
    # Order
    order = models.PositiveIntegerField(_('order'), default=0)
    
    # Points
    points = models.PositiveIntegerField(
        _('points'),
        default=1,
        help_text=_('How many points this question is worth')
    )
    
    # Explanation
    explanation = models.TextField(
        _('explanation'),
        blank=True,
        help_text=_('Explanation of the correct answer')
    )
    explanation_image = models.ImageField(
        _('explanation image'),
        upload_to='questions/explanations/%Y/%m/',
        blank=True,
        null=True
    )
    
    class Meta:
        db_table = 'questions'
        verbose_name = _('question')
        verbose_name_plural = _('questions')
        ordering = ['mondai', 'order', 'question_number']
        unique_together = [['mondai', 'question_number']]
        indexes = [
            models.Index(fields=['mondai', 'order']),
        ]
    
    def __str__(self):
        return f"Q{self.question_number}: {self.question_text[:50]}"


class Choice(TenantBaseModel):
    """
    Answer Choice for Multiple Choice Question
    Always 4 choices (1, 2, 3, 4)
    """
    
    # Parent question
    question = models.ForeignKey(
        Question,
        on_delete=models.CASCADE,
        related_name='choices'
    )
    
    # Choice number (1, 2, 3, 4)
    choice_number = models.PositiveIntegerField(
        _('choice number'),
        validators=[MinValueValidator(1), MaxValueValidator(4)]
    )
    
    # Choice content
    choice_text = models.CharField(
        _('choice text'),
        max_length=500,
        help_text=_('The answer choice text')
    )
    choice_html = models.TextField(
        _('choice HTML'),
        blank=True,
        help_text=_('HTML version with furigana')
    )
    
    # Optional image
    choice_image = models.ImageField(
        _('choice image'),
        upload_to='choices/%Y/%m/',
        blank=True,
        null=True
    )
    
    # Correct answer flag
    is_correct = models.BooleanField(
        _('correct answer'),
        default=False,
        db_index=True
    )
    
    # Order (usually same as choice_number)
    order = models.PositiveIntegerField(_('order'), default=0)
    
    class Meta:
        db_table = 'choices'
        verbose_name = _('choice')
        verbose_name_plural = _('choices')
        ordering = ['question', 'order', 'choice_number']
        unique_together = [['question', 'choice_number']]
        indexes = [
            models.Index(fields=['question', 'is_correct']),
        ]
        constraints = [
            models.CheckConstraint(
                check=models.Q(choice_number__gte=1, choice_number__lte=4),
                name='choice_number_range'
            )
        ]
    
    def __str__(self):
        correct = "✓" if self.is_correct else ""
        return f"{self.choice_number}. {self.choice_text[:30]} {correct}"