"""
Fixtures for Materials app tests.

Includes:
- Mock file uploads (valid PDF, MP3, spoofed files)
- Center and Group setup for multi-tenant testing
- User fixtures with different roles (ADMIN, TEACHER, STUDENT, GUEST)
- Storage mock to prevent real filesystem/S3 access
- Material fixtures (public and private/group-restricted)
"""

import io
import json
import subprocess
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile, InMemoryUploadedFile
from django.test import override_settings
from django.utils import timezone

from apps.authentication.models import User
from apps.centers.models import Center
from apps.groups.models import Group, GroupMembership
from apps.materials.models import Material


# ============================================================================
# DISABLE POSTGRESQL-SPECIFIC SIGNALS FOR SQLITE TESTS
# ============================================================================

@pytest.fixture(scope="session", autouse=True)
def disable_center_schema_creation_for_tests():
    """
    Disable Center signals during tests (PostgreSQL-specific).
    These signals fail with SQLite, so we disconnect them.
    Auto-runs for all tests in this session.
    """
    from django.db.models.signals import post_save
    from apps.centers.signals import (
        run_migrations_for_new_center,
        create_free_subscription_for_new_center
    )
    post_save.disconnect(run_migrations_for_new_center, sender=Center)
    post_save.disconnect(create_free_subscription_for_new_center, sender=Center)


# ============================================================================
# TENANT SCHEMA SETUP (mirrors groups_tests/conftest.py pattern)
# ============================================================================

@pytest.fixture(scope="session", autouse=True)
def setup_test_schemas(django_db_blocker):
    """
    Setup for multi-tenant materials testing.
    Tests run in the default (public) schema for simplicity.
    Tenant schema creation is skipped - not needed for unit tests.
    """
    pass  # Tests run in default public schema


# ============================================================================
# CENTERS FIXTURES
# ============================================================================

@pytest.fixture
def test_center(db):
    """Test center with schema tenant_test_center."""
    center = Center.objects.create(
        name="Test Center",
        schema_name="tenant_test_center",
    )
    return center


@pytest.fixture
def foreign_center(db):
    """Foreign center with schema tenant_foreign_center (for isolation testing)."""
    center = Center.objects.create(
        name="Foreign Center",
        schema_name="tenant_foreign_center",
    )
    return center


# ============================================================================
# USER FIXTURES (across different roles)
# ============================================================================

@pytest.fixture
def admin_user(db, test_center):
    """CENTER_ADMIN user."""
    user = User.objects.create_user(
        email="admin@test.com",
        password="testpass123",
        role="CENTER_ADMIN",
        center_id=test_center.id,
    )
    return user


@pytest.fixture
def teacher_user(db, test_center):
    """TEACHER user."""
    user = User.objects.create_user(
        email="teacher@test.com",
        password="testpass123",
        role="TEACHER",
        center_id=test_center.id,
    )
    return user


@pytest.fixture
def student_user(db, test_center):
    """STUDENT user."""
    user = User.objects.create_user(
        email="student@test.com",
        password="testpass123",
        role="STUDENT",
        center_id=test_center.id,
    )
    return user


@pytest.fixture
def guest_user(db, test_center):
    """GUEST user (no group membership)."""
    user = User.objects.create_user(
        email="guest@test.com",
        password="testpass123",
        role="GUEST",
        center_id=test_center.id,
    )
    return user


@pytest.fixture
def foreign_student_user(db, foreign_center):
    """STUDENT user in foreign center (for isolation testing)."""
    user = User.objects.create_user(
        email="foreign@test.com",
        password="testpass123",
        role="STUDENT",
        center_id=foreign_center.id,
    )
    return user


# ============================================================================
# GROUPS AND MEMBERSHIPS FIXTURES
# ============================================================================

@pytest.fixture
def test_group(db, test_center):
    """Group in test center."""
    group = Group.objects.create(
        name="Group A",
        description="Test group for materials",
        max_students=30,
        is_active=True,
        center_id=test_center.id,
    )
    return group


@pytest.fixture
def second_group(db, test_center):
    """Second group in test center (for group membership tests)."""
    group = Group.objects.create(
        name="Group B",
        description="Second test group",
        max_students=20,
        is_active=True,
        center_id=test_center.id,
    )
    return group


@pytest.fixture
def student_in_group(db, student_user, test_group):
    """Student with STUDENT role membership in test_group."""
    membership = GroupMembership.objects.create(
        user_id=student_user.id,
        group=test_group,
        role_in_group=GroupMembership.ROLE_STUDENT,
    )
    return membership


@pytest.fixture
def teacher_in_group(db, teacher_user, test_group):
    """Teacher with TEACHER role membership in test_group."""
    membership = GroupMembership.objects.create(
        user_id=teacher_user.id,
        group=test_group,
        role_in_group=GroupMembership.ROLE_TEACHER,
    )
    return membership


@pytest.fixture
def student_in_second_group(db, student_user, second_group):
    """Student membership in second_group (for access control tests)."""
    membership = GroupMembership.objects.create(
        user_id=student_user.id,
        group=second_group,
        role_in_group=GroupMembership.ROLE_STUDENT,
    )
    return membership


