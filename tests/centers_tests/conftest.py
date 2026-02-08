"""
Shared fixtures for centers app tests.

This module provides comprehensive test fixtures for:
- Centers with various subscription states (FREE, BASIC, PRO, ENTERPRISE, EXPIRED)
- Subscriptions in different lifecycle stages
- Invitations (pending, expired, approved, bulk)
- Contact requests
- Multi-tenant isolation testing
- Celery task mocking

Architecture Notes:
- All fixtures use set_public_schema() to ensure proper multi-tenant isolation
- Celery tasks are mocked by default to prevent actual schema creation during tests
- Database transactions are used to ensure test atomicity
"""

import pytest
from django.utils import timezone
from datetime import timedelta
from unittest.mock import Mock, patch, MagicMock
from rest_framework.test import APIClient
from django.db import connection
from django.contrib.auth import get_user_model

User = get_user_model()


# ============================================================================
# Core Test Utilities
# ============================================================================

@pytest.fixture
def api_client():
    """DRF APIClient for making API requests."""
    client = APIClient()
    client.raise_request_exception = True
    return client


@pytest.fixture
def mock_celery_task():
    """
    Mock Celery tasks to prevent actual execution during tests.
    
    Returns a context manager that mocks the run_tenant_migrations task.
    Use this in tests that create centers to avoid real schema creation.
    
    Usage:
        with mock_celery_task() as mock_task:
            response = api_client.post('/api/v1/owner-centers/', data)
            assert mock_task.delay.called
    """
    # Mock where the task is actually used (in signals.py after import)
    with patch('apps.centers.tasks.run_tenant_migrations') as mock_task:
        mock_result = MagicMock()
        mock_result.id = 'test-task-id-12345'
        mock_task.delay.return_value = mock_result
        yield mock_task


@pytest.fixture
def mock_celery_beat_task():
    """Mock the auto-suspension Celery Beat task."""
    with patch('apps.centers.tasks.check_and_suspend_expired_subscriptions') as mock_task:
        yield mock_task


def _get_error_detail(response):
    """
    Extract error details from DRF error responses.
    
    Handles both simple and nested error structures:
    - {"detail": "error message"}
    - {"field": ["error message"]}
    - {"field": {"nested": ["error"]}}
    """
    if hasattr(response, 'data'):
        data = response.data
        if isinstance(data, dict):
            if 'detail' in data:
                return data['detail']
            # Return first error from field errors
            for key, value in data.items():
                if isinstance(value, list) and value:
                    return value[0]
                elif isinstance(value, dict):
                    return _get_error_detail(type('obj', (), {'data': value})())
                return value
        elif isinstance(data, list) and data:
            return data[0]
    return str(response.data) if hasattr(response, 'data') else ''


# ============================================================================
# User Fixtures (Re-using from authentication_tests/conftest.py)
# ============================================================================

@pytest.fixture
def owner_user(db):
    """Platform owner user (role=OWNER, center=None)."""
    from apps.core.tenant_utils import set_public_schema
    set_public_schema()
    
    user = User.objects.create_user(
        email="owner@platform.com",
        password="OwnerPass123!",
        first_name="Platform",
        last_name="Owner",
        role=User.Role.OWNER,
        center=None,
        is_active=True,
        is_approved=True,
    )
    return user


# ============================================================================
# Center Fixtures with Various States
# ============================================================================

@pytest.fixture
def center_trial(db):
    """
    Center in TRIAL status with FREE subscription (40 days remaining).
    This represents a newly created center still in the 2-month trial period.
    """
    from apps.centers.models import Center, Subscription
    from apps.core.tenant_utils import set_public_schema
    
    set_public_schema()
    
    center = Center.objects.create(
        name="Trial Language Center",
        slug="trial-center",
        schema_name="tenant_trial_center",
        status=Center.Status.TRIAL,
        email="contact@trial.com",
        phone="+998901111111",
        is_ready=True,
    )
    
    # Update the auto-created FREE subscription to have 40 days remaining
    subscription = Subscription.objects.get(center=center)
    subscription.starts_at = timezone.now() - timedelta(days=20)
    subscription.ends_at = timezone.now() + timedelta(days=40)
    subscription.save()
    
    return center


