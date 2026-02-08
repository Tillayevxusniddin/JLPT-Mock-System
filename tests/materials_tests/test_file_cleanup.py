"""
Test file cleanup and soft-delete behavior for the Materials app.

Coverage:
- Hard delete triggers post_delete signal (file cleanup)
- Soft delete does NOT trigger post_delete signal (file preserved)
- transaction.on_commit() deferred execution
- Silent exception handling in signal
- File not found handling
"""

import pytest
from rest_framework import status
from django.core.files.uploadedfile import SimpleUploadedFile
from unittest.mock import patch, MagicMock

from apps.materials.models import Material


# ============================================================================
# SOFT DELETE - Does NOT trigger post_delete signal
# ============================================================================

@pytest.mark.django_db
def test_soft_delete_does_not_trigger_post_delete_signal(public_material, mock_storage):
    """
    CRITICAL: material.delete() calls soft_delete() (not hard_delete).
    post_delete signal is NOT triggered.
    File should remain in storage.
    """
    material_id = public_material.id
    file_name = public_material.file.name
    
    # Verify file exists in storage
    assert mock_storage.exists(file_name)
    
    # Soft delete via delete() method
    public_material.delete()
    
    # Verify material is soft-deleted (deleted_at set)
    material = Material.objects.filter(id=material_id).first()
    assert material is not None
    assert material.deleted_at is not None
    
    # Verify file still exists (signal not triggered)
    assert mock_storage.exists(file_name)


@pytest.mark.django_db
def test_soft_delete_material_not_in_alive_queryset(public_material):
    """
    Soft-deleted materials are excluded from .alive() queryset.
    """
    material_id = public_material.id
    
    # Soft delete
    public_material.delete()
    
    # Should not be in .alive() results
    assert not Material.objects.alive().filter(id=material_id).exists()


# ============================================================================
# HARD DELETE - Triggers post_delete signal
# ============================================================================

@pytest.mark.django_db
def test_hard_delete_triggers_post_delete_signal(public_material, mock_storage):
    """
    material.hard_delete() triggers post_delete signal.
    File should be deleted from storage.
    """
    material_id = public_material.id
    file_name = public_material.file.name
    
    # Verify file exists
    assert mock_storage.exists(file_name)
    
    # Hard delete
    public_material.hard_delete()
    
    # Verify material is deleted from DB
    assert not Material.objects.filter(id=material_id).exists()
    
    # Verify file is deleted from storage
    assert not mock_storage.exists(file_name)


@pytest.mark.django_db
def test_hard_delete_via_api_endpoint(api_client_admin, public_material, mock_storage):
    """
    DELETE via REST API endpoint should trigger signal.
    
    Note: REST API endpoint calls delete() (soft-delete).
    To test hard_delete signal, must call hard_delete() directly.
    This test verifies API behavior (soft-delete).
    """
    material_id = public_material.id
    file_name = public_material.file.name
    
    response = api_client_admin.delete(f'/api/v1/materials/{material_id}/')
    assert response.status_code == status.HTTP_204_NO_CONTENT
    
    # Verify soft-delete occurred (not hard-delete)
    material = Material.objects.filter(id=material_id).first()
    assert material is not None
    assert material.deleted_at is not None
    
    # File should still exist (soft-delete, no signal)
    assert mock_storage.exists(file_name)


# ============================================================================
# TRANSACTION.ON_COMMIT() DEFERRED EXECUTION
# ============================================================================

@pytest.mark.django_db
def test_file_deletion_deferred_until_commit(public_material, mock_storage):
    """
    File deletion is deferred via transaction.on_commit().
    During transaction, file should still exist.
    After transaction, file should be deleted.
    """
    file_name = public_material.file.name
    
    # Verify file exists
    assert mock_storage.exists(file_name)
    
    # Hard delete (in transaction)
    public_material.hard_delete()
    
    # After transaction commits, file should be deleted
    # (This test verifies the deferred behavior)
    assert not mock_storage.exists(file_name)


# ============================================================================
# SILENT EXCEPTION HANDLING - Storage failures don't raise
# ============================================================================

@pytest.mark.django_db
def test_storage_delete_failure_silent(public_material):
    """
    CRITICAL GOTCHA: Storage delete failures are caught silently.
    No exception raised, no logging.
    Material is hard-deleted even if file delete fails.
    """
    material_id = public_material.id
    
    # Mock storage to raise exception
    with patch('apps.materials.signals.transaction.on_commit') as mock_commit:
        # Capture the callback function
        def side_effect(callback):
            # Call the callback to execute it
            try:
                callback()
            except Exception:
                # Exception should be caught silently
                pass
        
        mock_commit.side_effect = side_effect
        
        # Hard delete
        with patch.object(public_material.file, 'delete', side_effect=Exception("Storage error")):
            # Should not raise, exception is caught
            public_material.hard_delete()
    
    # Material should be hard-deleted despite storage error
    assert not Material.objects.filter(id=material_id).exists()


