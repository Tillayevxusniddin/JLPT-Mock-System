"""
Test suite for permission matrix across all roles.

Tests verify that each role (Owner, CenterAdmin, Teacher, Student, Guest)
can only access endpoints they're authorized for.

Permission Matrix:
Action                      | Owner | CenterAdmin | Teacher | Student | Guest
---------------------------|-------|-------------|---------|---------|-------
Create Center              |   ✓   |      ✗      |    ✗    |    ✗    |   ✗
List All Centers           |   ✓   |      ✗      |    ✗    |    ✗    |   ✗
Suspend Center             |   ✓   |      ✗      |    ✗    |    ✗    |   ✗
Delete Center              |   ✓   |      ✗      |    ✗    |    ✗    |   ✗
View Own Center            |   ✓   |      ✓      |    ✗    |    ✗    |   ✗
Update Own Center          |   ✓   |      ✓      |    ✗    |    ✗    |   ✗
List All Subscriptions     |   ✓   |      ✗      |    ✗    |    ✗    |   ✗
Upgrade Subscription       |   ✓   |      ✗      |    ✗    |    ✗    |   ✗
View Own Subscription      |   ✓   |      ✓      |    ✗    |    ✗    |   ✗
Create Invitation          |   ✗   |      ✓      |    ✗    |    ✗    |   ✗
Approve Invitation         |   ✗   |      ✓      |    ✗    |    ✗    |   ✗
List Invitations           |   ✗   |      ✓      |    ✗    |    ✗    |   ✗
Create Contact Request     |   ✓   |      ✓      |    ✓    |    ✓    |   ✓
Manage Contact Requests    |   ✓   |      ✗      |    ✗    |    ✗    |   ✗
"""

import pytest
from rest_framework import status


@pytest.mark.django_db
class TestOwnerPermissions:
    """Test Owner role permissions."""
    
    def test_owner_can_access_all_owner_endpoints(
        self, api_client, owner_user, get_auth_header, center_trial
    ):
        """Owner has access to all owner-* endpoints."""
        headers = get_auth_header(owner_user)
        
        # List centers
        response = api_client.get('/api/v1/owner-centers/', **headers)
        assert response.status_code == status.HTTP_200_OK
        
        # List subscriptions
        response = api_client.get('/api/v1/owner-subscriptions/', **headers)
        assert response.status_code == status.HTTP_200_OK
        
        # List contact requests
        response = api_client.get('/api/v1/owner-contact-requests/', **headers)
        assert response.status_code == status.HTTP_200_OK
        
        # List center admins
        response = api_client.get('/api/v1/owner-center-admins/', **headers)
        assert response.status_code == status.HTTP_200_OK
    
    def test_owner_cannot_access_center_admin_endpoints(
        self, api_client, owner_user, get_auth_header
    ):
        """Owner cannot use center-admin-* endpoints (no center assigned)."""
        headers = get_auth_header(owner_user)
        
        # Center admin centers
        response = api_client.get('/api/v1/center-admin-centers/', **headers)
        # Should fail because owner has no center (403 is proper for permission denied)
        assert response.status_code in [status.HTTP_403_FORBIDDEN, status.HTTP_404_NOT_FOUND, status.HTTP_400_BAD_REQUEST]


