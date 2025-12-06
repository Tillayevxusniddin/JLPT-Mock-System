"""
Organization Models - Multi-tenant management
"""
from django.db import models
from django.utils.translation import gettext_lazy as _
from django.core.validators import MinValueValidator
from django.core.validators import RegexValidator

from apps.core.models import TimeStampedModel


class Organization(TimeStampedModel):
    """
    Language Center / Organization
    Each center is a separate tenant
    """
    
    class Status(models.TextChoices):
        TRIAL = 'TRIAL', _('Trial')
        ACTIVE = 'ACTIVE', _('Active')
        SUSPENDED = 'SUSPENDED', _('Suspended')
        CANCELLED = 'CANCELLED', _('Cancelled')
    
    # Basic Info
    name = models.CharField(_('organization name'), max_length=255, db_index=True)
    slug = models.SlugField(_('slug'), max_length=255, unique=True)
    description = models.TextField(_('description'), blank=True)
    
    # Contact Info
    email = models.EmailField(_('contact email'))
    phone = models.CharField(_('phone number'), max_length=20, blank=True)
    website = models.URLField(_('website'), blank=True)
    
    # Address
    address = models.TextField(_('address'), blank=True)
    city = models.CharField(_('city'), max_length=100, blank=True)
    country = models.CharField(_('country'), max_length=100, default='Uzbekistan')
    
    # Branding
    logo = models.ImageField(_('logo'), upload_to='organizations/logos/', blank=True, null=True)
    primary_color = models.CharField(_('primary color'), max_length=7, default='#1a73e8')
    
    # Status & Limits
    status = models.CharField(
        _('status'),
        max_length=20,
        choices=Status.choices,
        default=Status.TRIAL,
        db_index=True
    )
    
    max_students = models.PositiveIntegerField(_('max students'), default=50)
    max_teachers = models.PositiveIntegerField(_('max teachers'), default=5)
    max_storage_mb = models.PositiveIntegerField(_('max storage (MB)'), default=1000)
    
    # Trial & Subscription
    trial_ends_at = models.DateTimeField(_('trial ends at'), null=True, blank=True)
    subscription_starts_at = models.DateTimeField(_('subscription starts'), null=True, blank=True)
    subscription_ends_at = models.DateTimeField(_('subscription ends'), null=True, blank=True)
    
    # Settings
    timezone = models.CharField(_('timezone'), max_length=50, default='Asia/Tashkent')
    language = models.CharField(_('default language'), max_length=10, default='en')
    
    # Features
    features = models.JSONField(_('enabled features'), default=dict, blank=True)
    
    schema_name = models.CharField(
        _('schema name'), 
        max_length=63, 
        unique=True, 
        db_index=True,
        validators=[RegexValidator(r'^[a-z0-9_]+$', 'Only lowercase letters, numbers, and underscores.')]
    )

    def save(self, *args, **kwargs):
        if not self.schema_name:
            safe_slug = self.slug.replace('-', '_') if self.slug else f"org_{self.id.hex[:8]}"
            self.schema_name = f"tenant_{safe_slug}"
            
        super().save(*args, **kwargs)

    class Meta:
        db_table = 'organizations'
        verbose_name = _('organization')
        verbose_name_plural = _('organizations')
        ordering = ['name']
    
    def __str__(self):
        return self.name
    
    @property
    def is_active(self):
        return self.status == self.Status.ACTIVE
    
    @property
    def is_trial(self):
        return self.status == self.Status.TRIAL

class Subscription(TimeStampedModel):
    """
    Subscription Plans for Organizations
    """
    
    class Plan(models.TextChoices):
        FREE = 'FREE', _('Free Trial')
        BASIC = 'BASIC', _('Basic')
        PRO = 'PRO', _('Professional')
        ENTERPRISE = 'ENTERPRISE', _('Enterprise')
    
    organization = models.OneToOneField(
        Organization,
        on_delete=models.CASCADE,
        related_name='subscription'
    )
    
    plan = models.CharField(
        _('plan'),
        max_length=20,
        choices=Plan.choices,
        default=Plan.FREE
    )
    
    # Pricing
    price = models.DecimalField(
        _('price'),
        max_digits=10,
        decimal_places=2,
        default=0,
        validators=[MinValueValidator(0)]
    )
    currency = models.CharField(_('currency'), max_length=3, default='USD')
    
    # Billing
    billing_cycle = models.CharField(
        _('billing cycle'),
        max_length=20,
        choices=[
            ('monthly', _('Monthly')),
            ('yearly', _('Yearly')),
        ],
        default='monthly'
    )
    
    next_billing_date = models.DateField(_('next billing date'), null=True, blank=True)
    
    # Status
    is_active = models.BooleanField(_('active'), default=True)
    auto_renew = models.BooleanField(_('auto renew'), default=True)
    
    class Meta:
        db_table = 'subscriptions'
        verbose_name = _('subscription')
        verbose_name_plural = _('subscriptions')
    
    def __str__(self):
        return f"{self.organization.name} - {self.get_plan_display()}"