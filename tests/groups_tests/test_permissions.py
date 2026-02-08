"""
Test Group API permission checks.

Verifies that role-based access control (RBAC) works correctly for different user types
and that cross-tenant access is properly blocked.
"""

import pytest
from rest_framework import status
from apps.authentication.models import User


@pytest.mark.django_db(transaction=False)
class TestGroupPermissions:
    """Test permission checks for Group operations."""
    
    def test_center_admin_has_full_access(self, api_client, center_admin_headers, group_default):
        """CENTER_ADMIN has full access to group operations."""
        # List
        response = api_client.get('/api/v1/groups/', HTTP_AUTHORIZATION=center_admin_headers)
        assert response.status_code == status.HTTP_200_OK
        
        # Retrieve
        response = api_client.get(f'/api/v1/groups/{group_default.id}/', HTTP_AUTHORIZATION=center_admin_headers)
        assert response.status_code == status.HTTP_200_OK
        
        # Create
        payload = {'name': 'Admin Created Group'}
        response = api_client.post('/api/v1/groups/', payload, HTTP_AUTHORIZATION=center_admin_headers)
        assert response.status_code == status.HTTP_201_CREATED
        
        # Update
        response = api_client.patch(
            f'/api/v1/groups/{group_default.id}/',
            {'description': 'Updated by admin'},
            HTTP_AUTHORIZATION=center_admin_headers
        )
        assert response.status_code == status.HTTP_200_OK
    
    def test_teacher_has_limited_access(self, api_client, teacher_headers, group_with_teacher):
        """TEACHER has limited access - can read but not create/delete."""
        # List
        response = api_client.get('/api/v1/groups/', HTTP_AUTHORIZATION=teacher_headers)
        assert response.status_code == status.HTTP_200_OK
        
        # Retrieve - can get group they teach in
        response = api_client.get(f'/api/v1/groups/{group_with_teacher.id}/', HTTP_AUTHORIZATION=teacher_headers)
        assert response.status_code == status.HTTP_200_OK
        
        # Cannot create
        payload = {'name': 'Teacher Created Group'}
        response = api_client.post('/api/v1/groups/', payload, HTTP_AUTHORIZATION=teacher_headers)
        assert response.status_code == status.HTTP_403_FORBIDDEN
        
        # Cannot delete
        response = api_client.delete(f'/api/v1/groups/{group_with_teacher.id}/', HTTP_AUTHORIZATION=teacher_headers)
        assert response.status_code == status.HTTP_403_FORBIDDEN
    
    def test_teacher_can_update_own_group(self, api_client, group_with_teacher, teacher_user):
        """TEACHER can update a group they teach in."""
        from rest_framework_simplejwt.tokens import RefreshToken
        refresh = RefreshToken.for_user(teacher_user)
        auth_header = f'Bearer {str(refresh.access_token)}'
        
        payload = {'description': 'Updated by teacher'}
        response = api_client.patch(
            f'/api/v1/groups/{group_with_teacher.id}/',
            payload,
            HTTP_AUTHORIZATION=auth_header
        )
        assert response.status_code == status.HTTP_200_OK
    
    def test_teacher_cannot_update_other_group(self, api_client, teacher_headers, group_default):
        """TEACHER cannot update a group they don't teach in."""
        payload = {'description': 'Should fail'}
        response = api_client.patch(
            f'/api/v1/groups/{group_default.id}/',
            payload,
            HTTP_AUTHORIZATION=teacher_headers
        )
        # Returns 404 because teacher can't see groups they don't teach in
        assert response.status_code in [status.HTTP_403_FORBIDDEN, status.HTTP_404_NOT_FOUND]
    
    def test_student_can_only_read(self, api_client, student_headers, group_default):
        """STUDENT can only read groups."""
        # List
        response = api_client.get('/api/v1/groups/', HTTP_AUTHORIZATION=student_headers)
        assert response.status_code == status.HTTP_200_OK
        
        # Retrieve - student sees group but can't modify it
        # (Note: students only see groups they're in, so group_default might return 404 if they're not in it)
        response = api_client.get(f'/api/v1/groups/{group_default.id}/', HTTP_AUTHORIZATION=student_headers)
        # Accept both 200 and 404 depending on whether student is in the group
        assert response.status_code in [status.HTTP_200_OK, status.HTTP_404_NOT_FOUND]
        
        # Cannot create
        payload = {'name': 'Student Created Group'}
        response = api_client.post('/api/v1/groups/', payload, HTTP_AUTHORIZATION=student_headers)
        assert response.status_code == status.HTTP_403_FORBIDDEN
        
        # Cannot update
        response = api_client.patch(
            f'/api/v1/groups/{group_default.id}/',
            {'description': 'Should fail'},
            HTTP_AUTHORIZATION=student_headers
        )
        # Returns 404 or 403 depending on whether student can see the group
        assert response.status_code in [status.HTTP_403_FORBIDDEN, status.HTTP_404_NOT_FOUND]
        
        # Cannot delete
        response = api_client.delete(f'/api/v1/groups/{group_default.id}/', HTTP_AUTHORIZATION=student_headers)
        # Returns 404 or 403 depending on whether student can see the group
        assert response.status_code in [status.HTTP_403_FORBIDDEN, status.HTTP_404_NOT_FOUND]
    
    def test_guest_can_only_read(self, api_client, guest_headers, group_default):
        """GUEST can only read groups (same as student)."""
        # List
        response = api_client.get('/api/v1/groups/', HTTP_AUTHORIZATION=guest_headers)
        assert response.status_code == status.HTTP_200_OK
        
        # Retrieve
        response = api_client.get(f'/api/v1/groups/{group_default.id}/', HTTP_AUTHORIZATION=guest_headers)
        # Accept 200 or 404 depending on whether guest is in the group
        assert response.status_code in [status.HTTP_200_OK, status.HTTP_404_NOT_FOUND]
        
        # Cannot create
        payload = {'name': 'Guest Created Group'}
        response = api_client.post('/api/v1/groups/', payload, HTTP_AUTHORIZATION=guest_headers)
        assert response.status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.django_db(transaction=False)
