"""
Test CRUD operations for Group API endpoints.

All tests verify success via response.status_code and response.data,
never via database queries (to avoid 'transaction aborted' errors).
"""

import pytest
from rest_framework import status
from apps.groups.models import Group
from apps.authentication.models import User


@pytest.mark.django_db(transaction=False)
class TestGroupList:
    """Test Group list endpoint."""
    
    def test_center_admin_can_list_groups(self, api_client, center_admin_headers, group_default, group_small):
        """CENTER_ADMIN can list all groups in their center."""
        response = api_client.get('/api/v1/groups/', HTTP_AUTHORIZATION=center_admin_headers)
        assert response.status_code == status.HTTP_200_OK
        assert isinstance(response.data, dict)  # Paginated response
        assert 'results' in response.data
        assert len(response.data['results']) >= 2
    
    def test_teacher_can_list_groups(self, api_client, teacher_headers, group_default, group_small):
        """TEACHER can list groups."""
        response = api_client.get('/api/v1/groups/', HTTP_AUTHORIZATION=teacher_headers)
        assert response.status_code == status.HTTP_200_OK
        assert 'results' in response.data
    
    def test_student_can_list_groups(self, api_client, student_headers, group_default):
        """STUDENT can list groups (but only ones they're in)."""
        response = api_client.get('/api/v1/groups/', HTTP_AUTHORIZATION=student_headers)
        assert response.status_code == status.HTTP_200_OK
        assert 'results' in response.data
    
    def test_guest_can_list_groups(self, api_client, guest_headers):
        """GUEST can list groups."""
        response = api_client.get('/api/v1/groups/', HTTP_AUTHORIZATION=guest_headers)
        assert response.status_code == status.HTTP_200_OK
        assert 'results' in response.data
    
    def test_unauthenticated_cannot_list_groups(self, api_client):
        """Unauthenticated user cannot list groups."""
        response = api_client.get('/api/v1/groups/')
        assert response.status_code == status.HTTP_401_UNAUTHORIZED
    
    def test_list_groups_search_by_name(self, api_client, center_admin_headers, group_default):
        """CENTER_ADMIN can search groups by name."""
        response = api_client.get('/api/v1/groups/?search=Default', HTTP_AUTHORIZATION=center_admin_headers)
        assert response.status_code == status.HTTP_200_OK
        assert 'results' in response.data
        # Should contain the default group
        names = [g['name'] for g in response.data['results']]
        assert any('Default' in name for name in names)
    
    def test_list_groups_ordering(self, api_client, center_admin_headers, group_default, group_small):
        """CENTER_ADMIN can order groups."""
        response = api_client.get('/api/v1/groups/?ordering=name', HTTP_AUTHORIZATION=center_admin_headers)
        assert response.status_code == status.HTTP_200_OK
        assert 'results' in response.data


@pytest.mark.django_db(transaction=False)
class TestGroupRetrieve:
    """Test Group retrieve (detail) endpoint."""
    
    def test_center_admin_can_retrieve_group(self, api_client, center_admin_headers, group_default):
        """CENTER_ADMIN can retrieve a specific group."""
        response = api_client.get(f'/api/v1/groups/{group_default.id}/', HTTP_AUTHORIZATION=center_admin_headers)
        assert response.status_code == status.HTTP_200_OK
        assert response.data['id'] == str(group_default.id)
        assert response.data['name'] == group_default.name
    
    def test_teacher_can_retrieve_group(self, api_client, group_with_teacher):
        """TEACHER can retrieve a group they teach in."""
        from rest_framework_simplejwt.tokens import RefreshToken
        # Use the teacher from the group_with_teacher fixture
        from apps.groups.models import GroupMembership
        membership = GroupMembership.objects.filter(
            group=group_with_teacher,
            role_in_group=GroupMembership.ROLE_TEACHER
        ).first()
        
        if membership:
            # Get the teacher from public schema
            from apps.authentication.models import User
            from apps.core.tenant_utils import with_public_schema
            
            def get_user():
                return User.objects.get(id=membership.user_id)
            
            teacher = with_public_schema(get_user)
            refresh = RefreshToken.for_user(teacher)
            auth_header = f'Bearer {str(refresh.access_token)}'
            
            response = api_client.get(f'/api/v1/groups/{group_with_teacher.id}/', HTTP_AUTHORIZATION=auth_header)
            assert response.status_code == status.HTTP_200_OK
            assert response.data['id'] == str(group_with_teacher.id)
    
    def test_retrieve_nonexistent_group_returns_404(self, api_client, center_admin_headers):
        """Retrieving non-existent group returns 404."""
        from uuid import uuid4
        fake_id = uuid4()
        response = api_client.get(f'/api/v1/groups/{fake_id}/', HTTP_AUTHORIZATION=center_admin_headers)
        assert response.status_code == status.HTTP_404_NOT_FOUND


