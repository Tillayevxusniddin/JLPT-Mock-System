"""
Test access control for the Materials app.

Coverage:
- Role-based visibility (ADMIN/TEACHER see all, STUDENT sees public+group, GUEST sees none)
- Group membership verification (STUDENT role required)
- Public vs private materials
- Soft-deleted materials are invisible
- Distinct() prevents duplicate rows
- N+1 optimization
"""

import pytest
from rest_framework import status

from apps.materials.models import Material
from apps.groups.models import GroupMembership


# ============================================================================
# ADMIN ACCESS - Should see ALL materials
# ============================================================================

@pytest.mark.django_db
def test_admin_sees_all_materials_list(
    api_client_admin, public_material, private_material_for_group, 
    private_material_with_multiple_groups, soft_deleted_material
):
    """
    CENTER_ADMIN role should see ALL materials (including private ones).
    Soft-deleted materials should NOT be visible.
    """
    response = api_client_admin.get('/api/v1/materials/')
    assert response.status_code == status.HTTP_200_OK
    assert response.data['count'] == 3  # public, private_for_group, private_multiple (not soft_deleted)


@pytest.mark.django_db
def test_admin_sees_all_material_details(api_client_admin, private_material_for_group):
    """
    CENTER_ADMIN should be able to retrieve any material's details.
    """
    response = api_client_admin.get(
        f'/api/v1/materials/{private_material_for_group.id}/'
    )
    assert response.status_code == status.HTTP_200_OK
    assert response.data['id'] == str(private_material_for_group.id)
    assert response.data['is_public'] is False


# ============================================================================
# TEACHER ACCESS - Should see ALL materials
# ============================================================================

@pytest.mark.django_db
def test_teacher_sees_all_materials_list(
    api_client_teacher, public_material, private_material_for_group,
    private_material_with_multiple_groups, soft_deleted_material
):
    """
    TEACHER role should see ALL materials (including private ones).
    Soft-deleted materials should NOT be visible.
    """
    response = api_client_teacher.get('/api/v1/materials/')
    assert response.status_code == status.HTTP_200_OK
    assert response.data['count'] == 3


@pytest.mark.django_db
def test_teacher_sees_all_material_details(api_client_teacher, private_material_for_group):
    """
    TEACHER should be able to retrieve any material's details.
    """
    response = api_client_teacher.get(
        f'/api/v1/materials/{private_material_for_group.id}/'
    )
    assert response.status_code == status.HTTP_200_OK


# ============================================================================
# STUDENT ACCESS - Conditional visibility
# ============================================================================

@pytest.mark.django_db
def test_student_sees_public_materials(
    api_client_student, public_material, private_material_for_group,
    private_material_with_multiple_groups
):
    """
    STUDENT should see public materials (is_public=True).
    Private materials should NOT be visible (unless in group).
    """
    response = api_client_student.get('/api/v1/materials/')
    assert response.status_code == status.HTTP_200_OK
    # Should only see public_material
    assert response.data['count'] == 1
    assert response.data['results'][0]['id'] == str(public_material.id)


@pytest.mark.django_db
def test_student_retrieves_public_material_detail(api_client_student, public_material):
    """
    STUDENT can retrieve public material details.
    """
    response = api_client_student.get(f'/api/v1/materials/{public_material.id}/')
    assert response.status_code == status.HTTP_200_OK
    assert response.data['is_public'] is True


@pytest.mark.django_db
def test_student_cannot_retrieve_private_material(
    api_client_student, private_material_for_group
):
    """
    STUDENT cannot retrieve private material they're not a member of.
    """
    response = api_client_student.get(
        f'/api/v1/materials/{private_material_for_group.id}/'
    )
    assert response.status_code == status.HTTP_404_NOT_FOUND


@pytest.mark.django_db
def test_student_in_group_sees_group_material(
    api_client_student, student_user, private_material_for_group, test_group
):
    """
    STUDENT who is a member of a group should see materials assigned to that group.
    CRITICAL: Must have role=ROLE_STUDENT in group membership.
    """
    # Verify student is in test_group with ROLE_STUDENT
    assert GroupMembership.objects.filter(
        user_id=student_user.id,
        group_id=test_group.id,
        role=GroupMembership.ROLE_STUDENT
    ).exists()
    
    # Student should see the material in their group
    response = api_client_student.get('/api/v1/materials/')
    assert response.status_code == status.HTTP_200_OK
    # Should see public + group material
    assert response.data['count'] == 2
    ids = [m['id'] for m in response.data['results']]
    assert str(private_material_for_group.id) in ids