@pytest.fixture
def center_trial_expiring_soon(db):
    """
    Center in TRIAL status with FREE subscription expiring in 3 days.
    Tests edge case for upgrade urgency.
    """
    from apps.centers.models import Center, Subscription
    from apps.core.tenant_utils import set_public_schema
    
    set_public_schema()
    
    center = Center.objects.create(
        name="Expiring Trial Center",
        slug="expiring-trial",
        schema_name="tenant_expiring_trial",
        status=Center.Status.TRIAL,
        email="contact@expiring.com",
        is_ready=True,
    )
    
    # Update the auto-created subscription to expire in 3 days
    subscription = Subscription.objects.get(center=center)
    subscription.starts_at = timezone.now() - timedelta(days=57)
    subscription.ends_at = timezone.now() + timedelta(days=3)
    subscription.save()
    
    return center


@pytest.fixture
def center_expired(db):
    """
    Center with EXPIRED FREE subscription but not yet suspended.
    Simulates the window between expiry and auto-suspension task running.
    """
    from apps.centers.models import Center, Subscription
    from apps.core.tenant_utils import set_public_schema
    
    set_public_schema()
    
    center = Center.objects.create(
        name="Expired Trial Center",
        slug="expired-center",
        schema_name="tenant_expired_center",
        status=Center.Status.TRIAL,  # Not suspended yet
        email="contact@expired.com",
        is_ready=True,
    )
    
    # Update the auto-created subscription to be expired 5 days ago
    subscription = Subscription.objects.get(center=center)
    subscription.starts_at = timezone.now() - timedelta(days=65)
    subscription.ends_at = timezone.now() - timedelta(days=5)  # Expired 5 days ago
    subscription.save()
    
    return center


@pytest.fixture
def center_suspended(db):
    """
    SUSPENDED center with expired FREE subscription.
    This is the final state after auto-suspension.
    """
    from apps.centers.models import Center, Subscription
    from apps.core.tenant_utils import set_public_schema
    
    set_public_schema()
    
    center = Center.objects.create(
        name="Suspended Center",
        slug="suspended-center",
        schema_name="tenant_suspended_center",
        status=Center.Status.SUSPENDED,
        email="contact@suspended.com",
        is_ready=True,
    )
    
    # Update the auto-created subscription to be expired and inactive
    subscription = Subscription.objects.get(center=center)
    subscription.starts_at = timezone.now() - timedelta(days=70)
    subscription.ends_at = timezone.now() - timedelta(days=10)
    subscription.is_active = False  # Marked inactive after suspension
    subscription.save()
    
    return center


@pytest.fixture
def center_basic(db):
    """
    ACTIVE center with BASIC subscription (paid plan, 350 days remaining).
    """
    from apps.centers.models import Center, Subscription
    from apps.core.tenant_utils import set_public_schema

    set_public_schema()

    # Create center with TRIAL status first (will be set by signal)
    center = Center.objects.create(
        name="Basic Plan Center",
        slug="basic-center",
        schema_name="tenant_basic_center",
        status=Center.Status.TRIAL,  # Signal will set this
        email="contact@basic.com",
        phone="+998902222222",
        is_ready=True,
    )
    
    # Update the auto-created subscription to BASIC plan
    subscription = Subscription.objects.get(center=center)
    subscription.plan = Subscription.Plan.BASIC
    subscription.price = 29.99
    subscription.billing_cycle = 'monthly'
    subscription.starts_at = timezone.now() - timedelta(days=15)
    subscription.ends_at = timezone.now() + timedelta(days=350)
    subscription.auto_renew = True
    subscription.save()
    
    # After subscription is updated to BASIC (paid), set center status to ACTIVE
    center.status = Center.Status.ACTIVE
    center.save(update_fields=['status', 'updated_at'])
    
    return center


