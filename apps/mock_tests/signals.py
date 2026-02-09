# apps/mock_tests/signals.py
"""
Signals for the mock_tests app.

post_delete: When a QuestionGroup, Question, or QuizQuestion is hard-deleted,
remove associated media files (audio_file, image) from storage (S3/filesystem)
to avoid orphaned files. MockTest delete cascades to sections -> groups -> questions,
so each model's post_delete runs when the hierarchy is removed.

All deletions are wrapped in transaction.on_commit to ensure files are only deleted
if the database transaction commits successfully.
"""
from django.db import transaction
from django.db.models.signals import post_delete
from django.dispatch import receiver

from django.db.models.signals import post_save

from .models import QuestionGroup, Question, QuizQuestion
from .services import recalc_section_and_mock_scores


@receiver(post_delete, sender=QuestionGroup)
def delete_question_group_media(sender, instance, **kwargs):
    files_to_delete = []
    if instance.audio_file:
        files_to_delete.append(instance.audio_file)
    if instance.image:
        files_to_delete.append(instance.image)
    
    if files_to_delete:
        def delete_files():
            for file_field in files_to_delete:
                try:
                    file_field.delete(save=False)
                except Exception:
                    pass
        transaction.on_commit(delete_files)


@receiver(post_delete, sender=Question)
def delete_question_media(sender, instance, **kwargs):
    files_to_delete = []
    if instance.audio_file:
        files_to_delete.append(instance.audio_file)
    if instance.image:
        files_to_delete.append(instance.image)
    
    if files_to_delete:
        def delete_files():
            for file_field in files_to_delete:
                try:
                    file_field.delete(save=False)
                except Exception:
                    pass
        transaction.on_commit(delete_files)


@receiver(post_save, sender=Question)
def recalc_scores_on_question_save(sender, instance, **kwargs):
    if instance.group_id:
        section = instance.group.section
        transaction.on_commit(lambda: recalc_section_and_mock_scores(section))


@receiver(post_delete, sender=Question)
def recalc_scores_on_question_delete(sender, instance, **kwargs):
    if instance.group_id:
        section = instance.group.section
        transaction.on_commit(lambda: recalc_section_and_mock_scores(section))


@receiver(post_delete, sender=QuizQuestion)
def delete_quiz_question_media(sender, instance, **kwargs):
    if instance.image:
        image_to_delete = instance.image
        def delete_file():
            try:
                image_to_delete.delete(save=False)
            except Exception:
                pass
        transaction.on_commit(delete_file)
