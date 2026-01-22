#apps/centers/models.py
from django.db import connection
from django.utils import timezone
from django.utils.text import slugify
from datetime import timedelta
from apps.core.models import PublicBaseModel
from apps.core.utils import generate_code
from apps.core.validators import validate_schema_name
from django.core.validators import MinValueValidator

import logging
logger = logging.getLogger(__name__)

class Center(PublicBaseModel):
    """
    Language Center / Organization
    Each center is a separate tenant
    """
    
    class Status(models.TextChoices):
        TRIAL = 'TRIAL', 'Trial'
        ACTIVE = 'ACTIVE', 'Active'
        SUSPENDED = 'SUSPENDED', 'Suspended'
    
    id = models.BigAutoField(primary_key=True)
    name = models.CharField(max_length=150, unique=True)
    slug = models.SlugField(unique=True, null=True, blank=True)
    avatar = models.ImageField(upload_to="center_avatars/", null=True, blank=True)
    is_active = models.BooleanField(default=True)
    description = models.TextField('description', blank=True)
    
    schema_name = models.CharField(
        max_length=63, 
        unique=True,
        null=True,
        blank=True,
        validators=[validate_schema_name],
        help_text="PostgreSQL schema name for this tenant (auto-generated from slug)"
    )

    is_ready = models.BooleanField(
        default=False,
        help_text="True when tenant schema is fully migrated and ready for use."
    )

    # Contact Info
    email = models.EmailField('contact email', null=True, blank=True)
    phone = models.CharField('phone number', max_length=20, null=True, blank=True)
    website = models.URLField('website', null=True, blank=True)
    # Address
    address = models.TextField('address', null=True, blank=True)
    # Branding
    primary_color = models.CharField(max_length=7, default='#FFA500')
    
    # Status & Limits
    status = models.CharField(
        'status',
        max_length=20,
        choices=Status.choices,
        default=Status.TRIAL,
        db_index=True
    )
    
    trial_ends_at = models.DateTimeField('trial ends at', null=True, blank=True)
    subscription_starts_at = models.DateTimeField('subscription starts at', null=True, blank=True)
    subscription_ends_at = models.DateTimeField('subscription ends at', null=True, blank=True)
    
    # TODO: Features
    # features = models.JSONField('enabled features', default=dict, blank=True)
    
    def save(self, *args, **kwargs):
        from django.db import transaction, IntegrityError
        import random
        import string

        if self.pk: # if update existing center
            try:
                old_center = Center.objects.get(pk=self.pk)
                if old_center.avatar and old_center.avatar != self.avatar:
                    old_center.avatar.delete(save=False)
            except Center.DoesNotExist:
                pass
        
        max_retries = 5
        for attempt in range(max_retries):
            try:
                with transaction.atomic():
                    if not self.slug and self.name:
                        base = slugify(self.name)
                        slug_candidate = base or None
                        if attempt > 0:
                            random_suffix = ''.join(random.choices(string.ascii_lowercase + string.digits, k=4))
                            slug_candidate = f"{base}-{random_suffix}"
                        else:
                            i = 1
                            while Center.objects.filter(slug=slug_candidate).exclude(pk=self.pk).exists():
                                i += 1
                                slug_candidate = f"{base}-{i}"
                            self.slug = slug_candidate

                    if not self.schema_name and self.slug:
                        safe_slug = self.slug.replace('-', '_')
                        base_schema = f"center_{safe_slug}"
                        schema_candidate = base_schema
                        
                        # On retry, append random suffix
                        if attempt > 0:
                            random_suffix = ''.join(random.choices(string.ascii_lowercase + string.digits, k=4))
                            schema_candidate = f"{base_schema}_{random_suffix}"
                        else:
                            # First attempt: try sequential numbering
                            i = 1
                            while Center.objects.filter(schema_name=schema_candidate).exclude(pk=self.pk).exists():
                                i += 1
                                schema_candidate = f"{base_schema}_{i}"
                        self.schema_name = schema_candidate

                    super().save(*args, **kwargs)
                    break
            except IntegrityError as e:
                if attempt == max_retries - 1:
                    logger.error(f"Failed to generate unique slug/schema after {max_retries} attempts: {e}")
                    raise
                logger.warning(f"Slug collision on attempt {attempt + 1}, retrying...")
                continue
                        
    def create_schema(self):
        if not self.schema_name:
            logger.error(f"Cannot create schema for Center {self.id}: schema_name is empty")
            return False
        
        try:
            with connection.cursor() as cursor:
                cursor.execute(f"CREATE SCHEMA IF NOT EXISTS {self.schema_name}")
                logger.info(f"✅ Created empty schema: {self.schema_name} (migrations queued)")
            return True
        except Exception as e:
            logger.error(f"❌ Failed to create schema {self.schema_name}: {e}", exc_info=True)
            return False

    def delete_schema(self):
        if not self.schema_name:
            return False
        try:
            with connection.cursor() as cursor:
                cursor.execute(f"DROP SCHEMA IF EXISTS {self.schema_name} CASCADE")
                logger.warning(f"Dropped schema: {self.schema_name}")
            return True
        except Exception as e:
            logger.error(f"Failed to drop schema {self.schema_name}: {e}")
            return False
           
    def hard_delete(self, using=None, keep_parents=False):
        """
        Hard delete the center and its schema.
        
        NOTE: For user-triggered deletions, use hard_delete_center Celery task instead.
        This method is synchronous and should only be used in management commands or tests.
        """
        self.delete_schema()
        return super().hard_delete(using=using, keep_parents=keep_parents)

    class Meta:
        db_table = 'organizations'
        verbose_name = _('organization')
        verbose_name_plural = _('organizations')
        ordering = ['-created_at']
    
    def __str__(self):
        return self.name
    
    @property
    def is_active(self):
        return self.status == self.Status.ACTIVE
    
    @property
    def is_trial(self):
        return self.status == self.Status.TRIAL

    @property
    def is_suspended(self):
        return self.status == self.Status.SUSPENDED

