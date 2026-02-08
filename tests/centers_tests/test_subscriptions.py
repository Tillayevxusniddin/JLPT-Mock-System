"""
Test suite for Subscription management and lifecycle.

Tests cover:
- FREE trial creation on center creation
- Subscription upgrades (FREE → BASIC/PRO/ENTERPRISE)
- Subscription downgrades
- Auto-suspension after FREE trial expiry
- Owner subscription management
- Center Admin read-only subscription view
"""

import pytest
from django.utils import timezone
from datetime import timedelta
from rest_framework import status
from unittest.mock import patch, MagicMock


@pytest.mark.django_db
class TestSubscriptionAutoCreation:
    """Test automatic FREE subscription creation."""
    
    def test_free_subscription_created_on_center_creation(
        self, api_client, owner_user, get_auth_header, mock_celery_task
    ):
        """When center is created, FREE subscription is automatically created."""
        url = '/api/v1/owner-centers/'
        
        with mock_celery_task:
            response = api_client.post(
                url,
                {'name': 'Auto Subscription Test'},
                **get_auth_header(owner_user),
                format='json'
            )
        
        assert response.status_code == status.HTTP_201_CREATED
        
        from apps.centers.models import Subscription, Center
        center = Center.objects.get(id=response.data['id'])
        
        # Verify subscription exists
        assert Subscription.objects.filter(center=center).exists()
        
        subscription = Subscription.objects.get(center=center)
        assert subscription.plan == Subscription.Plan.FREE
        assert subscription.price == 0
        assert subscription.currency == 'USD'
        assert subscription.is_active is True
        assert subscription.auto_renew is False
        
        # Verify 2-month trial period
        trial_days = (subscription.ends_at - subscription.starts_at).days
        assert 59 <= trial_days <= 61  # Allow 1 day variance
    
    def test_center_status_is_trial_on_creation(
        self, api_client, owner_user, get_auth_header, mock_celery_task
    ):
        """New center has TRIAL status."""
        url = '/api/v1/owner-centers/'
        
        with mock_celery_task:
            response = api_client.post(
                url,
                {'name': 'Trial Status Test'},
                **get_auth_header(owner_user),
                format='json'
            )
        
        assert response.data['status'] == 'TRIAL'


@pytest.mark.django_db
class TestSubscriptionUpgrade:
    """Test subscription plan upgrades."""
    
    def test_owner_can_upgrade_trial_to_basic(
        self, api_client, owner_user, get_auth_header, center_trial
    ):
        """Owner upgrades FREE trial to BASIC plan."""
        from apps.centers.models import Subscription
        subscription = Subscription.objects.get(center=center_trial)
        url = f'/api/v1/owner-subscriptions/{subscription.id}/'
        
        response = api_client.patch(
            url,
            {'plan': 'BASIC'},
            **get_auth_header(owner_user),
            format='json'
        )
        
        assert response.status_code == status.HTTP_200_OK
        assert response.data['plan'] == 'BASIC'
        assert float(response.data['price']) == 29.99
        assert response.data['is_active'] is True
        assert response.data['auto_renew'] is True
        
        # Verify center status changed to ACTIVE
        center_trial.refresh_from_db()
        assert center_trial.status == center_trial.Status.ACTIVE
    
    def test_owner_can_upgrade_to_pro(
        self, api_client, owner_user, get_auth_header, center_basic
    ):
        """Owner upgrades BASIC to PRO."""
        from apps.centers.models import Subscription
        subscription = Subscription.objects.get(center=center_basic)
        url = f'/api/v1/owner-subscriptions/{subscription.id}/'
        
        response = api_client.patch(
            url,
            {'plan': 'PRO'},
            **get_auth_header(owner_user),
            format='json'
        )
        
        assert response.status_code == status.HTTP_200_OK
        assert response.data['plan'] == 'PRO'
        assert float(response.data['price']) == 79.99
    
    def test_owner_can_upgrade_suspended_center(
        self, api_client, owner_user, get_auth_header, center_suspended
    ):
        """Owner can upgrade suspended center to reactivate it."""
        from apps.centers.models import Subscription
        subscription = Subscription.objects.get(center=center_suspended)
        url = f'/api/v1/owner-subscriptions/{subscription.id}/'
        
        response = api_client.patch(
            url,
            {'plan': 'BASIC'},
            **get_auth_header(owner_user),
            format='json'
        )
        
        assert response.status_code == status.HTTP_200_OK
        
        # Verify center is now ACTIVE
        center_suspended.refresh_from_db()
        assert center_suspended.status == center_suspended.Status.ACTIVE
        
        # Verify subscription is active
        subscription.refresh_from_db()
        assert subscription.is_active is True
    
    def test_upgrade_endpoint_convenience_method(
        self, api_client, owner_user, get_auth_header, center_trial
    ):
        """Test /upgrade/ convenience endpoint."""
        from apps.centers.models import Subscription
        subscription = Subscription.objects.get(center=center_trial)
        url = f'/api/v1/owner-subscriptions/{subscription.id}/upgrade/'
        
        response = api_client.post(
            url,
            {'plan': 'ENTERPRISE'},
            **get_auth_header(owner_user),
            format='json'
        )
        
        assert response.status_code == status.HTTP_200_OK
        assert 'subscription' in response.data
        assert response.data['subscription']['plan'] == 'ENTERPRISE'
        assert float(response.data['subscription']['price']) == 199.99


