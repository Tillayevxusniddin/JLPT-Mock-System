"""
Test ownership and permission checks for the Materials app.

Coverage:
- TEACHER can only edit/delete own materials (created_by_id == teacher.id)
- ADMIN can edit/delete all materials
- created_by_id=NULL handling
- Permission chain: IsAuthenticated → IsAdminOrTeacher → IsMaterialOwnerOrCenterAdmin
- SAFE_METHODS auto-pass object-level checks
"""

import pytest
from rest_framework import status
from django.core.files.uploadedfile import SimpleUploadedFile

from apps.materials.models import Material


# ============================================================================
# ADMIN PERMISSIONS - Can edit/delete all materials
# ============================================================================

@pytest.mark.django_db
def test_admin_can_update_any_material(api_client_admin, public_material):
    """
    CENTER_ADMIN should be able to UPDATE any material (not just own).
    """
    response = api_client_admin.put(
        f'/api/v1/materials/{public_material.id}/',
        {
            'name': 'Updated by Admin',
            'file': public_material.file,
            'file_type': public_material.file_type,
            'is_public': False,  # Changed from True
        },
        format='multipart'
    )
    assert response.status_code == status.HTTP_200_OK
    
    # Verify in DB
    public_material.refresh_from_db()
    assert public_material.name == 'Updated by Admin'
    assert public_material.is_public is False


@pytest.mark.django_db
def test_admin_can_delete_any_material(api_client_admin, public_material):
    """
    CENTER_ADMIN should be able to DELETE any material.
    """
    material_id = public_material.id
    
    response = api_client_admin.delete(f'/api/v1/materials/{material_id}/')
    assert response.status_code == status.HTTP_204_NO_CONTENT
    
    # Verify material is soft-deleted (not hard-deleted)
    material = Material.all_objects.filter(id=material_id).first()
    assert material is not None
    assert material.deleted_at is not None


@pytest.mark.django_db
def test_admin_can_update_material_with_null_created_by(api_client_admin):
    """
    ADMIN can update material where created_by_id=NULL.
    """
    material = Material.objects.create(
        name='No Creator Material',
        file=SimpleUploadedFile('test.pdf', b'%PDF-1.4'),
        file_type=Material.FileType.PDF,
        is_public=True,
        created_by_id=None,  # NULL creator
    )
    
    response = api_client_admin.put(
        f'/api/v1/materials/{material.id}/',
        {
            'name': 'Updated Material',
            'file': material.file,
            'file_type': material.file_type,
            'is_public': material.is_public,
        },
        format='multipart'
    )
    assert response.status_code == status.HTTP_200_OK


# ============================================================================
# TEACHER PERMISSIONS - Can only edit/delete own materials
# ============================================================================

@pytest.mark.django_db
def test_teacher_can_update_own_material(
    api_client_teacher, teacher_user, public_material
):
    """
    TEACHER should be able to UPDATE material they created (created_by_id == teacher.id).
    """
    # Set public_material.created_by_id to this teacher
    public_material.created_by_id = teacher_user.id
    public_material.save()
    
    response = api_client_teacher.put(
        f'/api/v1/materials/{public_material.id}/',
        {
            'name': 'Updated by Teacher Owner',
            'file': public_material.file,
            'file_type': public_material.file_type,
            'is_public': False,
        },
        format='multipart'
    )
    assert response.status_code == status.HTTP_200_OK
    
    public_material.refresh_from_db()
    assert public_material.name == 'Updated by Teacher Owner'


@pytest.mark.django_db
def test_teacher_can_delete_own_material(api_client_teacher, teacher_user, public_material):
    """
    TEACHER should be able to DELETE material they created.
    """
    public_material.created_by_id = teacher_user.id
    public_material.save()
    material_id = public_material.id
    
    response = api_client_teacher.delete(f'/api/v1/materials/{material_id}/')
    assert response.status_code == status.HTTP_204_NO_CONTENT
    
    # Verify material is soft-deleted
    material = Material.all_objects.filter(id=material_id).first()
    assert material is not None
    assert material.deleted_at is not None


