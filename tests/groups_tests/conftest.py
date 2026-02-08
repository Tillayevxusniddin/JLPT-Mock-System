"""
Comprehensive test fixtures for Groups app.

This conftest creates tenant schemas before any tests run, using a subprocess
to avoid Django's atomic transaction issues.
"""

import pytest
import subprocess
import os
from rest_framework.test import APIClient
from uuid import uuid4
from django.db import connection

from apps.groups.models import Group, GroupMembership, GroupMembershipHistory
from apps.authentication.models import User


# ============================================================================
# Session Setup: Create Tenant Schemas (outside Django's transaction)
# ============================================================================

@pytest.fixture(scope="session", autouse=True)
def create_tenant_schemas():
    """Create all test tenant schemas using psql subprocess (outside Django transaction)."""
    # Get database connection info from Django settings
    from django.conf import settings
    db_config = settings.DATABASES['default']
    
    # pytest prefixes test database names with 'test_'
    db_name = 'test_' + db_config.get('NAME', 'jlpt_mock_db_test')
    db_host = db_config.get('HOST', 'localhost')
    db_port = db_config.get('PORT', '5432')
    db_user = db_config.get('USER', 'postgres')
    db_password = db_config.get('PASSWORD', '')
    
    # Prepare psql connection string
    psql_env = os.environ.copy()
    if db_password:
        psql_env['PGPASSWORD'] = db_password
    
    psql_cmd = [
        'psql', 
        f'--host={db_host}',
        f'--port={db_port}',
        f'--username={db_user}',
        f'--dbname={db_name}',
    ]
    
    # SQL commands to create schemas and tables
    sql_commands = """
    -- Create tenant schemas if they don't exist
    CREATE SCHEMA IF NOT EXISTS tenant_test_center;
    CREATE SCHEMA IF NOT EXISTS tenant_foreign_center;
    
    -- Create groups table in tenant_test_center
    CREATE TABLE IF NOT EXISTS tenant_test_center.groups (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
        updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
        deleted_at TIMESTAMP WITH TIME ZONE,
        name VARCHAR(255) NOT NULL,
        description TEXT DEFAULT '',
        avatar VARCHAR(100) DEFAULT '',
        max_students INTEGER DEFAULT 30,
        is_active BOOLEAN DEFAULT TRUE,
        student_count INTEGER DEFAULT 0,
        teacher_count INTEGER DEFAULT 0,
        UNIQUE(name)
    );
    
    -- Create groupmembership table in tenant_test_center
    CREATE TABLE IF NOT EXISTS tenant_test_center.groupmembership (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
        updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
        deleted_at TIMESTAMP WITH TIME ZONE,
        group_id UUID NOT NULL REFERENCES tenant_test_center.groups(id) ON DELETE CASCADE,
        user_id BIGINT NOT NULL,
        role_in_group VARCHAR(10) NOT NULL,
        UNIQUE(user_id, group_id, role_in_group)
    );
    
    -- Create groupmembershiphistory table in tenant_test_center
    CREATE TABLE IF NOT EXISTS tenant_test_center.groupmembershiphistory (
        id SERIAL PRIMARY KEY,
        group_id UUID NOT NULL REFERENCES tenant_test_center.groups(id) ON DELETE CASCADE,
        user_id BIGINT NOT NULL,
        role_in_group VARCHAR(10) NOT NULL,
        joined_at TIMESTAMP WITH TIME ZONE,
        left_at TIMESTAMP WITH TIME ZONE,
        left_reason VARCHAR(20)
    );
    
    -- Create tables in tenant_foreign_center
    CREATE TABLE IF NOT EXISTS tenant_foreign_center.groups (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
        updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
        deleted_at TIMESTAMP WITH TIME ZONE,
        name VARCHAR(255) NOT NULL,
        description TEXT DEFAULT '',
        avatar VARCHAR(100) DEFAULT '',
        max_students INTEGER DEFAULT 30,
        is_active BOOLEAN DEFAULT TRUE,
        student_count INTEGER DEFAULT 0,
        teacher_count INTEGER DEFAULT 0,
        UNIQUE(name)
    );
    
    CREATE TABLE IF NOT EXISTS tenant_foreign_center.groupmembership (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
        updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
        deleted_at TIMESTAMP WITH TIME ZONE,
        group_id UUID NOT NULL REFERENCES tenant_foreign_center.groups(id) ON DELETE CASCADE,
        user_id BIGINT NOT NULL,
        role_in_group VARCHAR(10) NOT NULL,
        UNIQUE(user_id, group_id, role_in_group)
    );
    
    CREATE TABLE IF NOT EXISTS tenant_foreign_center.groupmembershiphistory (
        id SERIAL PRIMARY KEY,
        group_id UUID NOT NULL REFERENCES tenant_foreign_center.groups(id) ON DELETE CASCADE,
        user_id BIGINT NOT NULL,
        role_in_group VARCHAR(10) NOT NULL,
        joined_at TIMESTAMP WITH TIME ZONE,
        left_at TIMESTAMP WITH TIME ZONE,
        left_reason VARCHAR(20)
    );
    """
    
    # Execute SQL via psql subprocess
    try:
        result = subprocess.run(
            psql_cmd,
            input=sql_commands,
            text=True,
            capture_output=True,
            env=psql_env,
            timeout=10
        )
        if result.returncode != 0:
            print(f"Warning: psql setup had issues: {result.stderr}")
    except Exception as e:
        print(f"Warning: Could not create tenant schemas via psql: {e}")
        # Don't fail tests if schema creation fails - it might already exist