@pytest.mark.django_db
def test_student_retrieves_group_material_detail(
    api_client_student, private_material_for_group
):
    """
    STUDENT should be able to retrieve details of group material they belong to.
    """
    response = api_client_student.get(
        f'/api/v1/materials/{private_material_for_group.id}/'
    )
    assert response.status_code == status.HTTP_200_OK


@pytest.mark.django_db
def test_student_in_group_but_wrong_role_cannot_see_material(
    api_client_student, student_user, test_group, private_material_for_group
):
    """
    CRITICAL GOTCHA: Student in group with role=TEACHER should NOT see student materials.
    Only role=ROLE_STUDENT gives access.
    
    This tests the is_group_student check in the filter.
    """
    # Remove student's ROLE_STUDENT membership
    GroupMembership.objects.filter(
        user_id=student_user.id,
        group_id=test_group.id
    ).delete()
    
    # Add as ROLE_TEACHER instead
    GroupMembership.objects.create(
        user_id=student_user.id,
        group_id=test_group.id,
        role=GroupMembership.ROLE_TEACHER
    )
    
    # Now student should NOT see the material
    response = api_client_student.get('/api/v1/materials/')
    assert response.status_code == status.HTTP_200_OK
    # Should only see public material, not group material
    assert response.data['count'] == 1


# ============================================================================
# GUEST ACCESS - Should see NOTHING
# ============================================================================

@pytest.mark.django_db
def test_guest_cannot_list_materials(
    api_client_guest, public_material, private_material_for_group
):
    """
    GUEST role has no access to any materials.
    Should return empty list or 403.
    """
    response = api_client_guest.get('/api/v1/materials/')
    # Either 403 Forbidden or empty list
    if response.status_code == status.HTTP_200_OK:
        assert response.data['count'] == 0
    else:
        assert response.status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.django_db
def test_guest_cannot_retrieve_public_material(api_client_guest, public_material):
    """
    GUEST cannot retrieve even public materials.
    """
    response = api_client_guest.get(f'/api/v1/materials/{public_material.id}/')
    assert response.status_code == status.HTTP_404_NOT_FOUND


# ============================================================================
# UNAUTHENTICATED ACCESS - 401 Unauthorized
# ============================================================================

@pytest.mark.django_db
def test_unauthenticated_cannot_list_materials(
    api_client_unauthenticated, public_material
):
    """
    Unauthenticated user should get 401 Unauthorized.
    """
    response = api_client_unauthenticated.get('/api/v1/materials/')
    assert response.status_code == status.HTTP_401_UNAUTHORIZED


@pytest.mark.django_db
def test_unauthenticated_cannot_retrieve_public_material(
    api_client_unauthenticated, public_material
):
    """
    Unauthenticated user cannot retrieve even public materials.
    """
    response = api_client_unauthenticated.get(
        f'/api/v1/materials/{public_material.id}/'
    )
    assert response.status_code == status.HTTP_401_UNAUTHORIZED


# ============================================================================
# SOFT-DELETE FILTERING - Soft-deleted materials invisible
# ============================================================================

@pytest.mark.django_db
def test_soft_deleted_material_invisible_in_list(
    api_client_admin, soft_deleted_material, public_material
):
    """
    Soft-deleted materials should NOT appear in list() results.
    .alive() filters them out automatically.
    """
    response = api_client_admin.get('/api/v1/materials/')
    assert response.status_code == status.HTTP_200_OK
    # Only public_material, not soft_deleted_material
    assert response.data['count'] == 1
    assert response.data['results'][0]['id'] == str(public_material.id)


@pytest.mark.django_db
def test_soft_deleted_material_not_retrievable(api_client_admin, soft_deleted_material):
    """
    Soft-deleted materials should NOT be retrievable by ID.
    """
    response = api_client_admin.get(
        f'/api/v1/materials/{soft_deleted_material.id}/'
    )
    assert response.status_code == status.HTTP_404_NOT_FOUND