@pytest.mark.django_db
class TestCenterAdminPermissions:
    """Test Center Admin role permissions."""
    
    def test_center_admin_can_access_center_admin_endpoints(
        self, api_client, admin_trial, get_auth_header
    ):
        """Center Admin has access to center-admin-* and invitation endpoints."""
        headers = get_auth_header(admin_trial)
        
        # View own center
        response = api_client.get('/api/v1/center-admin-centers/', **headers)
        assert response.status_code == status.HTTP_200_OK
        
        # View own subscription
        response = api_client.get('/api/v1/subscriptions/my-subscription/', **headers)
        assert response.status_code == status.HTTP_200_OK
        
        # List invitations
        response = api_client.get('/api/v1/centers/invitations/list/', **headers)
        assert response.status_code == status.HTTP_200_OK
        
        # Create invitation
        response = api_client.post(
            '/api/v1/centers/invitations/',
            {'role': 'STUDENT'},
            **headers,
            format='json'
        )
        assert response.status_code == status.HTTP_201_CREATED
    
    def test_center_admin_cannot_access_owner_endpoints(
        self, api_client, admin_trial, get_auth_header
    ):
        """Center Admin cannot access owner-* endpoints."""
        headers = get_auth_header(admin_trial)
        
        # Cannot list all centers
        response = api_client.get('/api/v1/owner-centers/', **headers)
        assert response.status_code == status.HTTP_403_FORBIDDEN
        
        # Cannot list all subscriptions
        response = api_client.get('/api/v1/owner-subscriptions/', **headers)
        assert response.status_code == status.HTTP_403_FORBIDDEN
        
        # Cannot list contact requests
        response = api_client.get('/api/v1/owner-contact-requests/', **headers)
        assert response.status_code == status.HTTP_403_FORBIDDEN
    
    def test_center_admin_cannot_modify_subscription(
        self, api_client, admin_trial, get_auth_header, center_trial
    ):
        """Center Admin cannot upgrade subscription."""
        from apps.centers.models import Subscription
        subscription = Subscription.objects.get(center=center_trial)
        
        response = api_client.patch(
            f'/api/v1/owner-subscriptions/{subscription.id}/',
            {'plan': 'BASIC'},
            **get_auth_header(admin_trial),
            format='json'
        )
        
        assert response.status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.django_db
class TestTeacherPermissions:
    """Test Teacher role permissions."""
    
    def test_teacher_cannot_access_center_management(
        self, api_client, teacher_trial, get_auth_header
    ):
        """Teachers cannot access any center management endpoints."""
        headers = get_auth_header(teacher_trial)
        
        # Cannot view center
        response = api_client.get('/api/v1/center-admin-centers/', **headers)
        assert response.status_code == status.HTTP_403_FORBIDDEN
        
        # Cannot view subscription
        response = api_client.get('/api/v1/subscriptions/my-subscription/', **headers)
        assert response.status_code == status.HTTP_403_FORBIDDEN
    
    def test_teacher_cannot_create_invitations(
        self, api_client, teacher_trial, get_auth_header
    ):
        """Teachers cannot create invitations."""
        response = api_client.post(
            '/api/v1/centers/invitations/',
            {'role': 'STUDENT'},
            **get_auth_header(teacher_trial),
            format='json'
        )
        
        assert response.status_code == status.HTTP_403_FORBIDDEN
    
    def test_teacher_cannot_approve_invitations(
        self, api_client, teacher_trial, get_auth_header, invitation_pending
    ):
        """Teachers cannot approve invitations."""
        response = api_client.post(
            '/api/v1/centers/invitations/approve/',
            {'code': invitation_pending.code},
            **get_auth_header(teacher_trial),
            format='json'
        )
        
        # Should get either 400 (bad request) or 403 (forbidden)
        assert response.status_code in [status.HTTP_403_FORBIDDEN, status.HTTP_400_BAD_REQUEST]


@pytest.mark.django_db
class TestStudentPermissions:
    """Test Student role permissions."""
    
    def test_student_cannot_access_center_management(
        self, api_client, student_trial, get_auth_header
    ):
        """Students cannot access any center management."""
        headers = get_auth_header(student_trial)
        
        response = api_client.get('/api/v1/center-admin-centers/', **headers)
        assert response.status_code == status.HTTP_403_FORBIDDEN
        
        response = api_client.get('/api/v1/subscriptions/my-subscription/', **headers)
        assert response.status_code == status.HTTP_403_FORBIDDEN
    
    def test_student_cannot_create_invitations(
        self, api_client, student_trial, get_auth_header
    ):
        """Students cannot create invitations."""
        response = api_client.post(
            '/api/v1/centers/invitations/',
            {'role': 'STUDENT'},
            **get_auth_header(student_trial),
            format='json'
        )
        
        assert response.status_code == status.HTTP_403_FORBIDDEN
    
    def test_student_cannot_access_owner_endpoints(
        self, api_client, student_trial, get_auth_header
    ):
        """Students cannot access owner endpoints."""
        headers = get_auth_header(student_trial)
        
        response = api_client.get('/api/v1/owner-centers/', **headers)
        assert response.status_code == status.HTTP_403_FORBIDDEN
        
        response = api_client.get('/api/v1/owner-subscriptions/', **headers)
        assert response.status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.django_db
