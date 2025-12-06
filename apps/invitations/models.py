from django.db import models
from django.utils.translation import gettext_lazy as _
from django.utils import timezone
from datetime import timedelta

from apps.core.models import TimeStampedModel
from .utils import generate_invitation_code

class Invitation(TimeStampedModel):
    class Role(models.TextChoices):
        TEACHER = 'TEACHER', _('Teacher')
        STUDENT = 'STUDENT', _('Student')

    # Kod (unikal)
    code = models.CharField(
        max_length=12, 
        unique=True, 
        default=generate_invitation_code, 
        editable=False,
        db_index=True
    )

    # Qaysi tashkilotga taklif qilinmoqda?
    organization = models.ForeignKey(
        'organizations.Organization',
        on_delete=models.CASCADE,
        related_name='invitations'
    )

    # Kim yaratdi? (CenterAdmin)
    # ✅ UUIDField instead of ForeignKey (User is in public schema, Invitation is in public schema)
    # Using UUIDField maintains consistency with tenant schema pattern
    created_by_id = models.UUIDField(
        _('creator user id'),
        null=True,
        blank=True,
        db_index=True,
        help_text=_('UUID of the user who created this invitation')
    )

    # Kim uchun? (Teacher yoki Student)
    role = models.CharField(max_length=20, choices=Role.choices)

    # Cheklovlar
    is_active = models.BooleanField(default=True) # Kodni vaqtincha o'chirib qo'yish uchun
    expires_at = models.DateTimeField(null=True, blank=True)
    
    # Usage limit (opsional): Bitta kodni necha kishi ishlata oladi?
    # Agar 0 bo'lsa - cheksiz (umumiy havola uchun).
    # Agar 1 bo'lsa - shaxsiy taklifnoma.
    usage_limit = models.PositiveIntegerField(default=0, help_text=_("0 for unlimited"))
    
    # Necha marta ishlatildi?
    usage_count = models.PositiveIntegerField(default=0)

    class Meta:
        db_table = 'public_invitations'
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.code} - {self.organization.name} ({self.role})"

    @property
    def is_valid(self):
        """Kod yaroqlimi?"""
        if not self.is_active:
            return False
        if self.expires_at and self.expires_at < timezone.now():
            return False
        if self.usage_limit > 0 and self.usage_count >= self.usage_limit:
            return False
        return True