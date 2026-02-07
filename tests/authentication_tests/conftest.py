"""
Shared fixtures for authentication tests.

Fixtures provided:
- api_client: DRF APIClient for making requests
- public_user: Owner role user (center=None) for main domain
- center_a, center_b: Two test centers with unique slugs and schemas
- center_admin_a, center_admin_b: Center admins for each center
- teacher_a, teacher_b: Teachers for each center
- student_a, student_b: Students for each center
- guest_a: Guest user for center A
- inactive_user_a: Inactive user in center A
- soft_deleted_user_a: Soft-deleted user in center A
- invitation_pending_a: Valid pending invitation for center A
- invitation_expired_a: Expired invitation for center A
- invitation_claimed_a: Already claimed invitation for center A
"""
import pytest
from django.utils import timezone
from datetime import timedelta
from rest_framework.test import APIClient
from django.db import connection
from django.contrib.auth import get_user_model

User = get_user_model()


@pytest.fixture
def api_client():
    """DRF APIClient for making API requests."""
    client = APIClient()
    client.raise_request_exception = True
    return client


@pytest.fixture
def public_user(db):
    """
    Owner user with center=None.
    This user can only log in on main domain (localhost, mikan.uz, api.mikan.uz).
    """
    from apps.core.tenant_utils import set_public_schema
    set_public_schema()
    
    user = User.objects.create_user(
        email="owner@platform.com",
        password="SecurePass123!",
        first_name="Platform",
        last_name="Owner",
        role=User.Role.OWNER,
        center=None,
        is_active=True,
        is_approved=True,
    )
    return user


@pytest.fixture
def center_a(db):
    """
    Test Center A with slug 'test-center-a' and schema 'tenant_test_center_a'.
    Subdomain: test-center-a.mikan.uz
    """
    from apps.centers.models import Center
    from apps.core.tenant_utils import set_public_schema
    from django.utils import timezone
    from datetime import timedelta
    
    set_public_schema()
    
    center = Center.objects.create(
        name="Test Center A",
        slug="test-center-a",
        schema_name="tenant_test_center_a",
        status=Center.Status.ACTIVE,
        email="contact@center-a.com",
        phone="+998901234567",
        is_ready=True,
    )
    
    # Update the auto-created subscription to BASIC plan
    from apps.centers.models import Subscription
    subscription = Subscription.objects.get(center=center)
    subscription.plan = Subscription.Plan.BASIC
    subscription.price = 29.99
    subscription.billing_cycle = 'monthly'
    subscription.starts_at = timezone.now()
    subscription.ends_at = timezone.now() + timedelta(days=365)
    subscription.auto_renew = True
    subscription.save()
    
    # Create schema if it doesn't exist (for tenant isolation tests)
    _create_tenant_schema(center.schema_name)
    
    return center


@pytest.fixture
def center_b(db):
    """
    Test Center B with slug 'test-center-b' and schema 'tenant_test_center_b'.
    Subdomain: test-center-b.mikan.uz
    """
    from apps.centers.models import Center
    from apps.core.tenant_utils import set_public_schema
    from django.utils import timezone
    from datetime import timedelta
    
    set_public_schema()
    
    center = Center.objects.create(
        name="Test Center B",
        slug="test-center-b",
        schema_name="tenant_test_center_b",
        status=Center.Status.ACTIVE,
        email="contact@center-b.com",
        phone="+998907654321",
        is_ready=True,
    )
    
    # Update the auto-created subscription to PRO plan
    from apps.centers.models import Subscription
    subscription = Subscription.objects.get(center=center)
    subscription.plan = Subscription.Plan.PRO
    subscription.price = 79.99
    subscription.billing_cycle = 'monthly'
    subscription.starts_at = timezone.now()
    subscription.ends_at = timezone.now() + timedelta(days=365)
    subscription.auto_renew = True
    subscription.save()
    
    # Create schema if it doesn't exist
    _create_tenant_schema(center.schema_name)
    
    return center


@pytest.fixture
def center_admin_a(db, center_a):
    """Center Admin for Center A."""
    from apps.core.tenant_utils import set_public_schema
    set_public_schema()
    
    user = User.objects.create_user(
        email="admin@center-a.com",
        password="AdminPass123!",
        first_name="Admin",
        last_name="CenterA",
        role=User.Role.CENTERADMIN,
        center=center_a,
        is_active=True,
        is_approved=True,
    )
    return user


@pytest.fixture
def center_admin_b(db, center_b):
    """Center Admin for Center B."""
    from apps.core.tenant_utils import set_public_schema
    set_public_schema()
    
    user = User.objects.create_user(
        email="admin@center-b.com",
        password="AdminPass123!",
        first_name="Admin",
        last_name="CenterB",
        role=User.Role.CENTERADMIN,
        center=center_b,
        is_active=True,
        is_approved=True,
    )
    return user


@pytest.fixture
def teacher_a(db, center_a):
    """Teacher for Center A."""
    from apps.core.tenant_utils import set_public_schema
    set_public_schema()
    
    user = User.objects.create_user(
        email="teacher@center-a.com",
        password="TeacherPass123!",
        first_name="Teacher",
        last_name="CenterA",
        role=User.Role.TEACHER,
        center=center_a,
        is_active=True,
        is_approved=True,
    )
    return user


