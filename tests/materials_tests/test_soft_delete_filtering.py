"""
Test soft-delete filtering for the Materials app.

Coverage:
- Soft-deleted materials excluded from get_queryset()
- Soft-deleted materials not retrievable
- .alive() and .dead() manager methods
- Filter chains with .alive()
- Restoration of soft-deleted materials
"""

import pytest
from rest_framework import status
from django.utils import timezone
from unittest.mock import patch

from apps.materials.models import Material


# ============================================================================
# SOFT-DELETE FILTERING - Queryset exclusion
# ============================================================================

@pytest.mark.django_db
def test_soft_deleted_excluded_from_objects_manager(soft_deleted_material, public_material):
    """
    Material.objects (SoftDeleteManager) auto-excludes soft-deleted.
    """
    # Count active materials
    active_count = Material.objects.count()
    
    # Should not include soft_deleted_material
    assert soft_deleted_material not in Material.objects.all()
    assert public_material in Material.objects.all()


@pytest.mark.django_db
def test_soft_deleted_included_in_all_objects_manager(soft_deleted_material, public_material):
    """
    Material.all_objects includes all materials (including soft-deleted).
    """
    all_count = Material.all_objects.count()
    
    # Should include both
    assert soft_deleted_material in Material.all_objects.all()
    assert public_material in Material.all_objects.all()


@pytest.mark.django_db
def test_alive_method_excludes_soft_deleted(soft_deleted_material, public_material):
    """
    .alive() returns only non-deleted materials.
    """
    alive = Material.objects.alive()
    
    assert soft_deleted_material not in alive
    assert public_material in alive
    assert alive.count() >= 1


@pytest.mark.django_db
def test_dead_method_returns_only_soft_deleted(soft_deleted_material, public_material):
    """
    .dead() returns only soft-deleted materials.
    """
    dead = Material.objects.dead()
    
    assert soft_deleted_material in dead
    assert public_material not in dead


# ============================================================================
# VISIBILITY IN API ENDPOINTS - Soft-deleted not returned
# ============================================================================

@pytest.mark.django_db
def test_soft_deleted_not_in_list_response(api_client_admin, soft_deleted_material, public_material):
    """
    GET /materials/ should not include soft-deleted materials.
    """
    response = api_client_admin.get('/api/v1/materials/')
    assert response.status_code == status.HTTP_200_OK
    
    ids = [m['id'] for m in response.data['results']]
    
    # Should include public_material, not soft_deleted_material
    assert str(public_material.id) in ids
    assert str(soft_deleted_material.id) not in ids


@pytest.mark.django_db
def test_soft_deleted_not_retrievable_by_id(api_client_admin, soft_deleted_material):
    """
    GET /materials/{id}/ should return 404 for soft-deleted material.
    """
    response = api_client_admin.get(f'/api/v1/materials/{soft_deleted_material.id}/')
    
    # Should be 404 (not found)
    assert response.status_code == status.HTTP_404_NOT_FOUND


@pytest.mark.django_db
def test_soft_deleted_not_visible_to_any_role(
    api_client_admin, api_client_teacher, api_client_student, soft_deleted_material
):
    """
    Soft-deleted materials are invisible to all roles (ADMIN, TEACHER, STUDENT).
    """
    # Try to retrieve as each role
    for api_client in [api_client_admin, api_client_teacher, api_client_student]:
        response = api_client.get(f'/api/v1/materials/{soft_deleted_material.id}/')
        assert response.status_code == status.HTTP_404_NOT_FOUND


# ============================================================================
# SOFT-DELETE OPERATION
# ============================================================================

@pytest.mark.django_db
def test_delete_sets_deleted_at(public_material):
    """
    Calling delete() on material sets deleted_at timestamp.
    """
    before_delete = timezone.now()
    
    public_material.delete()
    
    after_delete = timezone.now()
    
    # deleted_at should be set
    public_material.refresh_from_db()
    assert public_material.deleted_at is not None
    assert before_delete <= public_material.deleted_at <= after_delete


@pytest.mark.django_db
def test_delete_preserves_other_fields(public_material):
    """
    Soft delete preserves all other fields (name, file, etc).
    """
    original_name = public_material.name
    original_file = public_material.file.name
    
    public_material.delete()
    public_material.refresh_from_db()
    
    assert public_material.name == original_name
    assert public_material.file.name == original_file


# ============================================================================
# RESTORATION - Undo soft-delete
# ============================================================================

@pytest.mark.django_db
def test_restore_method_clears_deleted_at(soft_deleted_material):
    """
    .restore() clears deleted_at, making material visible again.
    """
    assert soft_deleted_material.deleted_at is not None
    
    soft_deleted_material.restore()
    
    # deleted_at should be cleared
    assert soft_deleted_material.deleted_at is None
    
    # Should now be in .alive() results
    assert soft_deleted_material in Material.objects.alive()


@pytest.mark.django_db
def test_restored_material_appears_in_list(api_client_admin, soft_deleted_material):
    """
    After restoration, material should appear in list() response.
    """
    # Restore
    soft_deleted_material.restore()
    
    response = api_client_admin.get('/api/v1/materials/')
    assert response.status_code == status.HTTP_200_OK
    
    ids = [m['id'] for m in response.data['results']]
    assert str(soft_deleted_material.id) in ids


@pytest.mark.django_db
def test_restored_material_retrievable_by_id(api_client_admin, soft_deleted_material):
    """
    After restoration, material should be retrievable by ID.
    """
    # Restore
    soft_deleted_material.restore()
    
    response = api_client_admin.get(f'/api/v1/materials/{soft_deleted_material.id}/')
    assert response.status_code == status.HTTP_200_OK


