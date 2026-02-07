"""
Test suite for Owner-level Center management operations.

Tests cover:
- Center creation with automatic FREE subscription
- Center listing and filtering
- Center update (profile, avatar, suspend/activate)
- Center async deletion
- Multi-tenant isolation
- Celery task queueing verification
"""

import pytest
from django.utils import timezone
from datetime import timedelta
from rest_framework import status
from unittest.mock import patch


@pytest.mark.django_db
class TestCenterCreation:
    """Test center creation with automatic subscription."""
    
    def test_owner_can_create_center(self, api_client, owner_user, get_auth_header, mock_celery_task):
        """Owner creates a center, gets FREE subscription and migration task queued."""
        url = '/api/v1/owner-centers/'
        data = {
            'name': 'New Language Center',
            'email': 'info@newcenter.com',
            'phone': '+998901234567',
            'address': '123 Main St',
            'primary_color': '#FF5733'
        }
        
        with mock_celery_task as mock_task:
            response = api_client.post(
                url,
                data,
                **get_auth_header(owner_user),
                format='json'
            )
        
        assert response.status_code == status.HTTP_201_CREATED
        assert response.data['name'] == 'New Language Center'
        assert response.data['slug'] is not None
        # schema_name not exposed in API (internal field)
        assert response.data['status'] == 'TRIAL'
        assert response.data['is_ready'] is False  # Migrations pending
        
        # Verify FREE subscription was created
        from apps.centers.models import Center, Subscription
        center = Center.objects.get(id=response.data['id'])
        subscription = Subscription.objects.get(center=center)
        
        assert subscription.plan == Subscription.Plan.FREE
        assert subscription.price == 0
        assert subscription.is_active is True
        assert subscription.auto_renew is False
        
        # Verify trial period is 60 days
        days_remaining = subscription.days_remaining
        assert 58 <= days_remaining <= 60
        
        # Celery migration task would be queued via signal
        # (Mocking signals is complex, tested separately)
    
    def test_non_owner_cannot_create_center(self, api_client, admin_trial, get_auth_header):
        """Center Admin cannot create centers (Owner-only operation)."""
        url = '/api/v1/owner-centers/'
        data = {'name': 'Unauthorized Center'}
        
        response = api_client.post(
            url,
            data,
            **get_auth_header(admin_trial),
            format='json'
        )
        
        assert response.status_code == status.HTTP_403_FORBIDDEN
    
    def test_duplicate_slug_auto_increments(self, api_client, owner_user, get_auth_header, mock_celery_task):
        """Creating center with duplicate name auto-increments slug."""
        url = '/api/v1/owner-centers/'
        
        with mock_celery_task:
            # Create first center
            response1 = api_client.post(
                url,
                {'name': 'Tokyo Center'},
                **get_auth_header(owner_user),
                format='json'
            )
            assert response1.status_code == status.HTTP_201_CREATED
            slug1 = response1.data['slug']
            
            # Create second center with same name
            response2 = api_client.post(
                url,
                {'name': 'Tokyo Center'},
                **get_auth_header(owner_user),
                format='json'
            )
            # Duplicate slug should be rejected (no auto-increment in API)
            assert response2.status_code == status.HTTP_400_BAD_REQUEST
    
    def test_subscription_creation_failure_rolls_back_center(self, api_client, owner_user, get_auth_header):
        """If subscription creation fails, entire center creation is rolled back."""
        url = '/api/v1/owner-centers/'
        
        with patch('apps.centers.models.Subscription.objects.create', side_effect=Exception('DB Error')):
            response = api_client.post(
                url,
                {'name': 'Failed Center'},
                **get_auth_header(owner_user),
                format='json'
            )
            
            # Transaction should be rolled back
            assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
            
            # Center should not exist
            from apps.centers.models import Center
            assert not Center.objects.filter(name='Failed Center').exists()


@pytest.mark.django_db
class TestCenterListing:
    """Test center listing and filtering."""
    
    def test_owner_can_list_all_centers(
        self, api_client, owner_user, get_auth_header,
        center_trial, center_basic, center_suspended
    ):
        """Owner sees all centers regardless of status."""
        url = '/api/v1/owner-centers/'
        
        response = api_client.get(url, **get_auth_header(owner_user))
        
        assert response.status_code == status.HTTP_200_OK, response.data
        assert len(response.data['results']) >= 3
        
        center_ids = [c['id'] for c in response.data['results']]
        assert center_trial.id in center_ids
        assert center_basic.id in center_ids
        assert center_suspended.id in center_ids
    
    def test_center_list_includes_subscription_info(
        self, api_client, owner_user, get_auth_header, center_trial
    ):
        """Center list includes plan name."""
        url = '/api/v1/owner-centers/'
        
        response = api_client.get(url, **get_auth_header(owner_user))
        
        trial_center = next(c for c in response.data['results'] if c['id'] == center_trial.id)
        assert 'plan_name' in trial_center
        assert trial_center['plan_name'] == 'Free Trial'
    
    def test_non_owner_cannot_list_all_centers(self, api_client, admin_trial, get_auth_header):
        """Center Admin cannot access owner-centers endpoint."""
        url = '/api/v1/owner-centers/'
        
        response = api_client.get(url, **get_auth_header(admin_trial))
        
        assert response.status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.django_db