# ============================================================================
# MOCK FILE FIXTURES (SimpleUploadedFile)
# ============================================================================

@pytest.fixture
def valid_pdf_file():
    """
    Valid PDF file (with actual PDF magic bytes).
    PDF files start with %PDF- (25 50 44 46 in hex).
    """
    pdf_content = b"%PDF-1.4\n%EOF"  # Minimal valid PDF
    return SimpleUploadedFile(
        name="test_document.pdf",
        content=pdf_content,
        content_type="application/pdf",
    )


@pytest.fixture
def valid_mp3_file():
    """
    Valid MP3 file (with actual MP3 magic bytes).
    MP3 files start with 0xFF 0xFB (MPEG-1 Layer 3) or 0xFF 0xFA (MPEG-2 Layer 3).
    """
    mp3_content = b"\xff\xfb\x10\x00" + b"\x00" * 100  # MPEG-1 Layer 3 header + data
    return SimpleUploadedFile(
        name="test_audio.mp3",
        content=mp3_content,
        content_type="audio/mpeg",
    )


@pytest.fixture
def valid_wav_file():
    """
    Valid WAV file (with actual WAV magic bytes).
    WAV files start with RIFF header (52 49 46 46 in hex).
    """
    wav_content = b"RIFF\x24\x00\x00\x00WAVEfmt \x10\x00\x00\x00" + b"\x00" * 100
    return SimpleUploadedFile(
        name="test_audio.wav",
        content=wav_content,
        content_type="audio/wav",
    )


@pytest.fixture
def valid_image_file():
    """
    Valid JPEG image file (with actual JPEG magic bytes).
    JPEG files start with 0xFF 0xD8.
    """
    jpeg_content = b"\xff\xd8\xff\xe0\x00\x10JFIF" + b"\x00" * 100
    return SimpleUploadedFile(
        name="test_image.jpg",
        content=jpeg_content,
        content_type="image/jpeg",
    )


@pytest.fixture
def spoofed_exe_as_pdf():
    """
    SPOOFED FILE: .pdf extension but actually an EXE (Windows PE header).
    MIME spoofing attack test.
    Content starts with MZ (4D 5A in hex), which is PE/EXE header.
    """
    exe_content = b"MZ\x90\x00" + b"\x00" * 100  # Windows PE header
    return SimpleUploadedFile(
        name="malicious.pdf",
        content=exe_content,
        content_type="application/pdf",  # LIE: claims to be PDF but is actually EXE
    )


@pytest.fixture
def spoofed_script_as_audio():
    """
    SPOOFED FILE: .mp3 extension but actually a shell script.
    Content is plain text bash script, not binary audio.
    """
    script_content = b"#!/bin/bash\nrm -rf /\n"
    return SimpleUploadedFile(
        name="malicious.mp3",
        content=script_content,
        content_type="audio/mpeg",  # LIE: claims to be MP3 but is actually a script
    )


@pytest.fixture
def txt_as_image():
    """
    SPOOFED FILE: .png extension but actually a text file.
    """
    txt_content = b"This is just plain text, not a PNG image!"
    return SimpleUploadedFile(
        name="fake_image.png",
        content=txt_content,
        content_type="image/png",  # LIE: claims to be PNG but is actually text
    )


@pytest.fixture
def corrupted_pdf():
    """
    Corrupted PDF file: starts with correct magic bytes but truncated.
    """
    pdf_content = b"%PDF-1.4"  # PDF header but no valid content
    return SimpleUploadedFile(
        name="corrupted.pdf",
        content=pdf_content,
        content_type="application/pdf",
    )


# ============================================================================
# STORAGE MOCKING (prevent real filesystem/S3 access)
# ============================================================================

@pytest.fixture
def mock_storage():
    """
    Mock django.core.files.storage.default_storage to prevent real filesystem/S3 access.
    Provides in-memory storage for testing.
    """
    with patch("django.core.files.storage.default_storage") as mock_store:
        # Mock save() method
        mock_store.save.return_value = "mocked/path/test_file.pdf"
        
        # Mock delete() method
        mock_store.delete.return_value = None
        
        # Mock url() method
        mock_store.url.return_value = "http://mock-storage.test/mocked/path/test_file.pdf"
        
        # Mock exists() method
        mock_store.exists.return_value = True
        
        # Mock open() method for reading
        mock_store.open.return_value = io.BytesIO(b"mock file content")
        
        yield mock_store


# ============================================================================
# MATERIAL FIXTURES (public and private)
# ============================================================================

@pytest.fixture
def public_material(db, admin_user, test_center):
    """
    Public material visible to all students.
    is_public=True, no specific group assignment.
    """
    material = Material.objects.create(
        name="Public JLPT Grammar Guide",
        file=SimpleUploadedFile(
            name="grammar_guide.pdf",
            content=b"%PDF-1.4\n%EOF",
            content_type="application/pdf",
        ),
        file_type=Material.FileType.PDF,
        created_by_id=admin_user.id,
        is_public=True,
    )
    return material


