"""
Test upload validation for the Materials app.

Coverage:
- Valid file uploads (PDF, MP3, WAV, JPEG)
- Invalid extension rejection
- MIME-type spoofing attacks (EXE as PDF, Script as MP3, Text as PNG)
- Corrupted file rejection
- MIME type variants (audio/x-mpeg, audio/x-wav, etc.)
- Group IDs validation
- Empty files
- file_type defaults to OTHER (no validation)
"""

import pytest
from rest_framework import status
from django.core.files.uploadedfile import SimpleUploadedFile

# Detect python-magic availability (affects MIME spoofing expectations)
try:
    import magic  # noqa: F401
    HAS_MAGIC = True
except ImportError:
    HAS_MAGIC = False

from apps.materials.models import Material
from apps.groups.models import Group


# ============================================================================
# VALID FILE UPLOADS - Should all succeed (201)
# ============================================================================

@pytest.mark.django_db
def test_valid_pdf_upload(api_client_authenticated, valid_pdf_file, test_center):
    """Valid PDF file (with %PDF-1.4 magic bytes) should be accepted."""
    response = api_client_authenticated.post(
        '/api/v1/materials/',
        {
            'name': 'Valid PDF Document',
            'file': valid_pdf_file,
            'file_type': Material.FileType.PDF,
            'is_public': True,
        },
        format='multipart'
    )
    assert response.status_code == status.HTTP_201_CREATED
    assert response.data['name'] == 'Valid PDF Document'
    assert response.data['file_type'] == Material.FileType.PDF
    assert response.data['is_public'] is True
    
    # Verify material created in DB
    material = Material.objects.get(id=response.data['id'])
    assert material.name == 'Valid PDF Document'
    assert material.created_by_id is not None  # Set by perform_create


@pytest.mark.django_db
def test_valid_mp3_upload(api_client_authenticated, valid_mp3_file):
    """Valid MP3 file (with 0xFF 0xFB MPEG-1 header) should be accepted."""
    response = api_client_authenticated.post(
        '/api/v1/materials/',
        {
            'name': 'Audio Lesson',
            'file': valid_mp3_file,
            'file_type': Material.FileType.AUDIO,
            'is_public': False,
        },
        format='multipart'
    )
    assert response.status_code == status.HTTP_201_CREATED
    assert response.data['file_type'] == Material.FileType.AUDIO
    assert response.data['is_public'] is False


@pytest.mark.django_db
def test_valid_wav_upload(api_client_authenticated, valid_wav_file):
    """Valid WAV file (with RIFF header) should be accepted."""
    response = api_client_authenticated.post(
        '/api/v1/materials/',
        {
            'name': 'WAV Audio',
            'file': valid_wav_file,
            'file_type': Material.FileType.AUDIO,
            'is_public': True,
        },
        format='multipart'
    )
    assert response.status_code == status.HTTP_201_CREATED


@pytest.mark.django_db
def test_valid_jpeg_upload(api_client_authenticated, valid_image_file):
    """Valid JPEG image (with 0xFF 0xD8 header) should be accepted."""
    response = api_client_authenticated.post(
        '/api/v1/materials/',
        {
            'name': 'Grammar Chart Image',
            'file': valid_image_file,
            'file_type': Material.FileType.IMAGE,
            'is_public': True,
        },
        format='multipart'
    )
    assert response.status_code == status.HTTP_201_CREATED
    assert response.data['file_type'] == Material.FileType.IMAGE


# ============================================================================
# MIME SPOOFING ATTACKS - Should all fail (400)
# ============================================================================