class Subscription(PublicBaseModel):
    """
    Subscription Plans for Center / Organization
    """
    
    class Plan(models.TextChoices):
        FREE = 'FREE', 'Free Trial'
        BASIC = 'BASIC', 'Basic'
        PRO = 'PRO', 'Professional'
        ENTERPRISE = 'ENTERPRISE', 'Enterprise'
    
    center = models.OneToOneField(
        Center,
        on_delete=models.CASCADE,
        related_name='subscription'
    )
    
    plan = models.CharField(
        max_length=20,
        choices=Plan.choices,
        default=Plan.FREE
    )
    
    # Pricing
    price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0,
        validators=[MinValueValidator(0)]
    )
    currency = models.CharField(max_length=3, default='USD')
    
    billing_cycle = models.CharField(
        max_length=20,
        choices=[
            ('monthly', 'Monthly'),
            ('yearly', 'Yearly'),
        ],
        default='monthly'
    )
    
    next_billing_date = models.DateField(null=True, blank=True)
    
    is_active = models.BooleanField(default=True)
    auto_renew = models.BooleanField(default=True)
    
    class Meta:
        db_table = 'subscriptions'
        verbose_name = 'subscription'
        verbose_name_plural = 'subscriptions'
    
    def __str__(self):
        return f"{self.center.name} - {self.get_plan_display()}"

class Invitation(PublicBaseModel):

    ROLE_CHOICES = [
        ("TEACHER", "Teacher"),
        ("STUDENT", "Student"),
        ("GUEST", "Guest Student"),
    ]

    STATUS_CHOICES = [
        ("PENDING", "Pending"),
        ("APPROVED", "Approved"),
        ("REJECTED", "Rejected"),
        ("EXPIRED", "Expired"),
    ]

    code = models.CharField(max_length=12, unique=True, default=generate_code)
    role = models.CharField(max_length=20, choices=ROLE_CHOICES)
    center = models.ForeignKey("centers.Center", on_delete=models.CASCADE, related_name="invitations")
    invited_by = models.ForeignKey("authentication.User", on_delete=models.CASCADE, related_name="sent_invitations")
    target_user = models.OneToOneField("authentication.User", on_delete=models.SET_NULL, null=True, blank=True)
    approved_by = models.ForeignKey("authentication.User", on_delete=models.SET_NULL, null=True, blank=True, related_name="approved_invitations")
    expires_at = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default="PENDING")
    is_guest = models.BooleanField(default=False)

    def __str__(self):
        return f"{self.role} invitation for {self.center.name if self.center else '-'} ({self.status})"

    def set_expiration(self, hours=24):
        """Set expiration time for guest invitations."""
        if self.is_guest:
            self.expires_at = timezone.now() + timedelta(hours=hours)
            self.save(update_fields=["expires_at"])
        return self.expires_at
    
    @property
    def is_expired(self):
        """Check if invitation has expired."""
        return bool(self.expires_at and timezone.now() > self.expires_at)

class ContactRequest(PublicBaseModel):
    center_name = models.CharField(max_length=200, help_text="Name of the center they want to join")
    full_name = models.CharField(max_length=150, help_text="Full name of the person requesting")
    phone_number = models.CharField(max_length=20, help_text="Contact phone number")
    message = models.TextField(help_text="Message from the requester")

    STATUS_CHOICES = [
        ('PENDING', 'Pending'),
        ('CONTACTED', 'Contacted'),
        ('RESOLVED', 'Resolved'),
        ('REJECTED', 'Rejected'),
    ]

    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='PENDING')
    ip_address = models.GenericIPAddressField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['center_name', 'phone_number']),
            models.Index(fields=['status', 'created_at']),
        ]

    def __str__(self):
        return f"Contact Request from {self.full_name} for {self.center_name}"