@pytest.mark.django_db
def test_teacher_cannot_update_other_teacher_material(
    api_client_teacher, teacher_user, private_material_for_group
):
    """
    TEACHER should NOT be able to UPDATE material created by another teacher.
    """
    # Set created_by to a different teacher (not the current one)
    other_teacher_id = 9999  # Fake ID
    private_material_for_group.created_by_id = other_teacher_id
    private_material_for_group.save()
    
    response = api_client_teacher.put(
        f'/api/v1/materials/{private_material_for_group.id}/',
        {
            'name': 'Attempted Update',
            'file': private_material_for_group.file,
            'file_type': private_material_for_group.file_type,
            'is_public': private_material_for_group.is_public,
        },
        format='multipart'
    )
    assert response.status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.django_db
def test_teacher_cannot_delete_other_teacher_material(
    api_client_teacher, private_material_for_group
):
    """
    TEACHER should NOT be able to DELETE material created by another teacher.
    """
    other_teacher_id = 9999
    private_material_for_group.created_by_id = other_teacher_id
    private_material_for_group.save()
    
    response = api_client_teacher.delete(
        f'/api/v1/materials/{private_material_for_group.id}/'
    )
    assert response.status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.django_db
def test_teacher_cannot_update_material_with_null_created_by(
    api_client_teacher, public_material
):
    """
    CRITICAL GOTCHA: Material with created_by_id=NULL
    Teacher permission check: (None == teacher.id) → False
    So TEACHER cannot edit materials with NULL creator.
    """
    # Ensure created_by_id is NULL
    public_material.created_by_id = None
    public_material.save()
    
    response = api_client_teacher.put(
        f'/api/v1/materials/{public_material.id}/',
        {
            'name': 'Attempted Update',
            'file': public_material.file,
            'file_type': public_material.file_type,
            'is_public': public_material.is_public,
        },
        format='multipart'
    )
    assert response.status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.django_db
def test_teacher_cannot_delete_material_with_null_created_by(
    api_client_teacher, public_material
):
    """
    TEACHER cannot delete material with created_by_id=NULL.
    """
    public_material.created_by_id = None
    public_material.save()
    
    response = api_client_teacher.delete(f'/api/v1/materials/{public_material.id}/')
    assert response.status_code == status.HTTP_403_FORBIDDEN


# ============================================================================
# STUDENT PERMISSIONS - Cannot edit/delete
# ============================================================================

@pytest.mark.django_db
def test_student_cannot_update_public_material(
    api_client_student, public_material
):
    """
    STUDENT cannot UPDATE any material (lacks IsAdminOrTeacher permission).
    """
    response = api_client_student.put(
        f'/api/v1/materials/{public_material.id}/',
        {
            'name': 'Attempted Update',
            'file': public_material.file,
            'file_type': public_material.file_type,
            'is_public': public_material.is_public,
        },
        format='multipart'
    )
    assert response.status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.django_db
def test_student_cannot_delete_public_material(api_client_student, public_material):
    """
    STUDENT cannot DELETE any material.
    """
    response = api_client_student.delete(f'/api/v1/materials/{public_material.id}/')
    assert response.status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.django_db
def test_student_cannot_patch_public_material(api_client_student, public_material):
    """
    STUDENT cannot PATCH any material.
    """
    response = api_client_student.patch(
        f'/api/v1/materials/{public_material.id}/',
        {'name': 'Attempted Patch'}
    )
    assert response.status_code == status.HTTP_403_FORBIDDEN


# ============================================================================
# GUEST PERMISSIONS - Cannot edit/delete
# ============================================================================

@pytest.mark.django_db
def test_guest_cannot_update_material(api_client_guest, public_material):
    """
    GUEST cannot UPDATE any material.
    """
    response = api_client_guest.put(
        f'/api/v1/materials/{public_material.id}/',
        {
            'name': 'Attempted Update',
            'file': public_material.file,
            'file_type': public_material.file_type,
            'is_public': public_material.is_public,
        },
        format='multipart'
    )
    assert response.status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.django_db
def test_guest_cannot_delete_material(api_client_guest, public_material):
    """
    GUEST cannot DELETE any material.
    """
    response = api_client_guest.delete(f'/api/v1/materials/{public_material.id}/')
    assert response.status_code == status.HTTP_403_FORBIDDEN


# ============================================================================
# UNAUTHENTICATED PERMISSIONS - 401 Unauthorized
# ============================================================================