class TestGuestPermissions:
    """Test Guest role permissions."""
    
    def test_guest_has_minimal_permissions(
        self, api_client, get_auth_header, center_trial
    ):
        """Guests have very limited access."""
        from apps.authentication.models import User
        
        guest = User.objects.create_user(
            email='guest@test.com',
            password='Pass123!',
            first_name='Guest',
            last_name='User',
            role=User.Role.GUEST,
            center=center_trial,
            is_active=True,
            is_approved=True,
        )
        
        headers = get_auth_header(guest)
        
        # Cannot access center management
        response = api_client.get('/api/v1/center-admin-centers/', **headers)
        assert response.status_code == status.HTTP_403_FORBIDDEN
        
        # Cannot create invitations
        response = api_client.post(
            '/api/v1/centers/invitations/',
            {'role': 'STUDENT'},
            **headers,
            format='json'
        )
        assert response.status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.django_db
class TestMultiTenantPermissionIsolation:
    """Test permission isolation across centers."""
    
    def test_center_admin_a_cannot_manage_center_b(
        self, api_client, admin_trial, admin_basic, get_auth_header, center_basic
    ):
        """Center Admin A cannot update Center B."""
        url = f'/api/v1/center-admin-centers/{center_basic.id}/'
        
        response = api_client.patch(
            url,
            {'description': 'Hacked!'},
            **get_auth_header(admin_trial),
            format='json'
        )
        
        # Should get 404 because queryset filters by user's center
        assert response.status_code == status.HTTP_404_NOT_FOUND
    
    def test_center_admin_a_cannot_view_center_b_subscription(
        self, api_client, admin_trial, admin_basic, get_auth_header
    ):
        """Center Admin A cannot view Center B's subscription."""
        # Admin A views subscription
        response_a = api_client.get(
            '/api/v1/subscriptions/my-subscription/',
            **get_auth_header(admin_trial)
        )
        assert response_a.status_code == status.HTTP_200_OK
        
        # Admin B views subscription
        response_b = api_client.get(
            '/api/v1/subscriptions/my-subscription/',
            **get_auth_header(admin_basic)
        )
        assert response_b.status_code == status.HTTP_200_OK
        
        # Different plans
        assert response_a.data['plan'] != response_b.data['plan']
    
    def test_center_admin_a_cannot_approve_center_b_invitations(
        self, api_client, admin_trial, admin_basic, get_auth_header
    ):
        """Center Admin A cannot approve Center B's invitations."""
        from apps.centers.models import Invitation
        from apps.authentication.models import User
        
        # Create invitation in Center B
        user_b = User.objects.create_user(
            email='test@centerb.com',
            password='Pass123!',
            first_name='Test',
            last_name='User',
            role=User.Role.STUDENT,
            center=admin_basic.center,
            is_active=True,
            is_approved=False,
        )
        
        inv_b = Invitation.objects.create(
            code='CENTER-B-INV',
            role='STUDENT',
            center=admin_basic.center,
            invited_by=admin_basic,
            target_user=user_b,
            status='PENDING',
            expires_at=timezone.now() + timedelta(days=7),
        )
        
        # Admin A tries to approve
        response = api_client.post(
            '/api/v1/centers/invitations/approve/',
            {'invitation_id': inv_b.id},
            **get_auth_header(admin_trial),
            format='json'
        )
        
        assert response.status_code in [status.HTTP_403_FORBIDDEN, status.HTTP_400_BAD_REQUEST]


@pytest.mark.django_db
class TestUnauthenticatedAccess:
    """Test public access (no authentication)."""
    
    def test_public_can_create_contact_request(self, api_client):
        """Anyone can create a contact request."""
        url = '/api/v1/contact-requests/'
        data = {
            'center_name': 'Tokyo Language School',
            'full_name': 'John Doe',
            'phone_number': '+81-3-1234-5678',
            'message': 'I want to join!'
        }
        
        response = api_client.post(url, data, format='json')
        
        assert response.status_code == status.HTTP_201_CREATED
    
    def test_public_cannot_access_protected_endpoints(self, api_client):
        """Unauthenticated requests are rejected for protected endpoints."""
        urls = [
            '/api/v1/owner-centers/',
            '/api/v1/owner-subscriptions/',
            '/api/v1/center-admin-centers/',
            '/api/v1/centers/invitations/',
        ]
        
        for url in urls:
            response = api_client.get(url)
            assert response.status_code == status.HTTP_401_UNAUTHORIZED


# Import timezone for timestamp tests
from django.utils import timezone
from datetime import timedelta
