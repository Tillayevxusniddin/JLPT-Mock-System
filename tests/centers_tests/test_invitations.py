"""
Test suite for Invitation management and workflow.

Tests cover:
- Center Admin creates invitations (single and bulk)
- Invitation listing and filtering
- Invitation approval workflow
- Guest invitations (24-hour expiry)
- Multi-tenant isolation (Center A cannot approve Center B invitations)
"""

import pytest
from django.utils import timezone
from datetime import timedelta
from rest_framework import status


@pytest.mark.django_db
class TestInvitationCreation:
    """Test invitation creation by Center Admin."""
    
    def test_center_admin_creates_single_student_invitation(
        self, api_client, admin_trial, get_auth_header
    ):
        """Center Admin creates single STUDENT invitation."""
        url = '/api/v1/centers/invitations/'
        data = {'role': 'STUDENT'}
        
        response = api_client.post(
            url,
            data,
            **get_auth_header(admin_trial),
            format='json'
        )
        
        assert response.status_code == status.HTTP_201_CREATED
        assert response.data['role'] == 'STUDENT'
        assert response.data['code'] is not None
        assert len(response.data['code']) == 10  # Invitation codes are 10 characters
        assert response.data['status'] == 'PENDING'
        assert response.data['is_guest'] is False
    
    def test_center_admin_creates_teacher_invitation(
        self, api_client, admin_trial, get_auth_header
    ):
        """Center Admin can create TEACHER invitation."""
        url = '/api/v1/centers/invitations/'
        data = {'role': 'TEACHER'}
        
        response = api_client.post(
            url,
            data,
            **get_auth_header(admin_trial),
            format='json'
        )
        
        assert response.status_code == status.HTTP_201_CREATED
        assert response.data['role'] == 'TEACHER'
    
    def test_center_admin_creates_bulk_invitations(
        self, api_client, admin_trial, get_auth_header
    ):
        """Center Admin creates multiple invitations at once."""
        url = '/api/v1/centers/invitations/'
        data = {
            'role': 'STUDENT',
            'quantity': 5
        }
        
        response = api_client.post(
            url,
            data,
            **get_auth_header(admin_trial),
            format='json'
        )
        
        assert response.status_code == status.HTTP_201_CREATED
        assert isinstance(response.data, list)
        assert len(response.data) == 5
        
        # All should have unique codes
        codes = [inv['code'] for inv in response.data]
        assert len(codes) == len(set(codes))
        
        # All should be STUDENT role
        assert all(inv['role'] == 'STUDENT' for inv in response.data)
    
    def test_center_admin_creates_guest_invitation(
        self, api_client, admin_trial, get_auth_header
    ):
        """Center Admin creates guest invitation with 24h expiry."""
        url = '/api/v1/centers/invitations/'
        data = {
            'role': 'STUDENT',
            'is_guest': True
        }
        
        response = api_client.post(
            url,
            data,
            **get_auth_header(admin_trial),
            format='json'
        )
        
        assert response.status_code == status.HTTP_201_CREATED
        assert response.data['is_guest'] is True
        
        # Verify expiry is ~24 hours
        from apps.centers.models import Invitation
        invitation = Invitation.objects.get(code=response.data['code'])
        hours_until_expiry = (invitation.expires_at - timezone.now()).total_seconds() / 3600
        assert 23 <= hours_until_expiry <= 25
    
    def test_teacher_cannot_create_invitations(
        self, api_client, teacher_trial, get_auth_header
    ):
        """Teachers cannot create invitations (admin-only)."""
        url = '/api/v1/centers/invitations/'
        data = {'role': 'STUDENT'}
        
        response = api_client.post(
            url,
            data,
            **get_auth_header(teacher_trial),
            format='json'
        )
        
        assert response.status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.django_db
