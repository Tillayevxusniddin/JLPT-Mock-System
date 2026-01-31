# apps/mock_tests/signals.py
"""
Signals for the mock_tests app.

post_delete: When a QuestionGroup, Question, or QuizQuestion is hard-deleted,
remove associated media files (audio_file, image) from storage (S3/filesystem)
to avoid orphaned files. MockTest delete cascades to sections -> groups -> questions,
so each model's post_delete runs when the hierarchy is removed.
"""
from django.db.models.signals import post_delete
from django.dispatch import receiver

from .models import QuestionGroup, Question, QuizQuestion


@receiver(post_delete, sender=QuestionGroup)
def delete_question_group_media(sender, instance, **kwargs):
    if instance.audio_file:
        try:
            instance.audio_file.delete(save=False)
        except Exception:
            pass
    if instance.image:
        try:
            instance.image.delete(save=False)
        except Exception:
            pass


@receiver(post_delete, sender=Question)
def delete_question_media(sender, instance, **kwargs):
    if instance.audio_file:
        try:
            instance.audio_file.delete(save=False)
        except Exception:
            pass
    if instance.image:
        try:
            instance.image.delete(save=False)
        except Exception:
            pass


@receiver(post_delete, sender=QuizQuestion)
def delete_quiz_question_media(sender, instance, **kwargs):
    if instance.image:
        try:
            instance.image.delete(save=False)
        except Exception:
            pass
