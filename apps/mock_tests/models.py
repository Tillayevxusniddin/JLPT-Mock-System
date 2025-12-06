"""
Mock Tests Models - JLPT Mock Test System
Structure: MockTest -> TestSection -> QuestionGroup (Mondai) -> Question -> Choice
"""
from django.db import models
from django.utils.translation import gettext_lazy as _
from django.core.validators import MinValueValidator, MaxValueValidator
from apps.core.models import TenantBaseModel

class MockTest(TenantBaseModel):
    """
    Mock Test (Ex: JLPT N5 Full Test 1)
    """
    class Level(models.TextChoices):
        N5 = 'N5', 'N5 - Beginner'
        N4 = 'N4', 'N4 - Elementary'
        N3 = 'N3', 'N3 - Intermediate'
        N2 = 'N2', 'N2 - Upper Intermediate'
        N1 = 'N1', 'N1 - Advanced'

    class Status(models.TextChoices):
        DRAFT = 'DRAFT', _('Draft')
        PUBLISHED = 'PUBLISHED', _('Published')
        ARCHIVED = 'ARCHIVED', _('Archived')

    title = models.CharField(max_length=255)
    level = models.CharField(max_length=2, choices=Level.choices, db_index=True)
    description = models.TextField(blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT)
    
    # Creator info (User ID saqlaymiz, chunki User Public Schemada)
    created_by_id = models.UUIDField(null=True, blank=True)

    # Scoring config
    pass_score = models.PositiveIntegerField(default=90) # Umumiy o'tish bali
    total_score = models.PositiveIntegerField(default=180) # Jami ball

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
        VOCAB = 'VOCAB', _('Vocabulary (Moji-Goi)')
        GRAMMAR_READING = 'GRAMMAR_READING', _('Grammar & Reading')
        LISTENING = 'LISTENING', _('Listening (Choukai)')
        FULL_WRITTEN = 'FULL_WRITTEN', _('Vocabulary, Grammar & Reading (N1/N2)')

    mock_test = models.ForeignKey(MockTest, on_delete=models.CASCADE, related_name='sections')
    name = models.CharField(max_length=255) # "Gengo Chishiki", "Choukai"
    section_type = models.CharField(max_length=20, choices=SectionType.choices)
    
    duration = models.PositiveIntegerField(help_text="Duration in minutes")
    order = models.PositiveIntegerField(default=1) # 1, 2, 3...
    
    total_score = models.PositiveIntegerField(default=60) # Bo'lim bali (odatda 60)

    class Meta:
        db_table = 'test_sections'
        ordering = ['order']
        
    def __str__(self):
        return f"{self.mock_test.title} - {self.name}"

class QuestionGroup(TenantBaseModel):
    """
    Savollar Guruhi (Mondai).
    Bitta matn yoki audio uchun bir nechta savol bo'lishi mumkin.
    """
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
    """
    Aniq bitta savol.
    """
    group = models.ForeignKey(QuestionGroup, on_delete=models.CASCADE, related_name='questions')
    
    text = models.TextField(blank=True) # Savol matni
    question_number = models.PositiveIntegerField(default=1) # 1, 2, 3...
    
    # Agar savolga xos alohida rasm yoki audio bo'lsa
    image = models.ImageField(upload_to='question_images/', blank=True, null=True)
    audio_file = models.FileField(upload_to='question_audios/', blank=True, null=True)
    
    score = models.PositiveIntegerField(default=1) # Ball
    order = models.PositiveIntegerField(default=1)

    class Meta:
        db_table = 'questions'
        ordering = ['group', 'order']

    def __str__(self):
        return f"Q{self.question_number}: {self.text[:30]}"

class Choice(TenantBaseModel):
    """
    Javob varianti.
    """
    question = models.ForeignKey(Question, on_delete=models.CASCADE, related_name='choices')
    text = models.CharField(max_length=255, blank=True)
    is_correct = models.BooleanField(default=False)
    order = models.PositiveIntegerField(default=1) # 1, 2, 3, 4

    class Meta:
        db_table = 'choices'
        ordering = ['order']




class Quiz(TenantBaseModel):
    """
    Kahoot-style Quiz. 
    Tezkor, sodda va qiziqarli.
    """
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    
    # Creator
    created_by_id = models.UUIDField(null=True, blank=True)
    
    # Settings
    is_active = models.BooleanField(default=True)
    
    # Default vaqt (agar savolda alohida ko'rsatilmasa, masalan 20 soniya)
    default_question_duration = models.PositiveIntegerField(default=20, help_text="Seconds")
    
    class Meta:
        db_table = 'quizzes'
        ordering = ['-created_at']

    def __str__(self):
        return self.title


class QuizQuestion(TenantBaseModel):
    """
    Bitta savol ekrani.
    """
    class QuestionType(models.TextChoices):
        QUIZ = 'QUIZ', _('Quiz (4 options)')
        TRUE_FALSE = 'TRUE_FALSE', _('True or False')

    quiz = models.ForeignKey(Quiz, on_delete=models.CASCADE, related_name='questions')
    
    text = models.CharField(max_length=500) # Savol qisqa bo'lishi kerak
    question_type = models.CharField(max_length=20, choices=QuestionType.choices, default=QuestionType.QUIZ)
    
    # Media (Kahootda rasm muhim)
    image = models.ImageField(upload_to='quiz_images/', blank=True, null=True)
    
    # Shu savol uchun vaqt (Soniya) - Kahoot logikasi
    duration = models.PositiveIntegerField(default=20, help_text="Seconds")
    
    # Ball (Odatda 1000, biz sodda 100 yoki 1 qilamiz)
    points = models.PositiveIntegerField(default=1)
    
    order = models.PositiveIntegerField(default=1)

    class Meta:
        db_table = 'quiz_questions'
        ordering = ['order']

    def __str__(self):
        return f"{self.text[:30]}"


class QuizOption(TenantBaseModel):
    """
    Rangli variantlar.
    """
    question = models.ForeignKey(QuizQuestion, on_delete=models.CASCADE, related_name='options')
    text = models.CharField(max_length=255)
    is_correct = models.BooleanField(default=False)
    order = models.PositiveIntegerField(default=1)

    class Meta:
        db_table = 'quiz_options'
        ordering = ['order']