@pytest.fixture
def center_pro(db):
    """
    ACTIVE center with PRO subscription.
    """
    from apps.centers.models import Center, Subscription
    from apps.core.tenant_utils import set_public_schema
    
    set_public_schema()
    
    # Create center with TRIAL status first (will be set by signal)
    center = Center.objects.create(
        name="Pro Plan Center",
        slug="pro-center",
        schema_name="tenant_pro_center",
        status=Center.Status.TRIAL,  # Signal will set this
        email="contact@pro.com",
        is_ready=True,
    )
    
    # Update the auto-created subscription to PRO plan
    subscription = Subscription.objects.get(center=center)
    subscription.plan = Subscription.Plan.PRO
    subscription.price = 79.99
    subscription.billing_cycle = 'monthly'
    subscription.starts_at = timezone.now()
    subscription.ends_at = timezone.now() + timedelta(days=365)
    subscription.auto_renew = True
    subscription.save()
    
    # After subscription is updated to PRO (paid), set center status to ACTIVE
    center.status = Center.Status.ACTIVE
    center.save(update_fields=['status', 'updated_at'])
    
    return center


@pytest.fixture
def center_enterprise(db):
    """
    ACTIVE center with ENTERPRISE subscription.
    """
    from apps.centers.models import Center, Subscription
    from apps.core.tenant_utils import set_public_schema
    
    set_public_schema()
    
    # Create center with TRIAL status first (will be set by signal)
    center = Center.objects.create(
        name="Enterprise Plan Center",
        slug="enterprise-center",
        schema_name="tenant_enterprise_center",
        status=Center.Status.TRIAL,  # Signal will set this
        email="contact@enterprise.com",
        is_ready=True,
    )
    
    # Update the auto-created subscription to ENTERPRISE plan
    subscription = Subscription.objects.get(center=center)
    subscription.plan = Subscription.Plan.ENTERPRISE
    subscription.price = 199.99
    subscription.billing_cycle = 'yearly'
    subscription.starts_at = timezone.now()
    subscription.ends_at = timezone.now() + timedelta(days=365)
    subscription.auto_renew = True
    subscription.save()
    
    # After subscription is updated to ENTERPRISE (paid), set center status to ACTIVE
    center.status = Center.Status.ACTIVE
    center.save(update_fields=['status', 'updated_at'])
    
    return center


@pytest.fixture
def center_not_ready(db):
    """
    Center that was just created but migrations haven't completed yet.
    is_ready=False simulates ongoing schema setup.
    """
    from apps.centers.models import Center, Subscription
    from apps.core.tenant_utils import set_public_schema
    
    set_public_schema()
    
    center = Center.objects.create(
        name="Not Ready Center",
        slug="not-ready-center",
        schema_name="tenant_not_ready",
        status=Center.Status.TRIAL,
        email="contact@notready.com",
        is_ready=False,  # Migrations still running
    )
    
    # The auto-created FREE subscription is already correct for this fixture
    # No updates needed since it's a standard 60-day FREE trial
    
    return center


# ============================================================================
# User Fixtures for Centers
# ============================================================================

@pytest.fixture
def admin_trial(db, center_trial):
    """Center Admin for the trial center."""
    from apps.core.tenant_utils import set_public_schema
    set_public_schema()
    
    return User.objects.create_user(
        email="admin@trial.com",
        password="AdminPass123!",
        first_name="Admin",
        last_name="Trial",
        role=User.Role.CENTERADMIN,
        center=center_trial,
        is_active=True,
        is_approved=True,
    )