@pytest.fixture
def teacher_b(db, center_b):
    """Teacher for Center B."""
    from apps.core.tenant_utils import set_public_schema
    set_public_schema()
    
    user = User.objects.create_user(
        email="teacher@center-b.com",
        password="TeacherPass123!",
        first_name="Teacher",
        last_name="CenterB",
        role=User.Role.TEACHER,
        center=center_b,
        is_active=True,
        is_approved=True,
    )
    return user


@pytest.fixture
def student_a(db, center_a):
    """Student for Center A."""
    from apps.core.tenant_utils import set_public_schema
    set_public_schema()
    
    user = User.objects.create_user(
        email="student@center-a.com",
        password="StudentPass123!",
        first_name="Student",
        last_name="CenterA",
        role=User.Role.STUDENT,
        center=center_a,
        is_active=True,
        is_approved=True,
    )
    return user


@pytest.fixture
def student_b(db, center_b):
    """Student for Center B."""
    from apps.core.tenant_utils import set_public_schema
    set_public_schema()
    
    user = User.objects.create_user(
        email="student@center-b.com",
        password="StudentPass123!",
        first_name="Student",
        last_name="CenterB",
        role=User.Role.STUDENT,
        center=center_b,
        is_active=True,
        is_approved=True,
    )
    return user


@pytest.fixture
def guest_a(db, center_a):
    """Guest user for Center A."""
    from apps.core.tenant_utils import set_public_schema
    set_public_schema()
    
    user = User.objects.create_user(
        email="guest@center-a.com",
        password="GuestPass123!",
        first_name="Guest",
        last_name="CenterA",
        role=User.Role.GUEST,
        center=center_a,
        is_active=True,
        is_approved=True,
    )
    return user


@pytest.fixture
def inactive_user_a(db, center_a):
    """Inactive user in Center A (should not be able to log in)."""
    from apps.core.tenant_utils import set_public_schema
    set_public_schema()
    
    user = User.objects.create_user(
        email="inactive@center-a.com",
        password="InactivePass123!",
        first_name="Inactive",
        last_name="User",
        role=User.Role.STUDENT,
        center=center_a,
        is_active=False,
        is_approved=True,
    )
    return user


@pytest.fixture
def unapproved_user_a(db, center_a):
    """Unapproved user in Center A (registered but waiting for admin approval)."""
    from apps.core.tenant_utils import set_public_schema
    set_public_schema()
    
    user = User.objects.create_user(
        email="unapproved@center-a.com",
        password="UnapprovedPass123!",
        first_name="Unapproved",
        last_name="User",
        role=User.Role.STUDENT,
        center=center_a,
        is_active=True,
        is_approved=False,
    )
    return user


@pytest.fixture
def soft_deleted_user_a(db, center_a):
    """Soft-deleted user in Center A (should not be able to log in)."""
    from apps.core.tenant_utils import set_public_schema
    set_public_schema()
    
    user = User.objects.create_user(
        email="deleted@center-a.com",
        password="DeletedPass123!",
        first_name="Deleted",
        last_name="User",
        role=User.Role.STUDENT,
        center=center_a,
        is_active=True,
        is_approved=True,
    )
    # Soft delete the user
    user.soft_delete()
    return user


@pytest.fixture
def invitation_pending_a(db, center_a, center_admin_a):
    """Valid pending invitation for Center A (STUDENT role)."""
    from apps.centers.models import Invitation
    from apps.core.tenant_utils import set_public_schema
    
    set_public_schema()
    
    invitation = Invitation.objects.create(
        code="VALID-CODE-A",
        role="STUDENT",
        center=center_a,
        invited_by=center_admin_a,
        status="PENDING",
        expires_at=timezone.now() + timedelta(days=7),
        is_guest=False,
    )
    return invitation


@pytest.fixture
def invitation_expired_a(db, center_a, center_admin_a):
    """Expired invitation for Center A."""
    from apps.centers.models import Invitation
    from apps.core.tenant_utils import set_public_schema
    
    set_public_schema()
    
    invitation = Invitation.objects.create(
        code="EXPIRE-COD-A",
        role="STUDENT",
        center=center_a,
        invited_by=center_admin_a,
        status="PENDING",
        expires_at=timezone.now() - timedelta(days=1),  # Expired yesterday
        is_guest=False,
    )
    return invitation


@pytest.fixture
def invitation_claimed_a(db, center_a, center_admin_a, student_a):
    """Already claimed invitation for Center A."""
    from apps.centers.models import Invitation
    from apps.core.tenant_utils import set_public_schema
    
    set_public_schema()
    
    invitation = Invitation.objects.create(
        code="CLAIM-COD-A",
        role="STUDENT",
        center=center_a,
        invited_by=center_admin_a,
        target_user=student_a,  # Already claimed
        status="PENDING",
        expires_at=timezone.now() + timedelta(days=7),
        is_guest=False,
    )
    return invitation


