# apps/mock_tests/models.py
"""
Mock Tests Models - JLPT Mock Test System
Structure: MockTest -> TestSection -> QuestionGroup (Mondai) -> Question -> Choice
"""
from django.db import models
from django.utils.translation import gettext_lazy as _
from django.core.validators import MinValueValidator, MaxValueValidator
from apps.core.models import TenantBaseModel

class MockTest(TenantBaseModel):
    class Level(models.TextChoices):
        N5 = 'N5', 'N5 - Beginner'
        N4 = 'N4', 'N4 - Elementary'
        N3 = 'N3', 'N3 - Intermediate'
        N2 = 'N2', 'N2 - Upper Intermediate'
        N1 = 'N1', 'N1 - Advanced'

    class Status(models.TextChoices):
        DRAFT = 'DRAFT', ('Draft')
        PUBLISHED = 'PUBLISHED', ('Published')

    title = models.CharField(max_length=255)
    level = models.CharField(max_length=2, choices=Level.choices, db_index=True)
    description = models.TextField(blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT)
    created_by_id = models.BigIntegerField(null=True, blank=True)
    pass_score = models.PositiveIntegerField(default=90)
    total_score = models.PositiveIntegerField(default=180)

    class Meta:
        db_table = 'mock_tests'
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.title} ({self.level})"

class TestSection(TenantBaseModel):
    """
    Imtihon bo'limi (Vaqt shu yerda boshqariladi)
    N5: 1. Vocabulary (20min), 2. Grammar/Reading (40min), 3. Listening (30min)
    """
    class SectionType(models.TextChoices):
        VOCAB = 'VOCAB', ('Vocabulary (Moji-Goi)')
        GRAMMAR_READING = 'GRAMMAR_READING', ('Grammar & Reading')
        LISTENING = 'LISTENING', ('Listening (Choukai)')
        FULL_WRITTEN = 'FULL_WRITTEN', ('Vocabulary, Grammar & Reading (N1/N2)')

    mock_test = models.ForeignKey(MockTest, on_delete=models.CASCADE, related_name='sections')
    name = models.CharField(max_length=255)
    section_type = models.CharField(max_length=20, choices=SectionType.choices)
    duration = models.PositiveIntegerField(help_text="Duration in minutes")
    order = models.PositiveIntegerField(default=1)
    total_score = models.PositiveIntegerField(default=60)

    class Meta:
        db_table = 'test_sections'
        ordering = ['order']
        
    def __str__(self):
        return f"{self.mock_test.title} - {self.name}"

class QuestionGroup(TenantBaseModel):
    section = models.ForeignKey(TestSection, on_delete=models.CASCADE, related_name='question_groups')
    
    # Mondai raqami (Mondai 1, Mondai 2...)
    mondai_number = models.PositiveIntegerField(default=1)
    title = models.CharField(max_length=255, blank=True) # "Kanji Reading"
    
    # Yo'riqnoma (Instruction)
    instruction = models.TextField(blank=True)
    
    # Shared Content (Matn yoki Audio)
    reading_text = models.TextField(blank=True, null=True) # Reading uchun matn
    audio_file = models.FileField(upload_to='listening_audios/', blank=True, null=True) # Listening uchun
    image = models.ImageField(upload_to='group_images/', blank=True, null=True) # Diagramma
    
    order = models.PositiveIntegerField(default=1)

    class Meta:
        db_table = 'question_groups'
        ordering = ['section', 'order']

    def __str__(self):
        return f"Mondai {self.mondai_number}: {self.title}"

class Question(TenantBaseModel):
    group = models.ForeignKey(QuestionGroup, on_delete=models.CASCADE, related_name='questions')
    text = models.TextField(blank=True)
    question_number = models.PositiveIntegerField(default=1)
    image = models.ImageField(upload_to='question_images/', blank=True, null=True)
    audio_file = models.FileField(upload_to='question_audios/', blank=True, null=True)
    score = models.PositiveIntegerField(default=1)
    order = models.PositiveIntegerField(default=1)
    options = models.JSONField(default=list, help_text="List of options with is_correct flag")
    # [
    #   {"id": 1, "text": "Option A", "is_correct": false},
    #   {"id": 2, "text": "Option B", "is_correct": true},
    #   ...
    # ]
    correct_option_index = models.PositiveSmallIntegerField(
        help_text="Index of the correct option in the options list (0-based)",
        null=True, blank=True
    )
    class Meta:
        db_table = 'questions'
        ordering = ['group', 'order']

    def clean(self):
        if not self.options:
            return
            
        if not isinstance(self.options, list):
            raise ValidationError("Options must be a list")
            
        correct_count = sum(1 for opt in self.options if opt.get('is_correct'))
        if correct_count != 1:
            raise ValidationError("There must be exactly one correct option.")

    def save(self, *args, **kwargs):
        if self.options:
            for idx, opt in enumerate(self.options):
                if opt.get('is_correct'):
                    self.correct_option_index = idx
                    break
        super().save(*args, **kwargs)

    def __str__(self):
        return f"Q{self.question_number}: {self.text[:30]}"

class Quiz(TenantBaseModel):
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    created_by_id = models.BigIntegerField(null=True, blank=True)
    is_active = models.BooleanField(default=True)
    default_question_duration = models.PositiveIntegerField(default=20)
    
    class Meta:
        db_table = 'quizzes'
        ordering = ['-created_at']

    def __str__(self):
        return self.title

class QuizQuestion(TenantBaseModel):
    class QuestionType(models.TextChoices):
        QUIZ = 'QUIZ', ('Quiz (4 options)')
        TRUE_FALSE = 'TRUE_FALSE', ('True or False')

    quiz = models.ForeignKey(Quiz, on_delete=models.CASCADE, related_name='questions')
    text = models.CharField(max_length=500)
    question_type = models.CharField(max_length=20, choices=QuestionType.choices, default=QuestionType.QUIZ)
    image = models.ImageField(upload_to='quiz_images/', blank=True, null=True)
    duration = models.PositiveIntegerField(default=20)
    points = models.PositiveIntegerField(default=1)
    order = models.PositiveIntegerField(default=1)

    # OPTIMIZATION: QuizOption model o'rniga JSONField
    options = models.JSONField(default=list)
    correct_option_index = models.PositiveSmallIntegerField(null=True, blank=True)

    class Meta:
        db_table = 'quiz_questions'
        ordering = ['order']