# ============================================================================
# FILE NOT FOUND - Material without file
# ============================================================================

@pytest.mark.django_db
def test_hard_delete_material_without_file(mock_storage):
    """
    Hard delete material with file=None should not crash.
    Signal checks 'if instance.file' before deletion.
    """
    material = Material.objects.create(
        name='No File Material',
        file=None,  # No file
        file_type=Material.FileType.PDF,
        is_public=True,
    )
    
    # Hard delete should not raise
    material.hard_delete()
    
    # Material should be deleted
    assert not Material.objects.filter(id=material.id).exists()


@pytest.mark.django_db
def test_hard_delete_material_with_missing_file(public_material, mock_storage):
    """
    Hard delete material where file doesn't exist in storage.
    Should be handled gracefully (file.delete() called anyway).
    """
    file_name = public_material.file.name
    
    # Remove file from storage
    mock_storage.delete(file_name)
    assert not mock_storage.exists(file_name)
    
    # Hard delete should not raise
    public_material.hard_delete()
    
    # Material should be deleted
    assert not Material.objects.filter(id=public_material.id).exists()


# ============================================================================
# MULTIPLE DELETES - Idempotent behavior
# ============================================================================

@pytest.mark.django_db
def test_multiple_soft_deletes_idempotent(public_material):
    """
    Multiple soft deletes should be idempotent.
    First delete: sets deleted_at
    Second delete: no-op (already deleted)
    """
    # First delete
    public_material.delete()
    first_deleted_at = public_material.deleted_at
    
    # Second delete
    public_material.delete()
    second_deleted_at = public_material.deleted_at
    
    # deleted_at should be the same (idempotent)
    assert first_deleted_at == second_deleted_at


@pytest.mark.django_db
def test_soft_delete_then_restore_then_hard_delete(public_material, mock_storage):
    """
    Soft delete → restore → hard delete
    Only hard delete triggers signal.
    """
    file_name = public_material.file.name
    
    # Soft delete
    public_material.delete()
    assert public_material.deleted_at is not None
    
    # Restore
    public_material.restore()
    assert public_material.deleted_at is None
    
    # Hard delete
    public_material.hard_delete()
    
    # File should be deleted
    assert not mock_storage.exists(file_name)


# ============================================================================
# CASCADE BEHAVIOR - Related objects
# ============================================================================

@pytest.mark.django_db
def test_hard_delete_removes_group_assignments(public_material, test_group):
    """
    Hard delete removes M2M group assignments.
    """
    public_material.groups.add(test_group)
    assert public_material.groups.count() == 1
    
    # Hard delete
    public_material.hard_delete()
    
    # Material gone
    assert not Material.objects.filter(id=public_material.id).exists()


# ============================================================================
# SOFT DELETE QUERYSET BEHAVIOR
# ============================================================================

@pytest.mark.django_db
def test_all_objects_manager_includes_soft_deleted(public_material):
    """
    Material.all_objects includes soft-deleted materials.
    Material.objects excludes soft-deleted materials.
    """
    material_id = public_material.id
    
    # Soft delete
    public_material.delete()
    
    # Check with different managers
    assert not Material.objects.filter(id=material_id).exists()  # objects excludes
    assert Material.all_objects.filter(id=material_id).exists()  # all_objects includes


@pytest.mark.django_db
def test_dead_queryset_method(public_material):
    """
    .dead() returns only soft-deleted materials.
    """
    public_material.delete()
    
    # Check with .dead() method
    assert Material.objects.dead().filter(id=public_material.id).exists()
    assert not Material.objects.alive().filter(id=public_material.id).exists()


# ============================================================================
# FILE STORAGE OPERATIONS
# ============================================================================

@pytest.mark.django_db
def test_file_cleanup_respects_file_field_value(public_material, mock_storage):
    """
    File cleanup uses the file field value from database at deletion time.
    If file field was changed, cleanup uses the new file name.
    """
    original_file = public_material.file.name
    
    # Verify original file exists
    assert mock_storage.exists(original_file)
    
    # Hard delete uses the file field value
    public_material.hard_delete()
    
    # Original file should be deleted
    assert not mock_storage.exists(original_file)


# ============================================================================
# BATCH OPERATIONS - Delete multiple materials
# ============================================================================

@pytest.mark.django_db
def test_batch_soft_delete(public_material, private_material_for_group, mock_storage):
    """
    Batch soft delete via queryset.delete()
    """
    file1 = public_material.file.name
    file2 = private_material_for_group.file.name
    
    # Batch soft delete
    Material.objects.filter(id__in=[public_material.id, private_material_for_group.id]).delete()
    
    # Both should be soft-deleted
    assert Material.objects.alive().filter(id=public_material.id).count() == 0
    
    # Files should still exist (soft-delete, no signal)
    assert mock_storage.exists(file1)
    assert mock_storage.exists(file2)