class TestGroupCrossTenantisolation:
    """Test that groups are properly isolated across tenants."""
    
    def test_foreign_center_admin_cannot_access_test_center_groups(
        self, db, foreign_test_center, test_center, api_client, group_default
    ):
        """Admin from foreign center cannot access test center groups."""
        # Create a foreign center admin
        from apps.core.tenant_utils import set_public_schema
        from rest_framework_simplejwt.tokens import RefreshToken
        
        set_public_schema()
        foreign_admin = User.objects.create_user(
            email='foreign_admin@test.com',
            password='Pass123!',
            role=User.Role.CENTERADMIN,
            center=foreign_test_center,
            is_active=True,
            is_approved=True,
        )
        refresh = RefreshToken.for_user(foreign_admin)
        auth_header = f'Bearer {str(refresh.access_token)}'
        
        # Try to access test center's groups
        response = api_client.get('/api/v1/groups/', HTTP_AUTHORIZATION=auth_header)
        assert response.status_code == status.HTTP_200_OK
        # Should see zero groups (they're in foreign center's schema)
        assert response.data['count'] == 0
    
    def test_foreign_center_admin_cannot_retrieve_test_center_group(
        self, db, foreign_test_center, api_client, group_default
    ):
        """Admin from foreign center cannot retrieve test center's specific group."""
        from apps.core.tenant_utils import set_public_schema
        from rest_framework_simplejwt.tokens import RefreshToken
        
        set_public_schema()
        foreign_admin = User.objects.create_user(
            email='foreign_admin2@test.com',
            password='Pass123!',
            role=User.Role.CENTERADMIN,
            center=foreign_test_center,
            is_active=True,
            is_approved=True,
        )
        refresh = RefreshToken.for_user(foreign_admin)
        auth_header = f'Bearer {str(refresh.access_token)}'
        
        response = api_client.get(f'/api/v1/groups/{group_default.id}/', HTTP_AUTHORIZATION=auth_header)
        assert response.status_code == status.HTTP_404_NOT_FOUND
    
    def test_foreign_center_admin_cannot_modify_test_center_group(
        self, db, foreign_test_center, api_client, group_default
    ):
        """Admin from foreign center cannot modify test center's group."""
        from apps.core.tenant_utils import set_public_schema
        from rest_framework_simplejwt.tokens import RefreshToken
        
        set_public_schema()
        foreign_admin = User.objects.create_user(
            email='foreign_admin3@test.com',
            password='Pass123!',
            role=User.Role.CENTERADMIN,
            center=foreign_test_center,
            is_active=True,
            is_approved=True,
        )
        refresh = RefreshToken.for_user(foreign_admin)
        auth_header = f'Bearer {str(refresh.access_token)}'
        
        response = api_client.patch(
            f'/api/v1/groups/{group_default.id}/',
            {'description': 'Hack attempt'},
            HTTP_AUTHORIZATION=auth_header
        )
        assert response.status_code == status.HTTP_404_NOT_FOUND


@pytest.mark.django_db(transaction=False)
class TestMembershipPermissions:
    """Test permission checks for GroupMembership operations."""
    
    def test_center_admin_can_add_members(self, api_client, center_admin_headers, group_default, student_user):
        """CENTER_ADMIN can add members to groups."""
        from apps.groups.models import GroupMembership
        
        payload = {
            'group_id': str(group_default.id),
            'user_id': student_user.id,
            'role_in_group': GroupMembership.ROLE_STUDENT,
        }
        response = api_client.post('/api/v1/group-memberships/', payload, HTTP_AUTHORIZATION=center_admin_headers)
        assert response.status_code == status.HTTP_201_CREATED
    
    def test_teacher_cannot_add_members(self, api_client, teacher_headers, group_default, student_user):
        """TEACHER cannot add members to groups."""
        from apps.groups.models import GroupMembership
        
        payload = {
            'group_id': str(group_default.id),
            'user_id': student_user.id,
            'role_in_group': GroupMembership.ROLE_STUDENT,
        }
        response = api_client.post('/api/v1/group-memberships/', payload, HTTP_AUTHORIZATION=teacher_headers)
        assert response.status_code == status.HTTP_403_FORBIDDEN
    
    def test_student_cannot_manage_memberships(self, api_client, student_headers, group_default, student_user_2):
        """STUDENT cannot add/remove members."""
        from apps.groups.models import GroupMembership
        
        payload = {
            'group_id': str(group_default.id),
            'user_id': student_user_2.id,
            'role_in_group': GroupMembership.ROLE_STUDENT,
        }
        response = api_client.post('/api/v1/group-memberships/', payload, HTTP_AUTHORIZATION=student_headers)
        assert response.status_code == status.HTTP_403_FORBIDDEN