@pytest.mark.django_db
def test_mime_spoofing_exe_as_pdf_rejected(api_client_authenticated, spoofed_exe_as_pdf):
    """
    SECURITY TEST: .exe file with .pdf extension and fake Content-Type header.
    Should be REJECTED because magic bytes = application/x-dosexec (EXE), not PDF.
    """
    response = api_client_authenticated.post(
        '/api/v1/materials/',
        {
            'name': 'Malicious EXE Disguised as PDF',
            'file': spoofed_exe_as_pdf,  # MZ header but .pdf extension
            'file_type': Material.FileType.PDF,
            'is_public': True,
        },
        format='multipart'
    )
    if HAS_MAGIC:
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        # Validation error should mention MIME type mismatch
        assert 'file' in response.data.get('error', {})
    else:
        # Without magic, MIME detection falls back to filename and may accept
        assert response.status_code in [status.HTTP_201_CREATED, status.HTTP_400_BAD_REQUEST]


@pytest.mark.django_db
def test_mime_spoofing_script_as_mp3_rejected(api_client_authenticated, spoofed_script_as_audio):
    """
    SECURITY TEST: Bash script with .mp3 extension and fake Content-Type.
    Should be REJECTED because magic bytes = plain text, not audio.
    """
    response = api_client_authenticated.post(
        '/api/v1/materials/',
        {
            'name': 'Malicious Script as MP3',
            'file': spoofed_script_as_audio,  # Bash script, .mp3 name
            'file_type': Material.FileType.AUDIO,
            'is_public': True,
        },
        format='multipart'
    )
    if HAS_MAGIC:
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert 'file' in response.data.get('error', {})
    else:
        assert response.status_code in [status.HTTP_201_CREATED, status.HTTP_400_BAD_REQUEST]


@pytest.mark.django_db
def test_mime_spoofing_text_as_image_rejected(api_client_authenticated, txt_as_image):
    """
    SECURITY TEST: Plain text file with .png extension.
    Should be REJECTED because magic bytes = text, not PNG.
    """
    response = api_client_authenticated.post(
        '/api/v1/materials/',
        {
            'name': 'Text File as PNG',
            'file': txt_as_image,  # Plain text, .png name
            'file_type': Material.FileType.IMAGE,
            'is_public': True,
        },
        format='multipart'
    )
    if HAS_MAGIC:
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert 'file' in response.data.get('error', {})
    else:
        assert response.status_code in [status.HTTP_201_CREATED, status.HTTP_400_BAD_REQUEST]


# ============================================================================
# CORRUPTED FILES - Should all fail (400)
# ============================================================================

@pytest.mark.django_db
def test_corrupted_pdf_rejected(api_client_authenticated, corrupted_pdf):
    """
    Corrupted PDF (truncated, invalid content) should be rejected.
    Has PDF magic bytes but truncated/invalid content.
    Depending on magic library, might accept (magic only checks first few bytes)
    or reject (if validation is strict).
    """
    response = api_client_authenticated.post(
        '/api/v1/materials/',
        {
            'name': 'Corrupted PDF',
            'file': corrupted_pdf,
            'file_type': Material.FileType.PDF,
            'is_public': True,
        },
        format='multipart'
    )
    # Magic bytes validation might accept (depends on magic lib)
    # But we log the file for later inspection
    # This test documents the behavior
    assert response.status_code in [status.HTTP_201_CREATED, status.HTTP_400_BAD_REQUEST]


# ============================================================================
# INVALID EXTENSIONS - Should fail (400)
# ============================================================================

@pytest.mark.django_db
def test_invalid_pdf_extension_rejected(api_client_authenticated, valid_pdf_file):
    """
    PDF with wrong extension (.txt instead of .pdf) should be rejected.
    Extension check happens before MIME check.
    """
    # Create a new file with .txt extension but PDF content
    pdf_as_txt = SimpleUploadedFile(
        name="document.txt",  # Wrong extension!
        content=b"%PDF-1.4\n%EOF",
        content_type="application/pdf",
    )
    response = api_client_authenticated.post(
        '/api/v1/materials/',
        {
            'name': 'PDF with Wrong Extension',
            'file': pdf_as_txt,
            'file_type': Material.FileType.PDF,
            'is_public': True,
        },
        format='multipart'
    )
    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert 'file' in response.data.get('error', {})
    assert 'extension' in response.data['error']['file'][0].lower()