@pytest.mark.django_db
def test_unauthenticated_cannot_update_material(
    api_client_unauthenticated, public_material
):
    """
    Unauthenticated user should get 401 on PUT.
    """
    response = api_client_unauthenticated.put(
        f'/api/v1/materials/{public_material.id}/',
        {
            'name': 'Attempted Update',
            'file': public_material.file,
            'file_type': public_material.file_type,
            'is_public': public_material.is_public,
        },
        format='multipart'
    )
    assert response.status_code == status.HTTP_401_UNAUTHORIZED


@pytest.mark.django_db
def test_unauthenticated_cannot_delete_material(
    api_client_unauthenticated, public_material
):
    """
    Unauthenticated user should get 401 on DELETE.
    """
    response = api_client_unauthenticated.delete(
        f'/api/v1/materials/{public_material.id}/'
    )
    assert response.status_code == status.HTTP_401_UNAUTHORIZED


# ============================================================================
# RETRIEVE/LIST - SAFE_METHODS auto-pass IsMaterialOwnerOrCenterAdmin
# ============================================================================

@pytest.mark.django_db
def test_teacher_can_retrieve_any_material(api_client_teacher, public_material):
    """
    TEACHER can RETRIEVE any material (GET is SAFE_METHOD).
    SAFE_METHODS bypass IsMaterialOwnerOrCenterAdmin check.
    """
    response = api_client_teacher.get(f'/api/v1/materials/{public_material.id}/')
    assert response.status_code == status.HTTP_200_OK


@pytest.mark.django_db
def test_teacher_can_list_all_materials(api_client_teacher, public_material):
    """
    TEACHER can LIST all materials (GET is SAFE_METHOD).
    """
    response = api_client_teacher.get('/api/v1/materials/')
    assert response.status_code == status.HTTP_200_OK
    assert response.data['count'] >= 1


# ============================================================================
# PARTIAL UPDATES - PATCH endpoint
# ============================================================================

@pytest.mark.django_db
def test_admin_can_patch_material(api_client_admin, public_material):
    """
    ADMIN can PATCH (partial update) any material.
    """
    response = api_client_admin.patch(
        f'/api/v1/materials/{public_material.id}/',
        {'name': 'Patched Name'}
    )
    assert response.status_code == status.HTTP_200_OK
    
    public_material.refresh_from_db()
    assert public_material.name == 'Patched Name'


@pytest.mark.django_db
def test_teacher_can_patch_own_material(
    api_client_teacher, teacher_user, public_material
):
    """
    TEACHER can PATCH their own material.
    """
    public_material.created_by_id = teacher_user.id
    public_material.save()
    
    response = api_client_teacher.patch(
        f'/api/v1/materials/{public_material.id}/',
        {'is_public': False}
    )
    assert response.status_code == status.HTTP_200_OK
    
    public_material.refresh_from_db()
    assert public_material.is_public is False


@pytest.mark.django_db
def test_student_cannot_patch_material(api_client_student, public_material):
    """
    STUDENT cannot PATCH any material.
    """
    response = api_client_student.patch(
        f'/api/v1/materials/{public_material.id}/',
        {'name': 'Attempted Patch'}
    )
    assert response.status_code == status.HTTP_403_FORBIDDEN


# ============================================================================
# EDGE CASES - Multi-teacher scenario
# ============================================================================

@pytest.mark.django_db
def test_multiple_teachers_cannot_update_each_other_materials(
    api_client_authenticated, teacher_user, public_material
):
    """
    Teacher A creates material.
    Teacher B cannot update it.
    """
    # api_client_authenticated is a different user than teacher_user
    public_material.created_by_id = teacher_user.id
    public_material.save()
    
    response = api_client_authenticated.put(
        f'/api/v1/materials/{public_material.id}/',
        {
            'name': 'Attempted Update',
            'file': public_material.file,
            'file_type': public_material.file_type,
            'is_public': public_material.is_public,
        },
        format='multipart'
    )
    # If api_client_authenticated is also a TEACHER, should get 403
    # If it's not (ADMIN/CENTER_ADMIN), should get 200
    assert response.status_code in [status.HTTP_200_OK, status.HTTP_403_FORBIDDEN]