@pytest.mark.django_db
class TestSubscriptionListing:
    """Test subscription listing and filtering."""
    
    def test_owner_can_list_all_subscriptions(
        self, api_client, owner_user, get_auth_header,
        center_trial, center_basic, center_suspended
    ):
        """Owner sees all subscriptions."""
        url = '/api/v1/owner-subscriptions/'
        
        response = api_client.get(url, **get_auth_header(owner_user))
        
        assert response.status_code == status.HTTP_200_OK
        assert len(response.data['results']) >= 3
    
    def test_owner_can_filter_by_plan(
        self, api_client, owner_user, get_auth_header, center_trial, center_basic
    ):
        """Owner can filter subscriptions by plan."""
        url = '/api/v1/owner-subscriptions/?plan=FREE'
        
        response = api_client.get(url, **get_auth_header(owner_user))
        
        assert response.status_code == status.HTTP_200_OK
        assert all(sub['plan'] == 'FREE' for sub in response.data['results'])
    
    def test_owner_can_filter_by_active_status(
        self, api_client, owner_user, get_auth_header, center_suspended
    ):
        """Owner can filter by is_active status."""
        url = '/api/v1/owner-subscriptions/?is_active=false'
        
        response = api_client.get(url, **get_auth_header(owner_user))
        
        assert response.status_code == status.HTTP_200_OK
        # Suspended center should have inactive subscription
        suspended_subs = [s for s in response.data['results'] 
                         if s['center_id'] == center_suspended.id]
        assert len(suspended_subs) > 0
    
    def test_subscription_detail_includes_center_info(
        self, api_client, owner_user, get_auth_header, center_trial
    ):
        """Subscription detail includes center name and ID."""
        from apps.centers.models import Subscription
        subscription = Subscription.objects.get(center=center_trial)
        url = f'/api/v1/owner-subscriptions/{subscription.id}/'
        
        response = api_client.get(url, **get_auth_header(owner_user))
        
        assert response.status_code == status.HTTP_200_OK
        assert response.data['center_id'] == center_trial.id
        assert response.data['center_name'] == center_trial.name