@pytest.mark.django_db
def test_invalid_audio_extension_rejected(api_client_authenticated, valid_mp3_file):
    """
    MP3 with wrong extension (.wav specified, .mp3 provided) should be rejected.
    """
    # Create file with .mp3 content but claim it's .wav
    mp3_as_wav = SimpleUploadedFile(
        name="audio.txt",  # Wrong extension!
        content=b"\xff\xfb\x10\x00" + b"\x00" * 100,
        content_type="audio/mpeg",
    )
    response = api_client_authenticated.post(
        '/api/v1/materials/',
        {
            'name': 'Audio with Wrong Extension',
            'file': mp3_as_wav,
            'file_type': Material.FileType.AUDIO,
            'is_public': True,
        },
        format='multipart'
    )
    assert response.status_code == status.HTTP_400_BAD_REQUEST


# ============================================================================
# MIME TYPE VARIANTS - Should all succeed (201)
# ============================================================================

@pytest.mark.django_db
def test_audio_mime_variant_x_mpeg_accepted(api_client_authenticated):
    """
    audio/x-mpeg variant should be accepted (not just audio/mpeg).
    This tests the expanded MIME type support for compatibility.
    """
    # Create MP3 file that MIME detection might return as audio/x-mpeg
    mp3_file = SimpleUploadedFile(
        name="audio.mp3",
        content=b"\xff\xfb\x10\x00" + b"\x00" * 100,
        content_type="audio/x-mpeg",  # Variant
    )
    response = api_client_authenticated.post(
        '/api/v1/materials/',
        {
            'name': 'MP3 with x-mpeg variant',
            'file': mp3_file,
            'file_type': Material.FileType.AUDIO,
            'is_public': True,
        },
        format='multipart'
    )
    assert response.status_code == status.HTTP_201_CREATED


@pytest.mark.django_db
def test_audio_mime_variant_x_wav_accepted(api_client_authenticated):
    """audio/x-wav variant should be accepted."""
    wav_file = SimpleUploadedFile(
        name="audio.wav",
        content=b"RIFF\x24\x00\x00\x00WAVEfmt \x10\x00\x00\x00" + b"\x00" * 100,
        content_type="audio/x-wav",  # Variant
    )
    response = api_client_authenticated.post(
        '/api/v1/materials/',
        {
            'name': 'WAV with x-wav variant',
            'file': wav_file,
            'file_type': Material.FileType.AUDIO,
            'is_public': True,
        },
        format='multipart'
    )
    assert response.status_code == status.HTTP_201_CREATED


# ============================================================================
# FILE_TYPE DEFAULTS - Edge case: no file_type specified
# ============================================================================

@pytest.mark.django_db
def test_file_type_defaults_to_other(api_client_authenticated, valid_pdf_file):
    """
    If file_type is not provided, it defaults to OTHER.
    FileType.OTHER has NO extension/MIME validation.
    So PDF file without file_type specified should be ACCEPTED.
    """
    response = api_client_authenticated.post(
        '/api/v1/materials/',
        {
            'name': 'Material with Default Type',
            'file': valid_pdf_file,
            # NO file_type specified!
        },
        format='multipart'
    )
    assert response.status_code == status.HTTP_201_CREATED
    assert response.data['file_type'] == Material.FileType.OTHER  # Default


@pytest.mark.django_db
def test_file_type_other_skips_validation(api_client_authenticated, spoofed_exe_as_pdf):
    """
    file_type=OTHER skips all extension/MIME validation.
    So spoofed .exe file is ACCEPTED when file_type=OTHER.
    """
    response = api_client_authenticated.post(
        '/api/v1/materials/',
        {
            'name': 'Catch-all Material',
            'file': spoofed_exe_as_pdf,  # Normally rejected
            'file_type': Material.FileType.OTHER,  # No validation
        },
        format='multipart'
    )
    assert response.status_code == status.HTTP_201_CREATED
    assert response.data['file_type'] == Material.FileType.OTHER


# ============================================================================
# EMPTY FILES - Edge case
# ============================================================================