# ============================================================================
# QUERYSET CHAINING - Filter before/after soft-delete check
# ============================================================================

@pytest.mark.django_db
def test_filter_chains_with_alive(public_material, soft_deleted_material):
    """
    Filtering should work with .alive() in the chain.
    """
    # Create both public and private materials
    public_material.is_public = True
    public_material.save()
    
    # Filter for public alive materials
    public_alive = Material.objects.alive().filter(is_public=True)
    
    # Should include public_material, not soft_deleted_material
    assert public_material in public_alive
    assert soft_deleted_material not in public_alive


@pytest.mark.django_db
def test_filter_on_deleted_at_directly(soft_deleted_material, public_material):
    """
    Can filter on deleted_at field directly.
    """
    # Filter for deleted
    deleted = Material.all_objects.filter(deleted_at__isnull=False)
    assert soft_deleted_material in deleted
    assert public_material not in deleted
    
    # Filter for not deleted
    not_deleted = Material.all_objects.filter(deleted_at__isnull=True)
    assert soft_deleted_material not in not_deleted
    assert public_material in not_deleted


# ============================================================================
# EDGE CASES - Multiple deletes, restore, etc
# ============================================================================

@pytest.mark.django_db
def test_soft_delete_then_restore_then_delete_again(public_material):
    """
    Soft delete → restore → soft delete again should work.
    """
    # First soft delete
    public_material.delete()
    assert public_material.deleted_at is not None
    first_deleted_at = public_material.deleted_at
    
    # Restore
    public_material.restore()
    assert public_material.deleted_at is None
    
    # Delete again
    public_material.delete()
    assert public_material.deleted_at is not None
    # Second deleted_at might be different timestamp
    assert public_material.deleted_at >= first_deleted_at


@pytest.mark.django_db
def test_hard_delete_of_soft_deleted_material(soft_deleted_material, mock_storage):
    """
    Can hard_delete a soft-deleted material.
    """
    file_name = soft_deleted_material.file.name
    material_id = soft_deleted_material.id
    
    with patch("apps.materials.signals.transaction.on_commit") as on_commit, \
        patch.object(soft_deleted_material.file, "delete") as delete_mock:
        on_commit.side_effect = lambda callback: callback()

        # Hard delete the soft-deleted material
        soft_deleted_material.hard_delete()
        delete_mock.assert_called_once_with(save=False)
    
    # Material completely gone
    assert not Material.objects.filter(id=material_id).exists()
    assert not Material.all_objects.filter(id=material_id).exists()
    


# ============================================================================
# BATCH OPERATIONS - Delete multiple, then restore
# ============================================================================

@pytest.mark.django_db
def test_batch_delete_via_queryset(public_material, private_material_for_group):
    """
    Batch delete via queryset.delete() soft-deletes all.
    """
    ids = [public_material.id, private_material_for_group.id]
    
    Material.objects.filter(id__in=ids).delete()
    
    # Both should be soft-deleted
    for material_id in ids:
        assert Material.objects.filter(id=material_id).count() == 0
        assert Material.all_objects.filter(id=material_id).count() == 1
        assert Material.all_objects.get(id=material_id).deleted_at is not None


@pytest.mark.django_db
def test_batch_restore_via_bulk_update():
    """
    Batch restore multiple materials.
    """
    # Create 3 soft-deleted materials
    materials = [
        Material.objects.create(
            name=f'Material {i}',
            file=None,
            file_type=Material.FileType.OTHER,
        )
        for i in range(3)
    ]
    
    # Soft delete all
    for m in materials:
        m.delete()
    
    # Restore all via bulk update
    Material.all_objects.filter(deleted_at__isnull=False).update(deleted_at=None)
    
    # All should be restored
    for m in materials:
        m.refresh_from_db()
        assert m.deleted_at is None


# ============================================================================
# PERMISSIONS WITH SOFT-DELETE
# ============================================================================

@pytest.mark.django_db
def test_cannot_edit_soft_deleted_material(api_client_admin, soft_deleted_material):
    """
    Attempting to PATCH soft-deleted material should return 404.
    """
    response = api_client_admin.patch(
        f'/api/v1/materials/{soft_deleted_material.id}/',
        {'name': 'New Name'}
    )
    assert response.status_code == status.HTTP_404_NOT_FOUND


@pytest.mark.django_db
def test_cannot_delete_soft_deleted_material_via_api(api_client_admin, soft_deleted_material):
    """
    Attempting to DELETE soft-deleted material should return 404.
    """
    response = api_client_admin.delete(f'/api/v1/materials/{soft_deleted_material.id}/')
    assert response.status_code == status.HTTP_404_NOT_FOUND


# ============================================================================
# VIEW-LEVEL FILTERING - get_queryset applies .alive()
# ============================================================================

@pytest.mark.django_db
def test_get_queryset_filters_soft_deleted(api_client_admin):
    """
    MaterialViewSet.get_queryset() applies .alive() filter.
    Soft-deleted materials are excluded at queryset level.
    """
    # This is more of an integration test
    # We create a soft-deleted material and verify it doesn't appear
    from django.core.files.uploadedfile import SimpleUploadedFile
    
    material = Material.objects.create(
        name='To Be Deleted',
        file=SimpleUploadedFile('test.pdf', b'%PDF'),
        file_type=Material.FileType.PDF,
        is_public=True,
    )
    
    # Soft delete
    material.delete()
    
    # List should not include it
    response = api_client_admin.get('/api/v1/materials/')
    ids = [m['id'] for m in response.data['results']]
    assert str(material.id) not in ids