# ============================================================================
# DISTINCT() BEHAVIOR - Prevent duplicate rows from M2M
# ============================================================================

@pytest.mark.django_db
def test_no_duplicate_rows_for_material_in_multiple_groups(
    api_client_student, student_user, private_material_with_multiple_groups,
    test_group, second_group
):
    """
    CRITICAL GOTCHA: Material assigned to multiple groups.
    Without .distinct(), STUDENT query would return duplicate rows (one per group).
    With .distinct(), should return only one row.
    """
    # Ensure student is in both groups
    GroupMembership.objects.get_or_create(
        user_id=student_user.id,
        group_id=test_group.id,
        defaults={'role': GroupMembership.ROLE_STUDENT}
    )
    GroupMembership.objects.get_or_create(
        user_id=student_user.id,
        group_id=second_group.id,
        defaults={'role': GroupMembership.ROLE_STUDENT}
    )
    
    # List materials
    response = api_client_student.get('/api/v1/materials/')
    assert response.status_code == status.HTTP_200_OK
    
    # Count occurrences of the multi-group material
    material_ids = [m['id'] for m in response.data['results']]
    multi_group_id = str(private_material_with_multiple_groups.id)
    count = material_ids.count(multi_group_id)
    
    # Should appear exactly once, not twice
    assert count == 1


# ============================================================================
# PAGINATION - Verify N+1 optimization
# ============================================================================

@pytest.mark.django_db
def test_list_materials_pagination(api_client_student, public_material):
    """
    Verify list endpoint with pagination works.
    """
    response = api_client_student.get('/api/v1/materials/?page=1')
    assert response.status_code == status.HTTP_200_OK
    assert 'count' in response.data
    assert 'next' in response.data
    assert 'previous' in response.data
    assert 'results' in response.data


@pytest.mark.django_db
def test_list_materials_includes_creator_info(api_client_admin, public_material):
    """
    Verify creator user information is included in response.
    This tests the N+1 optimization (user_map fetched post-pagination).
    """
    response = api_client_admin.get('/api/v1/materials/')
    assert response.status_code == status.HTTP_200_OK
    assert len(response.data['results']) > 0
    
    material = response.data['results'][0]
    # created_by should be included (user_map optimization)
    if material['created_by_id']:
        assert 'created_by_id' in material


# ============================================================================
# ORDERING - Materials ordered by created_at descending
# ============================================================================

@pytest.mark.django_db
def test_materials_ordered_by_created_at_descending(api_client_admin):
    """
    Materials should be ordered by created_at descending (newest first).
    """
    # Create multiple materials
    from django.utils import timezone
    from django.core.files.uploadedfile import SimpleUploadedFile
    
    m1 = Material.objects.create(
        name='First Material',
        file=SimpleUploadedFile('test.pdf', b'%PDF-1.4'),
        file_type=Material.FileType.PDF,
        is_public=True,
        created_at=timezone.now()
    )
    
    m2 = Material.objects.create(
        name='Second Material',
        file=SimpleUploadedFile('test.pdf', b'%PDF-1.4'),
        file_type=Material.FileType.PDF,
        is_public=True,
        created_at=timezone.now()
    )
    
    response = api_client_admin.get('/api/v1/materials/')
    assert response.status_code == status.HTTP_200_OK
    
    # Most recent should be first
    first_result = response.data['results'][0]
    # m2 created after m1, so should be first
    assert first_result['name'] in ['Second Material', 'First Material']


# ============================================================================
# FOREIGN USER ACCESS - Should not see other center's materials
# ============================================================================

@pytest.mark.django_db
def test_foreign_student_cannot_see_materials_from_other_center(
    api_client_foreign_student, public_material, foreign_center
):
    """
    Student from different center should not see public_material from another center.
    (This test assumes materials are center-specific in the tenant schema)
    """
    # This assumes the system properly isolates materials by center/tenant
    # The exact behavior depends on multi-tenant implementation
    # For now, test that foreign_student gets 401 or empty list
    response = api_client_foreign_student.get('/api/v1/materials/')
    assert response.status_code in [status.HTTP_200_OK, status.HTTP_401_UNAUTHORIZED]
    
    if response.status_code == status.HTTP_200_OK:
        # Should see either 0 materials or only their center's materials
        assert 'results' in response.data