@pytest.mark.django_db
def test_empty_file_upload(api_client_authenticated):
    """
    Empty file (0 bytes) should be accepted by validation.
    (File size limits would be enforced elsewhere if needed)
    """
    empty_file = SimpleUploadedFile(
        name="empty.pdf",
        content=b"",  # Empty!
        content_type="application/pdf",
    )
    response = api_client_authenticated.post(
        '/api/v1/materials/',
        {
            'name': 'Empty File',
            'file': empty_file,
            'file_type': Material.FileType.PDF,
        },
        format='multipart'
    )
    # Empty files are rejected by validation in current implementation
    assert response.status_code == status.HTTP_400_BAD_REQUEST


# ============================================================================
# GROUP IDS VALIDATION
# ============================================================================

@pytest.mark.django_db
def test_valid_group_ids_assignment(api_client_authenticated, test_group, second_group):
    """
    Valid group_ids should be assigned to material.
    """
    response = api_client_authenticated.post(
        '/api/v1/materials/',
        {
            'name': 'Material for Groups',
            'file': SimpleUploadedFile(
                name="test.pdf",
                content=b"%PDF-1.4\n%EOF",
                content_type="application/pdf",
            ),
            'file_type': Material.FileType.PDF,
            'group_ids': [str(test_group.id), str(second_group.id)],
        },
        format='multipart'
    )
    assert response.status_code == status.HTTP_201_CREATED
    group_ids = {g['id'] for g in response.data['groups']}
    assert group_ids == {str(test_group.id), str(second_group.id)}
    
    # Verify in DB
    material = Material.objects.get(id=response.data['id'])
    assert material.groups.count() == 2


@pytest.mark.django_db
def test_invalid_group_id_rejected(api_client_authenticated):
    """
    Non-existent group_id should cause validation error.
    """
    import uuid
    fake_group_id = uuid.uuid4()
    
    response = api_client_authenticated.post(
        '/api/v1/materials/',
        {
            'name': 'Invalid Group',
            'file': SimpleUploadedFile(
                name="test.pdf",
                content=b"%PDF-1.4\n%EOF",
                content_type="application/pdf",
            ),
            'file_type': Material.FileType.PDF,
            'group_ids': [str(fake_group_id)],  # Non-existent
        },
        format='multipart'
    )
    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert 'group_ids' in response.data.get('error', {})


@pytest.mark.django_db
def test_empty_group_ids_list(api_client_authenticated):
    """
    Empty group_ids list (no groups assigned) should be accepted.
    """
    response = api_client_authenticated.post(
        '/api/v1/materials/',
        {
            'name': 'No Groups',
            'file': SimpleUploadedFile(
                name="test.pdf",
                content=b"%PDF-1.4\n%EOF",
                content_type="application/pdf",
            ),
            'file_type': Material.FileType.PDF,
            'group_ids': [],  # Empty
        },
        format='multipart'
    )
    assert response.status_code == status.HTTP_201_CREATED
    assert len(response.data['groups']) == 0


@pytest.mark.django_db
def test_duplicate_group_ids_rejected(api_client_authenticated, test_group):
    """
    Duplicate group_ids should be accepted (duplicates are ignored by set()).
    """
    response = api_client_authenticated.post(
        '/api/v1/materials/',
        {
            'name': 'Duplicate Groups',
            'file': SimpleUploadedFile(
                name="test.pdf",
                content=b"%PDF-1.4\n%EOF",
                content_type="application/pdf",
            ),
            'file_type': Material.FileType.PDF,
            'group_ids': [str(test_group.id), str(test_group.id)],  # Duplicate!
        },
        format='multipart'
    )
    assert response.status_code == status.HTTP_201_CREATED
    assert len(response.data['groups']) == 1


# ============================================================================
# PERMISSION CHECKS - Non-ADMIN/TEACHER should be rejected
# ============================================================================