# ============================================================================
# Core Test Utilities
# ============================================================================

@pytest.fixture
def api_client():
    """DRF APIClient for making API requests."""
    client = APIClient()
    return client


# ============================================================================
# Center and Organization Fixtures
# ============================================================================

@pytest.fixture
def test_center(db):
    """Create a test center in public schema."""
    from apps.core.tenant_utils import set_public_schema
    from apps.centers.models import Center
    
    set_public_schema()
    center, created = Center.objects.get_or_create(
        id=1,
        defaults={
            'name': 'Test Center',
            'slug': 'test-center',
            'schema_name': 'tenant_test_center',
            'email': 'test@center.com',
            'phone': '+1234567890',
            'status': Center.Status.ACTIVE,
            'is_ready': True,
        }
    )
    return center


@pytest.fixture
def foreign_test_center(db):
    """Create a foreign center for cross-center isolation testing."""
    from apps.core.tenant_utils import set_public_schema
    from apps.centers.models import Center
    
    set_public_schema()
    center, created = Center.objects.get_or_create(
        id=2,
        defaults={
            'name': 'Foreign Center',
            'slug': 'foreign-center',
            'schema_name': 'tenant_foreign_center',
            'email': 'foreign@center.com',
            'phone': '+9876543210',
            'status': Center.Status.ACTIVE,
            'is_ready': True,
        }
    )
    return center


# ============================================================================
# User Fixtures
# ============================================================================

def get_auth_header(user):
    """Generate JWT auth header value for a user."""
    from rest_framework_simplejwt.tokens import RefreshToken
    
    refresh = RefreshToken.for_user(user)
    return f'Bearer {str(refresh.access_token)}'


@pytest.fixture
def center_admin_user(db, test_center):
    """Create a CENTER_ADMIN user."""
    from apps.core.tenant_utils import set_public_schema
    
    set_public_schema()
    user = User.objects.create_user(
        email='admin@test.com',
        password='Pass123!',
        first_name='Admin',
        last_name='User',
        role=User.Role.CENTERADMIN,
        center=test_center,
        is_active=True,
        is_approved=True,
    )
    return user


@pytest.fixture
def teacher_user(db, test_center):
    """Create a TEACHER user."""
    from apps.core.tenant_utils import set_public_schema
    
    set_public_schema()
    user = User.objects.create_user(
        email='teacher@test.com',
        password='Pass123!',
        first_name='Teacher',
        last_name='User',
        role=User.Role.TEACHER,
        center=test_center,
        is_active=True,
        is_approved=True,
    )
    return user


@pytest.fixture
def teacher_user_2(db, test_center):
    """Create a second TEACHER user."""
    from apps.core.tenant_utils import set_public_schema
    
    set_public_schema()
    user = User.objects.create_user(
        email='teacher2@test.com',
        password='Pass123!',
        first_name='Teacher2',
        last_name='User',
        role=User.Role.TEACHER,
        center=test_center,
        is_active=True,
        is_approved=True,
    )
    return user