@pytest.fixture
def admin_basic(db, center_basic):
    """Center Admin for the basic plan center."""
    from apps.core.tenant_utils import set_public_schema
    set_public_schema()
    
    return User.objects.create_user(
        email="admin@basic.com",
        password="AdminPass123!",
        first_name="Admin",
        last_name="Basic",
        role=User.Role.CENTERADMIN,
        center=center_basic,
        is_active=True,
        is_approved=True,
    )


@pytest.fixture
def admin_suspended(db, center_suspended):
    """Center Admin for suspended center (should have limited access)."""
    from apps.core.tenant_utils import set_public_schema
    set_public_schema()
    
    return User.objects.create_user(
        email="admin@suspended.com",
        password="AdminPass123!",
        first_name="Admin",
        last_name="Suspended",
        role=User.Role.CENTERADMIN,
        center=center_suspended,
        is_active=True,
        is_approved=True,
    )


@pytest.fixture
def teacher_trial(db, center_trial):
    """Teacher in trial center."""
    from apps.core.tenant_utils import set_public_schema
    set_public_schema()
    
    return User.objects.create_user(
        email="teacher@trial.com",
        password="TeacherPass123!",
        first_name="Teacher",
        last_name="Trial",
        role=User.Role.TEACHER,
        center=center_trial,
        is_active=True,
        is_approved=True,
    )


@pytest.fixture
def student_trial(db, center_trial):
    """Student in trial center."""
    from apps.core.tenant_utils import set_public_schema
    set_public_schema()
    
    return User.objects.create_user(
        email="student@trial.com",
        password="StudentPass123!",
        first_name="Student",
        last_name="Trial",
        role=User.Role.STUDENT,
        center=center_trial,
        is_active=True,
        is_approved=True,
    )


# ============================================================================
# Invitation Fixtures
# ============================================================================

@pytest.fixture
def invitation_pending(db, center_trial, admin_trial):
    """Valid pending invitation for STUDENT role."""
    from apps.centers.models import Invitation
    from apps.core.tenant_utils import set_public_schema
    
    set_public_schema()
    
    return Invitation.objects.create(
        code="STUD-INV-001",  # Max 12 chars
        role="STUDENT",
        center=center_trial,
        invited_by=admin_trial,
        status="PENDING",
        expires_at=timezone.now() + timedelta(days=7),
        is_guest=False,
    )


@pytest.fixture
def invitation_teacher_pending(db, center_trial, admin_trial):
    """Valid pending invitation for TEACHER role."""
    from apps.centers.models import Invitation
    from apps.core.tenant_utils import set_public_schema
    
    set_public_schema()
    
    return Invitation.objects.create(
        code="TCH-INV-0001",  # Max 12 chars
        role="TEACHER",
        center=center_trial,
        invited_by=admin_trial,
        status="PENDING",
        expires_at=timezone.now() + timedelta(days=7),
        is_guest=False,
    )


@pytest.fixture
def invitation_guest(db, center_trial, admin_trial):
    """Guest invitation (24-hour expiry)."""
    from apps.centers.models import Invitation
    from apps.core.tenant_utils import set_public_schema
    
    set_public_schema()
    
    return Invitation.objects.create(
        code="GUEST-INV-01",  # Max 12 chars
        role="STUDENT",
        center=center_trial,
        invited_by=admin_trial,
        status="PENDING",
        expires_at=timezone.now() + timedelta(hours=24),
        is_guest=True,
    )


@pytest.fixture
def invitation_expired(db, center_trial, admin_trial):
    """Expired invitation."""
    from apps.centers.models import Invitation
    from apps.core.tenant_utils import set_public_schema
    
    set_public_schema()
    
    return Invitation.objects.create(
        code="EXP-INV-0001",  # Max 12 chars
        role="STUDENT",
        center=center_trial,
        invited_by=admin_trial,
        status="PENDING",
        expires_at=timezone.now() - timedelta(days=1),
        is_guest=False,
    )


