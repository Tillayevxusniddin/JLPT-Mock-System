"""
Attempts Models - Separated logic for Mock Tests and Quizzes
"""
from django.db import models
from django.utils.translation import gettext_lazy as _
from apps.core.models import TenantBaseModel

# ==========================================
# 1. JLPT MOCK TEST ATTEMPTS
# ==========================================

class MockAttempt(TenantBaseModel):
    """
    Jiddiy imtihon urinishi (JLPT standarti).
    """
    class Status(models.TextChoices):
        IN_PROGRESS = 'IN_PROGRESS', _('In Progress')
        SUBMITTED = 'SUBMITTED', _('Submitted (Waiting for grading)')
        GRADED = 'GRADED', _('Graded (Published)')
        EXPIRED = 'EXPIRED', _('Expired (Time out)')

    # --- RELATIONS ---
    assignment = models.ForeignKey(
        'assignments.Assignment',
        on_delete=models.CASCADE,
        related_name='mock_attempts'
    )
    
    # User Public Schemada bo'lgani uchun UUID
    student_id = models.UUIDField(db_index=True)
    
    attempt_number = models.PositiveIntegerField(default=1)

    # --- TIMING ---
    started_at = models.DateTimeField(auto_now_add=True)
    submitted_at = models.DateTimeField(null=True, blank=True)
    
    # --- SCORES ---
    total_score = models.PositiveIntegerField(default=0) # Masalan: 120/180
    is_passed = models.BooleanField(default=False)
    
    # Section Scores (JLPT uchun)
    # { "vocab": 40, "grammar": 35, "listening": 45 }
    section_scores = models.JSONField(default=dict, blank=True)
    
    status = models.CharField(
        max_length=20, 
        choices=Status.choices, 
        default=Status.IN_PROGRESS, 
        db_index=True
    )

    class Meta:
        db_table = 'mock_attempts'
        ordering = ['-started_at']
        unique_together = [['assignment', 'student_id', 'attempt_number']]

    def __str__(self):
        return f"Mock Attempt #{self.attempt_number} - {self.student_id}"


class MockStudentAnswer(TenantBaseModel):
    """
    Mock Test savoliga javob.
    """
    attempt = models.ForeignKey(MockAttempt, on_delete=models.CASCADE, related_name='answers')
    
    # Faqat Mock Questionga bog'lanadi
    question = models.ForeignKey(
        'mock_tests.Question', 
        on_delete=models.CASCADE,
        related_name='student_answers'
    )
    
    # Tanlangan variant
    selected_choice = models.ForeignKey(
        'mock_tests.Choice',
        on_delete=models.CASCADE,
        null=True, blank=True
    )
    
    # Grading
    is_correct = models.BooleanField(default=False)
    score_obtained = models.PositiveIntegerField(default=0)
    
    # Review uchun (Teacher belgilab qo'yishi mumkin)
    is_flagged = models.BooleanField(default=False)

    class Meta:
        db_table = 'mock_student_answers'
        unique_together = [['attempt', 'question']]

    def __str__(self):
        return f"Ans: {self.question_id}"


# ==========================================
# 2. QUIZ ATTEMPTS (Kahoot Style)
# ==========================================

class QuizAttempt(TenantBaseModel):
    """
    O'yin/Quiz urinishi.
    Natija darhol chiqadi.
    """
    class Status(models.TextChoices):
        IN_PROGRESS = 'IN_PROGRESS', _('In Progress')
        COMPLETED = 'COMPLETED', _('Completed') 

    assignment = models.ForeignKey(
        'assignments.Assignment',
        on_delete=models.CASCADE,
        related_name='quiz_attempts'
    )
    
    student_id = models.UUIDField(db_index=True)
    
    started_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    
    # --- SIMPLE SCORING ---
    total_score = models.PositiveIntegerField(default=0) # Yig'ilgan ballar
    correct_count = models.PositiveIntegerField(default=0) # Nechta to'g'ri
    incorrect_count = models.PositiveIntegerField(default=0) # Nechta xato
    
    status = models.CharField(
        max_length=20, 
        choices=Status.choices, 
        default=Status.IN_PROGRESS
    )

    class Meta:
        db_table = 'quiz_attempts'
        ordering = ['-started_at']

    def __str__(self):
        return f"Quiz Attempt - {self.student_id}"


class QuizStudentAnswer(TenantBaseModel):
    """
    Quiz savoliga javob.
    Vaqt muhim (Kahootda tez javobga ko'p ball).
    """
    attempt = models.ForeignKey(QuizAttempt, on_delete=models.CASCADE, related_name='answers')
    
    # Faqat Quiz Questionga bog'lanadi
    question = models.ForeignKey(
        'mock_tests.QuizQuestion', 
        on_delete=models.CASCADE,
        related_name='student_answers'
    )
    
    selected_option = models.ForeignKey(
        'mock_tests.QuizOption',
        on_delete=models.CASCADE,
        null=True, blank=True
    )
    
    # Qancha vaqtda javob berdi? (Sekund) - Gamification uchun muhim
    time_taken_seconds = models.FloatField(default=0.0)
    
    is_correct = models.BooleanField(default=False)
    points_earned = models.PositiveIntegerField(default=0)

    class Meta:
        db_table = 'quiz_student_answers'
        unique_together = [['attempt', 'question']]

    def __str__(self):
        return f"Quiz Ans: {self.question_id}"