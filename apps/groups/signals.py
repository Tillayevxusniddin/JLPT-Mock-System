#apps/groups/signals.py
from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from django.conf import settings
import logging

from apps.groups.models import GroupMembership

logger = logging.getLogger(__name__)


@receiver([post_save, post_delete], sender=GroupMembership)
def update_group_counts(sender, instance: GroupMembership, **kwargs):
    if getattr(settings, 'DISABLE_GROUP_SIGNALS', False):
        return

    try:
        group = instance.group
        
        student_count = GroupMembership.objects.filter(
            group=group, role_in_group=GroupMembership.ROLE_STUDENT
        ).count()
        teacher_count = GroupMembership.objects.filter(
            group=group, role_in_group=GroupMembership.ROLE_TEACHER
        ).count()

        group.student_count = student_count
        group.teacher_count = teacher_count
        group.save(update_fields=['student_count', 'teacher_count'])
        
    except Exception as e:
        logger.error(f"Failed to update group counts for group {instance.group_id}: {e}")


# Group membership notifications are handled in apps.notifications.signals