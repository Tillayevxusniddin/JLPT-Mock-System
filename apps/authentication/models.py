#apps/authentication/models.py
from django.contrib.auth.models import AbstractUser
from django.db import models
from apps.core.models import PublicBaseModel
from apps.core.managers import SoftDeleteManager
from .managers import SoftDeleteUserManager
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

class User(PublicBaseModel, AbstractUser):
    
    id = models.BigAutoField(primary_key=True)

    username = None
    email = models.EmailField(unique=True)     
    first_name = models.CharField(max_length=150, blank=True)
    last_name = models.CharField(max_length=150, blank=True)
    avatar = models.ImageField(upload_to="avatars/", null=True, blank=True)

    class Role(models.TextChoices):
        OWNER = "OWNER", "Owner"
        CENTERADMIN = "CENTER_ADMIN", "CenterAdmin"
        TEACHER = "TEACHER", "Teacher"
        STUDENT = "STUDENT", "Student"
        GUEST = "GUEST", "Guest"

    role = models.CharField(max_length=20, choices=Role.choices, default=Role.GUEST)
    center = models.ForeignKey("centers.Center", on_delete=models.CASCADE, null=True, blank=True)
    is_approved = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)

    address = models.TextField(null=True, blank=True)
    bio = models.TextField(null=True, blank=True)
    city = models.CharField(max_length=100, null=True, blank=True)
    emergency_contact_phone = models.CharField(max_length=20, null=True, blank=True)

    last_login_ip = models.GenericIPAddressField(null=True, blank=True)
    last_login_agent = models.CharField(max_length=255, blank=True)
    last_login_at = models.DateTimeField(null=True, blank=True)

    objects = SoftDeleteUserManager()
    global_objects = SoftDeleteManager()

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = []

    class Meta:
        db_table = 'users'
        verbose_name = _('user')
        verbose_name_plural = _('users')
        indexes = [
            models.Index(fields=['email', 'is_active']),
            models.Index(fields=['center_id', 'role']),
        ]

    def __str__(self):
        return f"{self.get_full_name()}-{self.role}"

    def get_full_name(self):
        return " ".join(filter(None, [self.first_name, self.last_name]))

    def get_short_name(self):
        return self.first_name

    def is_center_member(self):
        return self.center_id is not None

    def update_last_login_info(self, ip, agent):
        self.last_login_ip = ip
        self.last_login_agent = agent
        self.last_login_at = timezone.now()
        self.save(update_fields=["last_login_ip", "last_login_agent", "last_login_at"])

    def save(self, *args, **kwargs):
        #Override save to handle avatar replacement
        if self.pk:
            try:
                old_user = User.objects.get(pk=self.pk)
                if old_user.avatar and old_user.avatar != self.avatar:
                    old_user.avatar.delete(save=False)
            except User.DoesNotExist:
                pass
        super().save(*args, **kwargs)

    def soft_delete(self):
        # Delete avatar from S3 on soft delete
        if self.avatar:
            self.avatar.delete(save=False)
        return super().soft_delete()

    @property
    def is_owner_role(self):
        return self.role == self.Role.OWNER

    @property
    def is_center_admin_role(self):
        return self.role == self.Role.CENTERADMIN

    @property
    def is_teacher_role(self):
        return self.role == self.Role.TEACHER

    @property
    def is_student_role(self):
        return self.role == self.Role.STUDENT

    @property
    def is_guest_role(self):
        return self.role == self.Role.GUEST

class UserActivity(PublicBaseModel):

    user = models.ForeignKey(
        "authentication.User", 
        on_delete=models.CASCADE, 
        related_name="activities"
    )
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.CharField(max_length=255, blank=True)
    logged_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.user.email} - {self.ip_address or 'unknown'}"