class TestInvitationListing:
    """Test invitation listing and filtering."""
    
    def test_center_admin_lists_own_center_invitations(
        self, api_client, admin_trial, get_auth_header,
        invitation_pending, invitation_expired
    ):
        """Center Admin sees only their center's invitations."""
        url = '/api/v1/centers/invitations/list/'
        
        response = api_client.get(url, **get_auth_header(admin_trial))
        
        assert response.status_code == status.HTTP_200_OK
        assert len(response.data['results']) >= 2
        
        # All should belong to admin's center
        for inv in response.data['results']:
            assert inv['center'] == admin_trial.center_id
    
    def test_center_admin_cannot_see_other_center_invitations(
        self, api_client, admin_trial, admin_basic, get_auth_header
    ):
        """Center Admin A cannot see Center B's invitations."""
        from apps.centers.models import Invitation
        
        # Create invitation in Center B
        Invitation.objects.create(
            code='CENTER-B-INV',
            role='STUDENT',
            center=admin_basic.center,
            invited_by=admin_basic,
            status='PENDING',
            expires_at=timezone.now() + timedelta(days=7),
        )
        
        url = '/api/v1/centers/invitations/list/'
        response = api_client.get(url, **get_auth_header(admin_trial))
        
        # Should not see Center B's invitation
        codes = [inv['code'] for inv in response.data['results']]
        assert 'CENTER-B-INV' not in codes
    
    def test_filter_invitations_by_role(
        self, api_client, admin_trial, get_auth_header,
        invitation_pending, invitation_teacher_pending
    ):
        """Filter invitations by role."""
        url = '/api/v1/centers/invitations/list/?role=TEACHER'
        
        response = api_client.get(url, **get_auth_header(admin_trial))
        
        assert response.status_code == status.HTTP_200_OK
        assert all(inv['role'] == 'TEACHER' for inv in response.data['results'])
    
    def test_filter_invitations_by_status(
        self, api_client, admin_trial, get_auth_header,
        invitation_pending, invitation_approved
    ):
        """Filter invitations by status."""
        url = '/api/v1/centers/invitations/list/?status=PENDING'
        
        response = api_client.get(url, **get_auth_header(admin_trial))
        
        assert response.status_code == status.HTTP_200_OK
        assert all(inv['status'] == 'PENDING' for inv in response.data['results'])
    
    def test_filter_unused_invitations(
        self, api_client, admin_trial, get_auth_header,
        invitation_pending, invitation_approved
    ):
        """Filter for unused invitations (no target_user)."""
        url = '/api/v1/centers/invitations/list/?is_used=false'
        
        response = api_client.get(url, **get_auth_header(admin_trial))
        
        assert response.status_code == status.HTTP_200_OK
        # Pending invitation should be in list
        codes = [inv['code'] for inv in response.data['results']]
        assert invitation_pending.code in codes


@pytest.mark.django_db
class TestInvitationApproval:
    """Test invitation approval workflow."""
    
    def test_center_admin_approves_pending_invitation(
        self, api_client, admin_trial, get_auth_header, invitation_pending, student_trial
    ):
        """Center Admin approves an invitation after user registers."""
        # First, claim the invitation (simulate registration)
        invitation_pending.target_user = student_trial
        invitation_pending.save()
        
        url = '/api/v1/centers/invitations/approve/'
        data = {'invitation_id': invitation_pending.id}
        
        response = api_client.post(
            url,
            data,
            **get_auth_header(admin_trial),
            format='json'
        )
        
        assert response.status_code == status.HTTP_200_OK
        
        # Verify invitation is approved
        invitation_pending.refresh_from_db()
        assert invitation_pending.status == 'APPROVED'
        assert invitation_pending.approved_by == admin_trial
        
        # Verify user is now approved
        student_trial.refresh_from_db()
        assert student_trial.is_approved is True
    
    def test_cannot_approve_expired_invitation(
        self, api_client, admin_trial, get_auth_header, invitation_expired
    ):
        """Cannot approve expired invitation."""
        url = '/api/v1/centers/invitations/approve/'
        data = {'invitation_id': invitation_expired.id}
        
        response = api_client.post(
            url,
            data,
            **get_auth_header(admin_trial),
            format='json'
        )
        
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert 'expired' in str(response.data).lower()
    
    def test_cannot_approve_invitation_from_other_center(
        self, api_client, admin_trial, admin_basic, get_auth_header
    ):
        """Center Admin A cannot approve Center B's invitation."""
        from apps.centers.models import Invitation
        from apps.authentication.models import User
        
        # Create user and invitation in Center B
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
            code='INV-B',
            role='STUDENT',
            center=admin_basic.center,
            invited_by=admin_basic,
            target_user=user_b,
            status='PENDING',
            expires_at=timezone.now() + timedelta(days=7),
        )
        
        # Admin A tries to approve Center B's invitation
        url = '/api/v1/centers/invitations/approve/'
        data = {'invitation_id': inv_b.id}
        
        response = api_client.post(
            url,
            data,
            **get_auth_header(admin_trial),
            format='json'
        )
        
        assert response.status_code in [status.HTTP_403_FORBIDDEN, status.HTTP_400_BAD_REQUEST]
    
    def test_teacher_cannot_approve_invitations(
        self, api_client, teacher_trial, get_auth_header, invitation_pending
    ):
        """Teachers cannot approve invitations."""
        url = '/api/v1/centers/invitations/approve/'
        data = {'invitation_id': invitation_pending.id}
        
        response = api_client.post(
            url,
            data,
            **get_auth_header(teacher_trial),
            format='json'
        )
        
        assert response.status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.django_db