@pytest.fixture
def private_material_for_group(db, admin_user, test_center, test_group):
    """
    Private material assigned to specific group (test_group).
    is_public=False, assigned to test_group.
    Only students in test_group can see this.
    """
    material = Material.objects.create(
        name="Group A - Kanji Workbook",
        file=SimpleUploadedFile(
            name="kanji_workbook.pdf",
            content=b"%PDF-1.4\n%EOF",
            content_type="application/pdf",
        ),
        file_type=Material.FileType.PDF,
        created_by_id=admin_user.id,
        is_public=False,
    )
    material.groups.add(test_group)
    return material


@pytest.fixture
def private_material_for_second_group(db, admin_user, test_center, second_group):
    """
    Private material assigned only to second_group.
    Test isolation: student in test_group should NOT see this.
    """
    material = Material.objects.create(
        name="Group B - Listening Practice",
        file=SimpleUploadedFile(
            name="listening_practice.mp3",
            content=b"\xff\xfb\x10\x00" + b"\x00" * 100,
            content_type="audio/mpeg",
        ),
        file_type=Material.FileType.AUDIO,
        created_by_id=admin_user.id,
        is_public=False,
    )
    material.groups.add(second_group)
    return material


@pytest.fixture
def soft_deleted_material(db, admin_user, test_center):
    """
    Soft-deleted material.
    Should NOT appear in list() queries (using .alive() filter).
    """
    material = Material.objects.create(
        name="Archived Material",
        file=SimpleUploadedFile(
            name="archived.pdf",
            content=b"%PDF-1.4\n%EOF",
            content_type="application/pdf",
        ),
        file_type=Material.FileType.PDF,
        created_by_id=admin_user.id,
        is_public=True,
    )
    # Soft delete the material
    material.soft_delete()
    return material


@pytest.fixture
def private_material_with_multiple_groups(db, admin_user, test_center, test_group, second_group):
    """
    Material assigned to multiple groups.
    Students in either group can access it.
    Tests .distinct() requirement to prevent duplicate rows.
    """
    material = Material.objects.create(
        name="Multi-Group Teaching Materials",
        file=SimpleUploadedFile(
            name="multi_group.pdf",
            content=b"%PDF-1.4\n%EOF",
            content_type="application/pdf",
        ),
        file_type=Material.FileType.PDF,
        created_by_id=admin_user.id,
        is_public=False,
    )
    material.groups.add(test_group, second_group)
    return material


# ============================================================================
# AUTHENTICATED API CLIENT FIXTURES
# ============================================================================

@pytest.fixture
def api_client_authenticated(db, admin_user, test_center):
    """
    Authenticated API client as CENTER_ADMIN.
    Uses force_authenticate instead of JWT tokens for simpler testing.
    """
    from rest_framework.test import APIClient

    client = APIClient()
    # Use force_authenticate to bypass JWT token requirement in tests
    client.force_authenticate(user=admin_user)
    return client


@pytest.fixture
def api_client_admin(db, admin_user, test_center):
    """Authenticated API client as CENTER_ADMIN."""
    from rest_framework.test import APIClient

    client = APIClient()
    client.force_authenticate(user=admin_user)
    return client


@pytest.fixture
def api_client_teacher(db, teacher_user, test_center):
    """Authenticated API client as TEACHER."""
    from rest_framework.test import APIClient

    client = APIClient()
    client.force_authenticate(user=teacher_user)
    return client


@pytest.fixture
def api_client_student(db, student_user, test_center):
    """Authenticated API client as STUDENT."""
    from rest_framework.test import APIClient

    client = APIClient()
    client.force_authenticate(user=student_user)
    return client


@pytest.fixture
def api_client_guest(db, guest_user, test_center):
    """Authenticated API client as GUEST (read-only)."""
    from rest_framework.test import APIClient

    client = APIClient()
    client.force_authenticate(user=guest_user)
    return client


@pytest.fixture
def api_client_foreign_student(db, foreign_student_user, foreign_center):
    """Authenticated API client as STUDENT from foreign center."""
    from rest_framework.test import APIClient

    client = APIClient()
    client.force_authenticate(user=foreign_student_user)
    return client


@pytest.fixture
def api_client_unauthenticated():
    """Unauthenticated API client (no auth headers)."""
    from rest_framework.test import APIClient
    return APIClient()


# ============================================================================
# OVERRIDE SETTINGS FOR TESTS
# ============================================================================

@pytest.fixture
def disable_atomic_requests(settings):
    """
    Override ATOMIC_REQUESTS to False for tests.
    Critical for multi-tenant schema testing.
    """
    settings.DATABASES["default"]["ATOMIC_REQUESTS"] = False
    return settings


@pytest.fixture
def mock_file_storage(settings, tmp_path):
    """
    Override FILE_UPLOAD_TEMP_DIR and MEDIA_ROOT to use tmp_path.
    Prevents tests from touching real filesystem.
    """
    with override_settings(
        FILE_UPLOAD_TEMP_DIR=str(tmp_path / "temp"),
        MEDIA_ROOT=str(tmp_path / "media"),
    ):
        yield settings
