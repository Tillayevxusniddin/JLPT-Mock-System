"""
Authentication Models
"""
import uuid
from django.db import models
from django.contrib.auth.models import AbstractBaseUser, PermissionsMixin
from django.utils.translation import gettext_lazy as _
from django.core.validators import RegexValidator

from apps.core.models import TimeStampedModel
from .managers import UserManager


class User(AbstractBaseUser, PermissionsMixin, TimeStampedModel):
    """
    Custom User Model
    Supports multiple roles: OWNER, CENTERADMIN, TEACHER, STUDENT
    
    ✅ Uses UUID as Primary Key for multi-tenant architecture consistency
    """
    
    # Primary Key - UUID for cross-schema compatibility
    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
        help_text=_('Unique identifier for user across all schemas')
    )
    
    class Role(models.TextChoices):
        OWNER = 'OWNER', _('Platform Owner')
        CENTERADMIN = 'CENTERADMIN', _('Center Administrator')
        TEACHER = 'TEACHER', _('Teacher')
        STUDENT = 'STUDENT', _('Student')
    
    # Basic Information
    email = models.EmailField(_('email address'), unique=True, db_index=True)
    phone = models.CharField(
        _('phone number'),
        max_length=20,
        blank=True,
        validators=[RegexValidator(r'^\+?1?\d{9,15}$')]
    )
    
    first_name = models.CharField(_('first name'), max_length=150)
    last_name = models.CharField(_('last name'), max_length=150)
    
    # Profile
    avatar = models.ImageField(_('avatar'), upload_to='avatars/%Y/%m/', blank=True, null=True)
    date_of_birth = models.DateField(_('date of birth'), null=True, blank=True)
    
    # Role & Organization
    role = models.CharField(
        _('role'),
        max_length=20,
        choices=Role.choices,
        db_index=True
    )
    organization = models.ForeignKey(
        'organizations.Organization',
        on_delete=models.SET_NULL, 
        null=True,
        blank=True,
        related_name='users',
        help_text=_('Organization the user belongs to (null for OWNER)')
    )
    
    # Status
    is_active = models.BooleanField(_('active'), default=True)
    is_approved = models.BooleanField(_('approved'), default=False)
    is_staff = models.BooleanField(_('staff status'), default=False)
    is_email_verified = models.BooleanField(_('email verified'), default=False)
    
    # Timestamps
    email_verified_at = models.DateTimeField(_('email verified at'), null=True, blank=True)
    last_login_at = models.DateTimeField(_('last login at'), null=True, blank=True)
    
    # Settings
    language = models.CharField(_('language'), max_length=10, default='en')
    timezone = models.CharField(_('timezone'), max_length=50, default='UTC')
    
    objects = UserManager()

    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = ['first_name', 'last_name', 'role']
    
    class Meta:
        db_table = 'users'
        verbose_name = _('user')
        verbose_name_plural = _('users')
        indexes = [
            models.Index(fields=['email', 'is_active']),
            models.Index(fields=['organization_id', 'role']),
        ]
    
    def __str__(self):
        return f"{self.get_full_name()} ({self.email})"
    
    def get_full_name(self):
        return f"{self.first_name} {self.last_name}".strip()
    
    def get_short_name(self):
        return self.first_name
    
    @property
    def is_owner(self):
        return self.role == self.Role.OWNER
    
    @property
    def is_center_admin(self):
        return self.role == self.Role.CENTERADMIN
    
    @property
    def is_teacher(self):
        return self.role == self.Role.TEACHER
    
    @property
    def is_student(self):
        return self.role == self.Role.STUDENT


class UserProfile(TimeStampedModel):
    """
    Common fields for all users
    """
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')
    address = models.TextField(_('address'), blank=True)
    city = models.CharField(_('city'), max_length=100, blank=True)
    bio = models.TextField(_('biography'), blank=True)
    emergency_contact_name = models.CharField(_('emergency contact name'), max_length=150, blank=True)
    emergency_contact_phone = models.CharField(_('emergency contact phone'), max_length=20, blank=True)

    """
    Student's fields 
    """
    enrollment_date = models.DateField(_('enrollment date'), null=True, blank=True)
    current_level = models.CharField(
        _('current JLPT level'),
        max_length=2,
        choices=[
            ('N5', 'N5'),
            ('N4', 'N4'),
            ('N3', 'N3'),
            ('N2', 'N2'),
            ('N1', 'N1'),
        ],
        blank=True,
        null=True
    )

    """
    Teacher's fields 
    """
    years_of_experience = models.PositiveIntegerField(_('years of experience'), default=0)

    class Meta:
        db_table = 'user_profiles'
        verbose_name = _('user profile')
        verbose_name_plural = _('user profiles')

    def __str__(self):
        return f"Profile of {self.user.email}"
    