@pytest.mark.django_db
class TestCenterAdminSubscriptionView:
    """Test Center Admin's read-only subscription access."""
    
    def test_center_admin_can_view_own_subscription(
        self, api_client, admin_trial, get_auth_header, center_trial
    ):
        """Center Admin can view their center's subscription."""
        url = '/api/v1/subscriptions/my-subscription/'
        
        response = api_client.get(url, **get_auth_header(admin_trial))
        
        assert response.status_code == status.HTTP_200_OK
        assert response.data['plan'] == 'FREE'
        assert 'days_remaining' in response.data
        assert 'is_expired' in response.data
    
    def test_center_admin_sees_correct_days_remaining(
        self, api_client, admin_trial, get_auth_header, center_trial_expiring_soon
    ):
        """Center Admin sees accurate days remaining."""
        from apps.centers.models import Subscription
        from apps.authentication.models import User
        
        # Create admin for expiring center
        admin = User.objects.create_user(
            email="admin@expiring.com",
            password="Pass123!",
            first_name="Admin",
            last_name="Expiring",
            role=User.Role.CENTERADMIN,
            center=center_trial_expiring_soon,
            is_active=True,
            is_approved=True,
        )
        
        url = '/api/v1/subscriptions/my-subscription/'
        response = api_client.get(url, **get_auth_header(admin))
        
        assert response.status_code == status.HTTP_200_OK
        assert 1 <= response.data['days_remaining'] <= 3
    
    def test_center_admin_cannot_modify_subscription(
        self, api_client, admin_trial, get_auth_header
    ):
        """Center Admin cannot upgrade subscription (owner-only)."""
        url = '/api/v1/subscriptions/my-subscription/'
        
        response = api_client.patch(
            url,
            {'plan': 'BASIC'},
            **get_auth_header(admin_trial),
            format='json'
        )
        
        # Endpoint is GET-only
        assert response.status_code == status.HTTP_405_METHOD_NOT_ALLOWED
    
    def test_teacher_cannot_view_subscription(
        self, api_client, teacher_trial, get_auth_header
    ):
        """Teachers cannot view subscription details."""
        url = '/api/v1/subscriptions/my-subscription/'
        
        response = api_client.get(url, **get_auth_header(teacher_trial))
        
        assert response.status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.django_db
class TestAutoSuspensionTask:
    """Test automatically suspension of expired FREE trials."""
    
    def test_expired_centers_are_suspended(self, center_expired):
        """Expired FREE trial centers are suspended by Celery task."""
        from apps.centers.tasks import check_and_suspend_expired_subscriptions
        
        # Run the task directly
        result = check_and_suspend_expired_subscriptions()
        
        # Verify center was suspended
        center_expired.refresh_from_db()
        assert center_expired.status == center_expired.Status.SUSPENDED
        
        # Verify subscription is now inactive
        from apps.centers.models import Subscription
        subscription = Subscription.objects.get(center=center_expired)
        assert subscription.is_active is False
    
    def test_active_paid_subscriptions_not_affected(self, center_basic):
        """Active paid subscriptions are not touched by auto-suspension."""
        from apps.centers.tasks import check_and_suspend_expired_subscriptions
        
        original_status = center_basic.status
        
        check_and_suspend_expired_subscriptions()
        
        # Center should remain ACTIVE
        center_basic.refresh_from_db()
        assert center_basic.status == original_status
        assert center_basic.status == center_basic.Status.ACTIVE
    
    def test_trial_centers_with_time_remaining_not_suspended(self, center_trial):
        """Centers with time remaining in trial are not suspended."""
        from apps.centers.tasks import check_and_suspend_expired_subscriptions
        
        check_and_suspend_expired_subscriptions()
        
        # Center should remain in TRIAL
        center_trial.refresh_from_db()
        assert center_trial.status == center_trial.Status.TRIAL


@pytest.mark.django_db
class TestSubscriptionEdgeCases:
    """Test edge cases and validation."""
    
    def test_cannot_upgrade_to_invalid_plan(
        self, api_client, owner_user, get_auth_header, center_trial
    ):
        """Invalid plan names are rejected."""
        from apps.centers.models import Subscription
        subscription = Subscription.objects.get(center=center_trial)
        url = f'/api/v1/owner-subscriptions/{subscription.id}/'
        
        response = api_client.patch(
            url,
            {'plan': 'INVALID_PLAN'},
            **get_auth_header(owner_user),
            format='json'
        )
        
        assert response.status_code == status.HTTP_400_BAD_REQUEST
    
    def test_subscription_properties_calculated_correctly(self, center_expired):
        """is_expired and days_remaining properties work correctly."""
        from apps.centers.models import Subscription
        subscription = Subscription.objects.get(center=center_expired)
        
        assert subscription.is_expired is True
        assert subscription.days_remaining == 0
    
    def test_subscription_not_expired_when_active(self, center_trial):
        """Active subscription with future end date is not expired."""
        from apps.centers.models import Subscription
        subscription = Subscription.objects.get(center=center_trial)
        
        assert subscription.is_expired is False
        assert subscription.days_remaining > 0