@pytest.fixture
def student_user(db, test_center):
    """Create a STUDENT user."""
    from apps.core.tenant_utils import set_public_schema
    
    set_public_schema()
    user = User.objects.create_user(
        email='student@test.com',
        password='Pass123!',
        first_name='Student',
        last_name='User',
        role=User.Role.STUDENT,
        center=test_center,
        is_active=True,
        is_approved=True,
    )
    return user


@pytest.fixture
def student_user_2(db, test_center):
    """Create a second STUDENT user."""
    from apps.core.tenant_utils import set_public_schema
    
    set_public_schema()
    user = User.objects.create_user(
        email='student2@test.com',
        password='Pass123!',
        first_name='Student2',
        last_name='User',
        role=User.Role.STUDENT,
        center=test_center,
        is_active=True,
        is_approved=True,
    )
    return user


@pytest.fixture
def guest_user(db, test_center):
    """Create a GUEST user."""
    from apps.core.tenant_utils import set_public_schema
    
    set_public_schema()
    user = User.objects.create_user(
        email='guest@test.com',
        password='Pass123!',
        first_name='Guest',
        last_name='User',
        role=User.Role.GUEST,
        center=test_center,
        is_active=True,
        is_approved=True,
    )
    return user


@pytest.fixture
def foreign_center_teacher(db, foreign_test_center):
    """Create a TEACHER from a different center."""
    from apps.core.tenant_utils import set_public_schema
    
    set_public_schema()
    user = User.objects.create_user(
        email='foreign_teacher@test.com',
        password='Pass123!',
        first_name='Foreign',
        last_name='Teacher',
        role=User.Role.TEACHER,
        center=foreign_test_center,
        is_active=True,
        is_approved=True,
    )
    return user


# ============================================================================
# Auth Header Fixtures
# ============================================================================

@pytest.fixture
def center_admin_headers(center_admin_user):
    """Auth header for CENTER_ADMIN."""
    return get_auth_header(center_admin_user)


@pytest.fixture
def teacher_headers(teacher_user):
    """Auth header for TEACHER."""
    return get_auth_header(teacher_user)


@pytest.fixture
def student_headers(student_user):
    """Auth header for STUDENT."""
    return get_auth_header(student_user)


@pytest.fixture
def guest_headers(guest_user):
    """Auth header for GUEST."""
    return get_auth_header(guest_user)


@pytest.fixture
def foreign_center_headers(foreign_center_teacher):
    """Auth header for foreign center teacher."""
    return get_auth_header(foreign_center_teacher)


# ============================================================================
# Group Fixtures
# ============================================================================

@pytest.fixture
def group_default(db, test_center):
    """Create a default group in tenant schema."""
    from apps.core.tenant_utils import set_tenant_schema
    
    set_tenant_schema(test_center.schema_name)
    group = Group.objects.create(
        id=uuid4(),
        name="Default Group",
        description="A default group for testing",
        max_students=30,
        is_active=True,
        student_count=0,
        teacher_count=0,
    )
    return group


@pytest.fixture
def group_small(db, test_center):
    """Create a small group with limited capacity."""
    from apps.core.tenant_utils import set_tenant_schema
    
    set_tenant_schema(test_center.schema_name)
    group = Group.objects.create(
        id=uuid4(),
        name="Small Group",
        description="A group with limited capacity",
        max_students=2,
        is_active=True,
        student_count=0,
        teacher_count=0,
    )
    return group


@pytest.fixture
def group_inactive(db, test_center):
    """Create an inactive group."""
    from apps.core.tenant_utils import set_tenant_schema
    
    set_tenant_schema(test_center.schema_name)
    group = Group.objects.create(
        id=uuid4(),
        name="Inactive Group",
        description="An inactive group",
        max_students=30,
        is_active=False,
        student_count=0,
        teacher_count=0,
    )
    return group


@pytest.fixture
def group_with_teacher(db, test_center, teacher_user):
    """Create a group with a teacher assigned."""
    from apps.core.tenant_utils import set_tenant_schema
    
    set_tenant_schema(test_center.schema_name)
    group = Group.objects.create(
        id=uuid4(),
        name="Group With Teacher",
        description="A group with a teacher",
        max_students=30,
        is_active=True,
        student_count=0,
        teacher_count=1,
    )
    
    # Add teacher to group
    GroupMembership.objects.create(
        group=group,
        user_id=teacher_user.id,
        role_in_group=GroupMembership.ROLE_TEACHER,
    )
    
    return group