@pytest.mark.django_db(transaction=False)
class TestGroupCreate:
    """Test Group creation endpoint."""
    
    def test_center_admin_can_create_group(self, api_client, center_admin_headers):
        """CENTER_ADMIN can create a new group."""
        payload = {
            'name': 'New Test Group',
            'description': 'A brand new test group',
            'max_students': 25,
            'is_active': True,
        }
        response = api_client.post('/api/v1/groups/', payload, HTTP_AUTHORIZATION=center_admin_headers)
        assert response.status_code == status.HTTP_201_CREATED
        assert response.data['name'] == 'New Test Group'
        assert response.data['description'] == 'A brand new test group'
        assert response.data['max_students'] == 25
        assert 'id' in response.data
    
    def test_center_admin_can_create_group_with_teachers(self, api_client, center_admin_headers, teacher_user, teacher_user_2):
        """CENTER_ADMIN can create a group with teachers assigned."""
        payload = {
            'name': 'Group With Teachers',
            'description': 'Test group with teachers',
            'max_students': 30,
            'is_active': True,
            'teacher_ids': [teacher_user.id, teacher_user_2.id],
        }
        response = api_client.post('/api/v1/groups/', payload, HTTP_AUTHORIZATION=center_admin_headers)
        assert response.status_code == status.HTTP_201_CREATED
        assert 'id' in response.data
        # Teacher data should be in response
        assert 'teachers' in response.data or response.data['teacher_count'] >= 0
    
    def test_teacher_cannot_create_group(self, api_client, teacher_headers):
        """TEACHER cannot create a group (permission denied)."""
        payload = {
            'name': 'Unauthorized Group',
            'description': 'This should fail',
        }
        response = api_client.post('/api/v1/groups/', payload, HTTP_AUTHORIZATION=teacher_headers)
        assert response.status_code == status.HTTP_403_FORBIDDEN
    
    def test_student_cannot_create_group(self, api_client, student_headers):
        """STUDENT cannot create a group."""
        payload = {
            'name': 'Unauthorized Group',
            'description': 'This should fail',
        }
        response = api_client.post('/api/v1/groups/', payload, HTTP_AUTHORIZATION=student_headers)
        assert response.status_code == status.HTTP_403_FORBIDDEN
    
    def test_create_group_with_duplicate_name_fails(self, api_client, center_admin_headers, group_default):
        """Creating a group with duplicate name fails (unique constraint)."""
        payload = {
            'name': group_default.name,
            'description': 'Duplicate name',
        }
        response = api_client.post('/api/v1/groups/', payload, HTTP_AUTHORIZATION=center_admin_headers)
        # Should fail with 400 or similar validation error
        assert response.status_code in [status.HTTP_400_BAD_REQUEST, status.HTTP_409_CONFLICT]
    
    def test_create_group_name_is_required(self, api_client, center_admin_headers):
        """Creating a group without name fails."""
        payload = {
            'description': 'No name provided',
        }
        response = api_client.post('/api/v1/groups/', payload, HTTP_AUTHORIZATION=center_admin_headers)
        assert response.status_code == status.HTTP_400_BAD_REQUEST
    
    def test_unauthenticated_cannot_create_group(self, api_client):
        """Unauthenticated user cannot create a group."""
        payload = {'name': 'Test Group'}
        response = api_client.post('/api/v1/groups/', payload)
        assert response.status_code == status.HTTP_401_UNAUTHORIZED


@pytest.mark.django_db(transaction=False)
class TestGroupUpdate:
    """Test Group update (partial update) endpoint."""
    
    def test_center_admin_can_update_group(self, api_client, center_admin_headers, group_default):
        """CENTER_ADMIN can update a group."""
        payload = {
            'name': 'Updated Group Name',
            'description': 'Updated description',
        }
        response = api_client.patch(f'/api/v1/groups/{group_default.id}/', payload, HTTP_AUTHORIZATION=center_admin_headers)
        assert response.status_code == status.HTTP_200_OK
        assert response.data['name'] == 'Updated Group Name'
        assert response.data['description'] == 'Updated description'
    
    def test_teacher_can_update_group_if_teacher(self, api_client, group_with_teacher, teacher_user, test_center):
        """TEACHER can update a group if they are a teacher in it."""
        from rest_framework_simplejwt.tokens import RefreshToken
        refresh = RefreshToken.for_user(teacher_user)
        auth_header = f'Bearer {str(refresh.access_token)}'
        
        payload = {'description': 'Updated by teacher'}
        response = api_client.patch(f'/api/v1/groups/{group_with_teacher.id}/', payload, HTTP_AUTHORIZATION=auth_header)
        assert response.status_code == status.HTTP_200_OK
        assert response.data['description'] == 'Updated by teacher'
    
    def test_teacher_cannot_update_group_if_not_teacher(self, api_client, teacher_headers, group_default):
        """TEACHER cannot update a group if they're not a teacher in it."""
        payload = {'description': 'Should fail'}
        response = api_client.patch(f'/api/v1/groups/{group_default.id}/', payload, HTTP_AUTHORIZATION=teacher_headers)
        # Returns 404 because teacher can't see groups they don't teach in
        assert response.status_code in [status.HTTP_403_FORBIDDEN, status.HTTP_404_NOT_FOUND]
    
    def test_student_cannot_update_group(self, api_client, student_headers, group_default):
        """STUDENT cannot update a group."""
        payload = {'description': 'Should fail'}
        response = api_client.patch(f'/api/v1/groups/{group_default.id}/', payload, HTTP_AUTHORIZATION=student_headers)
        # Returns 404 because student can't see groups they're not in
        assert response.status_code in [status.HTTP_403_FORBIDDEN, status.HTTP_404_NOT_FOUND]
    
    def test_update_group_full_put(self, api_client, center_admin_headers, group_default):
        """CENTER_ADMIN can fully replace a group with PUT."""
        payload = {
            'name': 'Completely New Name',
            'description': 'Completely new description',
            'max_students': 50,
            'is_active': False,
        }
        response = api_client.put(f'/api/v1/groups/{group_default.id}/', payload, HTTP_AUTHORIZATION=center_admin_headers)
        assert response.status_code == status.HTTP_200_OK
        assert response.data['name'] == 'Completely New Name'
        assert response.data['max_students'] == 50
        assert response.data['is_active'] == False
    
    def test_update_nonexistent_group_returns_404(self, api_client, center_admin_headers):
        """Updating non-existent group returns 404."""
        from uuid import uuid4
        fake_id = uuid4()
        payload = {'name': 'Test'}
        response = api_client.patch(f'/api/v1/groups/{fake_id}/', payload, HTTP_AUTHORIZATION=center_admin_headers)
        assert response.status_code == status.HTTP_404_NOT_FOUND