@pytest.fixture
def invitation_approved(db, center_trial, admin_trial, student_trial):
    """Already approved invitation."""
    from apps.centers.models import Invitation
    from apps.core.tenant_utils import set_public_schema
    
    set_public_schema()
    
    return Invitation.objects.create(
        code="APP-INV-0001",  # Max 12 chars
        role="STUDENT",
        center=center_trial,
        invited_by=admin_trial,
        target_user=student_trial,
        approved_by=admin_trial,
        status="APPROVED",
        expires_at=timezone.now() + timedelta(days=7),
        is_guest=False,
    )


# ============================================================================
# Contact Request Fixtures
# ============================================================================

@pytest.fixture
def contact_request_pending(db):
    """Pending contact request."""
    from apps.centers.models import ContactRequest
    from apps.core.tenant_utils import set_public_schema
    
    set_public_schema()
    
    return ContactRequest.objects.create(
        center_name="Tokyo Language School",
        full_name="John Smith",
        phone_number="+81-3-1234-5678",
        message="I want to register our school on your platform.",
        status="PENDING",
        ip_address="203.0.113.42",
    )


@pytest.fixture
def contact_request_contacted(db):
    """Contact request in CONTACTED status."""
    from apps.centers.models import ContactRequest
    from apps.core.tenant_utils import set_public_schema
    
    set_public_schema()
    
    return ContactRequest.objects.create(
        center_name="Kyoto Learning Center",
        full_name="Mike Johnson",
        phone_number="+81-75-5555-1234",
        message="Please send more information.",
        status="CONTACTED",
    )


@pytest.fixture
def contact_request_resolved(db):
    """Resolved contact request."""
    from apps.centers.models import ContactRequest
    from apps.core.tenant_utils import set_public_schema
    
    set_public_schema()
    
    return ContactRequest.objects.create(
        center_name="Osaka Language Academy",
        full_name="Jane Doe",
        phone_number="+81-6-9876-5432",
        message="How do I join?",
        status="RESOLVED",
    )


# ============================================================================
# JWT Auth Helper
# ============================================================================

@pytest.fixture
def get_auth_header():
    """Generate JWT auth headers for a user."""
    from rest_framework_simplejwt.tokens import RefreshToken
    
    def _get_header(user):
        refresh = RefreshToken.for_user(user)
        return {'HTTP_AUTHORIZATION': f'Bearer {str(refresh.access_token)}'}
    
    return _get_header


# ============================================================================
# Multi-Tenancy Helpers
# ============================================================================

@pytest.fixture(autouse=True)
def ensure_public_schema(db):
    """Ensure all tests start and end in the public schema."""
    from django.db import connection
    
    if connection.vendor == 'postgresql':
        from apps.core.tenant_utils import set_public_schema
        set_public_schema()

    yield

    if connection.vendor == 'postgresql':
        from apps.core.tenant_utils import set_public_schema
        set_public_schema()


@pytest.fixture(autouse=True)
def disable_contact_request_notification_signals(db):
    """Disable contact request notification signals to avoid circular imports in tests."""
    from django.db.models.signals import post_save
    from django.apps import apps as django_apps
    ContactRequest = django_apps.get_model("centers", "ContactRequest")
    try:
        from apps.centers.signals import notify_owner_on_contact_request
    except Exception:  # pragma: no cover
        notify_owner_on_contact_request = None
    try:
        from apps.notifications.signals import contact_request_priority_handler
    except Exception:  # pragma: no cover
        contact_request_priority_handler = None

    if notify_owner_on_contact_request:
        post_save.disconnect(notify_owner_on_contact_request, sender=ContactRequest)
    if contact_request_priority_handler:
        post_save.disconnect(contact_request_priority_handler, sender=ContactRequest)

    yield

    if notify_owner_on_contact_request:
        post_save.connect(notify_owner_on_contact_request, sender=ContactRequest)
    if contact_request_priority_handler:
        post_save.connect(contact_request_priority_handler, sender=ContactRequest)