@pytest.fixture
def invitation_admin_role_a(db, center_a, center_admin_a):
    """
    Invitation with CENTER_ADMIN role (should not be allowed via public registration).
    """
    from apps.centers.models import Invitation
    from apps.core.tenant_utils import set_public_schema
    
    set_public_schema()
    
    # Note: In the actual Invitation model ROLE_CHOICES, CENTER_ADMIN is not included.
    # This fixture tests the validation that rejects Owner/CenterAdmin registrations.
    # We'll use a mock or create manually if needed in tests.
    invitation = Invitation.objects.create(
        code="ADMIN-COD-A",
        role=User.Role.CENTERADMIN,  # This should be rejected
        center=center_a,
        invited_by=center_admin_a,
        status="PENDING",
        expires_at=timezone.now() + timedelta(days=7),
        is_guest=False,
    )
    return invitation


# Helper utilities


def _create_tenant_schema(schema_name):
    """
    Create a PostgreSQL schema if it doesn't exist.
    This is used for multi-tenancy testing to ensure schema isolation.
    """
    with connection.cursor() as cursor:
        cursor.execute(f"""
            DO $$
            BEGIN
                IF NOT EXISTS (
                    SELECT 1 FROM information_schema.schemata 
                    WHERE schema_name = %s
                ) THEN
                    EXECUTE 'CREATE SCHEMA ' || quote_ident(%s);
                END IF;
            END
            $$;
        """, [schema_name, schema_name])


@pytest.fixture
def cleanup_tenant_schemas(db):
    """
    Cleanup fixture to drop test tenant schemas after tests complete.
    Use this with autouse=True in conftest if you want automatic cleanup.
    """
    yield
    
    # Drop test schemas
    test_schemas = ['tenant_test_center_a', 'tenant_test_center_b']
    with connection.cursor() as cursor:
        for schema_name in test_schemas:
            try:
                cursor.execute(f"DROP SCHEMA IF EXISTS {schema_name} CASCADE;")
            except Exception:
                pass


@pytest.fixture
def mock_request_factory():
    """
    Factory for creating mock request objects with custom hosts.
    Useful for testing subdomain-based authentication logic.
    """
    from unittest.mock import Mock
    
    def _create_mock_request(host="localhost", user=None):
        """
        Create a mock request with specified host.
        
        Args:
            host: The host to return from get_host() (e.g., 'test-center-a.mikan.uz')
            user: Optional user to attach to the request
        
        Returns:
            Mock request object
        """
        request = Mock()
        request.get_host = Mock(return_value=host)
        request.user = user
        request.META = {'HTTP_HOST': host}
        return request
    
    return _create_mock_request


@pytest.fixture
def jwt_auth_header():
    """
    Helper function to generate JWT auth headers for a user.
    Returns a function that takes a user and returns Authorization header dict.
    """
    from rest_framework_simplejwt.tokens import RefreshToken
    
    def _get_auth_header(user):
        """
        Generate JWT token and return Authorization header.
        
        Args:
            user: User instance
            
        Returns:
            dict: {'HTTP_AUTHORIZATION': 'Bearer <token>'}
        """
        refresh = RefreshToken.for_user(user)
        return {'HTTP_AUTHORIZATION': f'Bearer {str(refresh.access_token)}'}
    
    return _get_auth_header


@pytest.fixture(autouse=True)
def ensure_public_schema(db):
    """
    Ensure all tests start in the public schema.
    This prevents schema leakage between tests.
    
    Uses 'db' fixture to enable database access.
    Skips schema setup for SQLite (testing database).
    """
    from django.db import connection
    
    # Only set schema for PostgreSQL (not for SQLite in testing)
    if connection.vendor == 'postgresql':
        from apps.core.tenant_utils import set_public_schema
        set_public_schema()
    
    yield
    
    if connection.vendor == 'postgresql':
        from apps.core.tenant_utils import set_public_schema
        set_public_schema()


@pytest.fixture
def suspended_center(db):
    """
    Suspended center for testing login restrictions.
    Users from suspended centers should not be able to log in.
    """
    from apps.centers.models import Center
    from apps.core.tenant_utils import set_public_schema
    from django.utils import timezone
    from datetime import timedelta
    
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
    from apps.centers.models import Subscription
    subscription = Subscription.objects.get(center=center)
    subscription.starts_at = timezone.now() - timedelta(days=65)
    subscription.ends_at = timezone.now() - timedelta(days=5)  # Expired 5 days ago
    subscription.is_active = False
    subscription.save()
    
    _create_tenant_schema(center.schema_name)
    
    return center


@pytest.fixture
def student_in_suspended_center(db, suspended_center):
    """Student in a suspended center (should not be able to log in)."""
    from apps.core.tenant_utils import set_public_schema
    set_public_schema()
    
    user = User.objects.create_user(
        email="student@suspended.com",
        password="StudentPass123!",
        first_name="Student",
        last_name="Suspended",
        role=User.Role.STUDENT,
        center=suspended_center,
        is_active=True,
        is_approved=True,
    )
    return user