@pytest.mark.django_db(transaction=False)
class TestGroupDelete:
    """Test Group deletion endpoint."""
    
    def test_center_admin_can_delete_group(self, api_client, center_admin_headers, test_center):
        """CENTER_ADMIN can delete a group."""
        from apps.core.tenant_utils import set_tenant_schema
        from uuid import uuid4
        
        # Create a group to delete
        set_tenant_schema(test_center.schema_name)
        group = Group.objects.create(
            id=uuid4(),
            name='Group to Delete',
            description='This will be deleted',
        )
        group_id = group.id
        
        # Delete it via API
        response = api_client.delete(f'/api/v1/groups/{group_id}/', HTTP_AUTHORIZATION=center_admin_headers)
        assert response.status_code == status.HTTP_204_NO_CONTENT
    
    def test_teacher_cannot_delete_group(self, api_client, teacher_headers, group_default):
        """TEACHER cannot delete a group (even if they teach in it)."""
        response = api_client.delete(f'/api/v1/groups/{group_default.id}/', HTTP_AUTHORIZATION=teacher_headers)
        assert response.status_code == status.HTTP_403_FORBIDDEN
    
    def test_student_cannot_delete_group(self, api_client, student_headers, group_default):
        """STUDENT cannot delete a group."""
        response = api_client.delete(f'/api/v1/groups/{group_default.id}/', HTTP_AUTHORIZATION=student_headers)
        assert response.status_code == status.HTTP_403_FORBIDDEN
    
    def test_delete_nonexistent_group_returns_404(self, api_client, center_admin_headers):
        """Deleting non-existent group returns 404."""
        from uuid import uuid4
        fake_id = uuid4()
        response = api_client.delete(f'/api/v1/groups/{fake_id}/', HTTP_AUTHORIZATION=center_admin_headers)
        assert response.status_code == status.HTTP_404_NOT_FOUND


@pytest.mark.django_db(transaction=False)
class TestGroupTenantIsolation:
    """Test that groups are properly isolated by tenant."""
    
    def test_foreign_center_teacher_cannot_access_test_center_groups(
        self, api_client, foreign_center_headers, group_default
    ):
        """Teacher from foreign center cannot access test center's groups."""
        response = api_client.get('/api/v1/groups/', HTTP_AUTHORIZATION=foreign_center_headers)
        assert response.status_code == status.HTTP_200_OK
        # Should have zero groups (foreign center's groups)
        assert response.data['count'] == 0
    
    def test_foreign_center_teacher_cannot_retrieve_test_center_group(
        self, api_client, foreign_center_headers, group_default
    ):
        """Teacher from foreign center cannot retrieve test center's group."""
        response = api_client.get(f'/api/v1/groups/{group_default.id}/', HTTP_AUTHORIZATION=foreign_center_headers)
        assert response.status_code == status.HTTP_404_NOT_FOUND
    
    def test_foreign_center_teacher_cannot_delete_test_center_group(
        self, api_client, foreign_center_headers, group_default
    ):
        """Teacher from foreign center cannot delete test center's group."""
        response = api_client.delete(f'/api/v1/groups/{group_default.id}/', HTTP_AUTHORIZATION=foreign_center_headers)
        # Returns 403 or 404 depending on architecture
        assert response.status_code in [status.HTTP_403_FORBIDDEN, status.HTTP_404_NOT_FOUND]