class TestGuestInvitations:
    """Test guest invitation specific behavior."""
    
    def test_guest_invitation_has_short_expiry(
        self, api_client, admin_trial, get_auth_header
    ):
        """Guest invitations expire in 24 hours."""
        url = '/api/v1/centers/invitations/'
        data = {
            'role': 'STUDENT',
            'is_guest': True
        }
        
        response = api_client.post(
            url,
            data,
            **get_auth_header(admin_trial),
            format='json'
        )
        
        assert response.status_code == status.HTTP_201_CREATED
        
        from apps.centers.models import Invitation
        invitation = Invitation.objects.get(code=response.data['code'])
        
        time_until_expiry = invitation.expires_at - timezone.now()
        hours = time_until_expiry.total_seconds() / 3600
        
        assert 23 <= hours <= 25  # ~24 hours
    
    def test_guest_approved_becomes_student(
        self, api_client, admin_trial, get_auth_header, invitation_guest
    ):
        """Approved guest invitation results in STUDENT role."""
        from apps.authentication.models import User
        
        # Create guest user
        guest = User.objects.create_user(
            email='guest@test.com',
            password='Pass123!',
            first_name='Guest',
            last_name='User',
            role=User.Role.GUEST,
            center=admin_trial.center,
            is_active=True,
            is_approved=False,
        )
        
        invitation_guest.target_user = guest
        invitation_guest.save()
        
        url = '/api/v1/centers/invitations/approve/'
        data = {'invitation_id': invitation_guest.id}
        
        response = api_client.post(
            url,
            data,
            **get_auth_header(admin_trial),
            format='json'
        )
        
        assert response.status_code == status.HTTP_200_OK
        
        # Guest should now be STUDENT
        guest.refresh_from_db()
        assert guest.role == User.Role.STUDENT
        assert guest.is_approved is True


@pytest.mark.django_db
class TestInvitationEdgeCases:
    """Test invitation edge cases and validation."""
    
    def test_cannot_create_more_than_100_bulk_invitations(
        self, api_client, admin_trial, get_auth_header
    ):
        """Bulk creation is limited to prevent abuse."""
        url = '/api/v1/centers/invitations/'
        data = {
            'role': 'STUDENT',
            'quantity': 150
        }
        
        response = api_client.post(
            url,
            data,
            **get_auth_header(admin_trial),
            format='json'
        )
        
        assert response.status_code == status.HTTP_400_BAD_REQUEST
    
    def test_invitation_code_is_unique(
        self, api_client, admin_trial, get_auth_header
    ):
        """Each invitation gets a unique code."""
        url = '/api/v1/centers/invitations/'
        
        codes = set()
        for _ in range(10):
            response = api_client.post(
                url,
                {'role': 'STUDENT'},
                **get_auth_header(admin_trial),
                format='json'
            )
            assert response.status_code == status.HTTP_201_CREATED
            codes.add(response.data['code'])
        
        assert len(codes) == 10  # All unique
    
    def test_cannot_approve_already_approved_invitation(
        self, api_client, admin_trial, get_auth_header, invitation_approved
    ):
        """Cannot re-approve an invitation."""
        url = '/api/v1/centers/invitations/approve/'
        data = {'invitation_id': invitation_approved.id}
        
        response = api_client.post(
            url,
            data,
            **get_auth_header(admin_trial),
            format='json'
        )
        
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert 'already' in str(response.data).lower() or 'processed' in str(response.data).lower()