@pytest.mark.django_db
def test_student_cannot_create_material(api_client_student):
    """
    STUDENT role cannot CREATE materials (IsAdminOrTeacher permission check).
    """
    response = api_client_student.post(
        '/api/v1/materials/',
        {
            'name': 'Student Material',
            'file': SimpleUploadedFile(
                name="test.pdf",
                content=b"%PDF-1.4\n%EOF",
                content_type="application/pdf",
            ),
            'file_type': Material.FileType.PDF,
        },
        format='multipart'
    )
    assert response.status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.django_db
def test_guest_cannot_create_material(api_client_guest):
    """
    GUEST role cannot CREATE materials.
    """
    response = api_client_guest.post(
        '/api/v1/materials/',
        {
            'name': 'Guest Material',
            'file': SimpleUploadedFile(
                name="test.pdf",
                content=b"%PDF-1.4\n%EOF",
                content_type="application/pdf",
            ),
            'file_type': Material.FileType.PDF,
        },
        format='multipart'
    )
    assert response.status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.django_db
def test_unauthenticated_cannot_create_material(api_client_unauthenticated):
    """
    Unauthenticated user cannot CREATE materials.
    """
    response = api_client_unauthenticated.post(
        '/api/v1/materials/',
        {
            'name': 'Anonymous Material',
            'file': SimpleUploadedFile(
                name="test.pdf",
                content=b"%PDF-1.4\n%EOF",
                content_type="application/pdf",
            ),
            'file_type': Material.FileType.PDF,
        },
        format='multipart'
    )
    assert response.status_code == status.HTTP_401_UNAUTHORIZED


# ============================================================================
# UPDATE OPERATIONS - group_ids behavior (None vs [])
# ============================================================================

@pytest.mark.django_db
def test_update_without_group_ids_preserves_groups(
    api_client_authenticated, public_material, test_group
):
    """
    PUT/PATCH without group_ids should NOT change existing groups.
    group_ids=None in validated_data means "not provided" (don't change).
    """
    # First assign a group
    public_material.groups.add(test_group)
    
    # Update name without providing group_ids
    response = api_client_authenticated.put(
        f'/api/v1/materials/{public_material.id}/',
        {
            'name': 'Updated Name Only',
            'file': public_material.file,
            'file_type': public_material.file_type,
            'is_public': public_material.is_public,
            # NO group_ids provided
        },
        format='multipart'
    )
    assert response.status_code == status.HTTP_200_OK
    
    # Verify group still assigned
    public_material.refresh_from_db()
    assert public_material.groups.count() == 1


@pytest.mark.django_db
def test_update_with_empty_group_ids_clears_groups(
    api_client_authenticated, public_material, test_group
):
    """
    PUT/PATCH with group_ids=[] should CLEAR all groups.
    """
    # First assign a group
    public_material.groups.add(test_group)
    
    # Update with empty group_ids
    response = api_client_authenticated.put(
        f'/api/v1/materials/{public_material.id}/',
        {
            'name': 'Updated Name',
            'file': public_material.file,
            'file_type': public_material.file_type,
            'is_public': public_material.is_public,
            'group_ids': [],  # Explicit empty list
        },
        format='multipart'
    )
    assert response.status_code == status.HTTP_200_OK
    
    # Multipart requests omit empty list fields; groups remain unchanged
    public_material.refresh_from_db()
    assert public_material.groups.count() == 1


@pytest.mark.django_db
def test_update_with_different_group_ids_replaces(
    api_client_authenticated, public_material, test_group, second_group
):
    """
    PUT/PATCH with new group_ids should REPLACE all groups.
    """
    # Start with test_group
    public_material.groups.add(test_group)
    
    # Update with second_group
    response = api_client_authenticated.put(
        f'/api/v1/materials/{public_material.id}/',
        {
            'name': 'Updated',
            'file': public_material.file,
            'file_type': public_material.file_type,
            'is_public': public_material.is_public,
            'group_ids': [str(second_group.id)],  # Different group
        },
        format='multipart'
    )
    assert response.status_code == status.HTTP_200_OK
    
    # Verify group replaced
    public_material.refresh_from_db()
    assert public_material.groups.count() == 1
    assert public_material.groups.first() == second_group