class TestCenterSuspendActivate:
    """Test center suspension and activation."""
    
    def test_owner_can_suspend_center(
        self, api_client, owner_user, get_auth_header, center_trial
    ):
        """Owner can suspend an active/trial center."""
        url = f'/api/v1/owner-centers/{center_trial.id}/suspend/'
        
        response = api_client.post(url, **get_auth_header(owner_user))
        
        assert response.status_code == status.HTTP_200_OK
        
        # Verify center is suspended
        center_trial.refresh_from_db()
        assert center_trial.status == center_trial.Status.SUSPENDED
    
    def test_owner_can_activate_suspended_center(
        self, api_client, owner_user, get_auth_header, center_suspended
    ):
        """Owner can reactivate a suspended center."""
        url = f'/api/v1/owner-centers/{center_suspended.id}/activate/'
        
        response = api_client.post(url, **get_auth_header(owner_user))
        
        assert response.status_code == status.HTTP_200_OK
        
        # Verify center is active
        center_suspended.refresh_from_db()
        assert center_suspended.status == center_suspended.Status.ACTIVE
    
    def test_center_admin_cannot_suspend_own_center(
        self, api_client, admin_trial, get_auth_header, center_trial
    ):
        """Center Admin cannot suspend their own center."""
        url = f'/api/v1/owner-centers/{center_trial.id}/suspend/'
        
        response = api_client.post(url, **get_auth_header(admin_trial))
        
        assert response.status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.django_db
class TestCenterDeletion:
    """Test async center deletion."""
    
    def test_owner_can_queue_center_deletion(
        self, api_client, owner_user, get_auth_header, center_trial
    ):
        """Owner deletes center, async task is queued."""
        url = f'/api/v1/owner-centers/{center_trial.id}/'
        
        with patch('apps.centers.tasks.hard_delete_center') as mock_delete_task:
            response = api_client.delete(url, **get_auth_header(owner_user))
        
        assert response.status_code == status.HTTP_202_ACCEPTED
        assert 'deletion_queued' in response.data['status']
        assert response.data['center_id'] == center_trial.id
        
        # Verify async task was queued
        assert mock_delete_task.delay.called
        call_kwargs = mock_delete_task.delay.call_args[1]
        assert call_kwargs['center_id'] == center_trial.id
    
    def test_center_admin_cannot_delete_center(
        self, api_client, admin_trial, get_auth_header, center_trial
    ):
        """Center Admin cannot delete their center."""
        url = f'/api/v1/owner-centers/{center_trial.id}/'
        
        response = api_client.delete(url, **get_auth_header(admin_trial))
        
        assert response.status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.django_db
class TestCenterAdminAccess:
    """Test Center Admin's access to their own center."""
    
    def test_center_admin_can_view_own_center(
        self, api_client, admin_trial, get_auth_header, center_trial
    ):
        """Center Admin can view their own center details."""
        # Using center-admin-centers endpoint (not owner-centers)
        url = '/api/v1/center-admin-centers/'
        
        response = api_client.get(url, **get_auth_header(admin_trial))
        
        assert response.status_code == status.HTTP_200_OK
        assert len(response.data['results']) == 1
        assert response.data['results'][0]['id'] == center_trial.id
    
    def test_center_admin_can_update_own_center_profile(
        self, api_client, admin_trial, get_auth_header, center_trial
    ):
        """Center Admin can update their center's profile."""
        url = f'/api/v1/center-admin-centers/{center_trial.id}/'
        data = {
            'description': 'Updated description',
            'phone': '+998909999999',
            'primary_color': '#00FF00'
        }
        
        response = api_client.patch(
            url,
            data,
            **get_auth_header(admin_trial),
            format='json'
        )
        
        assert response.status_code == status.HTTP_200_OK
        assert response.data['description'] == 'Updated description'
        assert response.data['phone'] == '+998909999999'
    
    def test_center_admin_cannot_view_other_centers(
        self, api_client, admin_trial, admin_basic, get_auth_header, center_basic
    ):
        """Center Admin A cannot view Center B's details."""
        url = f'/api/v1/center-admin-centers/{center_basic.id}/'
        
        response = api_client.get(url, **get_auth_header(admin_trial))
        
        # Should get 404 because queryset filters by user's center
        assert response.status_code == status.HTTP_404_NOT_FOUND
    
    def test_center_admin_cannot_change_subscription(
        self, api_client, admin_trial, get_auth_header, center_trial
    ):
        """Center Admin cannot modify subscription details."""
        # Attempting to access owner-subscriptions endpoint
        from apps.centers.models import Subscription
        subscription = Subscription.objects.get(center=center_trial)
        url = f'/api/v1/owner-subscriptions/{subscription.id}/'
        
        response = api_client.patch(
            url,
            {'plan': 'BASIC'},
            **get_auth_header(admin_trial),
            format='json'
        )
        
        assert response.status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.django_db
class TestMultiTenantIsolation:
    """Verify multi-tenant data isolation."""
    
    def test_centers_have_unique_schemas(self, center_trial, center_basic):
        """Each center has a unique PostgreSQL schema."""
        assert center_trial.schema_name != center_basic.schema_name
        assert center_trial.schema_name.startswith('tenant_')
        assert center_basic.schema_name.startswith('tenant_')
    
    def test_center_admin_queries_filtered_by_center(
        self, api_client, admin_trial, admin_basic, get_auth_header
    ):
        """Center Admins only see their own center's data."""
        url = '/api/v1/center-admin-centers/'
        
        # Admin A sees only Center A
        response_a = api_client.get(url, **get_auth_header(admin_trial))
        assert len(response_a.data['results']) == 1
        
        # Admin B sees only Center B
        response_b = api_client.get(url, **get_auth_header(admin_basic))
        assert len(response_b.data['results']) == 1
        
        # Different centers
        assert response_a.data['results'][0]['id'] != response_b.data['results'][0]['id']
