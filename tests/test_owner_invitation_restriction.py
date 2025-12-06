"""
Test to verify Owner cannot access invitation system
"""
from django.test import TestCase
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient
from rest_framework import status
from apps.organizations.models import Organization
from apps.invitations.models import Invitation

User = get_user_model()


class OwnerInvitationRestrictionTest(TestCase):
    """Test that Owner cannot interfere with organization's invitation system"""
    
    def setUp(self):
        """Set up test data"""
        # Create organization
        self.org = Organization.objects.create(
            name="Test Center",
            slug="test-center",
            email="test@center.com",
            schema_name="tenant_test_center"
        )
        
        # Create Owner user (no organization)
        self.owner = User.objects.create_user(
            email="owner@platform.com",
            password="testpass123",
            first_name="Platform",
            last_name="Owner",
            role="OWNER",
            is_approved=True,
            is_active=True
        )
        
        # Create CenterAdmin user
        self.center_admin = User.objects.create_user(
            email="admin@center.com",
            password="testpass123",
            first_name="Center",
            last_name="Admin",
            role="CENTERADMIN",
            organization=self.org,
            is_approved=True,
            is_active=True
        )
        
        # Create invitation by CenterAdmin
        self.invitation = Invitation.objects.create(
            organization=self.org,
            created_by=self.center_admin,
            role="STUDENT",
            usage_limit=1
        )
        
        self.client = APIClient()
    
    def test_owner_cannot_list_invitations(self):
        """Owner should NOT be able to list invitations"""
        self.client.force_authenticate(user=self.owner)
        response = self.client.get('/api/v1/invitations/')
        
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
    
    def test_owner_cannot_create_invitation(self):
        """Owner should NOT be able to create invitations"""
        self.client.force_authenticate(user=self.owner)
        response = self.client.post('/api/v1/invitations/create/', {
            'role': 'TEACHER',
            'usage_limit': 10
        })
        
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
    
    def test_owner_cannot_view_invitation_detail(self):
        """Owner should NOT be able to view invitation details"""
        self.client.force_authenticate(user=self.owner)
        response = self.client.get(f'/api/v1/invitations/{self.invitation.id}/')
        
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
    
    def test_owner_cannot_update_invitation(self):
        """Owner should NOT be able to update invitations"""
        self.client.force_authenticate(user=self.owner)
        response = self.client.patch(f'/api/v1/invitations/{self.invitation.id}/update/', {
            'is_active': False
        })
        
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
    
    def test_center_admin_can_list_invitations(self):
        """CenterAdmin SHOULD be able to list their organization's invitations"""
        self.client.force_authenticate(user=self.center_admin)
        response = self.client.get('/api/v1/invitations/')
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['results']), 1)
    
    def test_center_admin_can_create_invitation(self):
        """CenterAdmin SHOULD be able to create invitations"""
        self.client.force_authenticate(user=self.center_admin)
        response = self.client.post('/api/v1/invitations/create/', {
            'role': 'TEACHER',
            'usage_limit': 5
        })
        
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(Invitation.objects.filter(organization=self.org).count(), 2)
    
    def test_center_admin_can_view_invitation_detail(self):
        """CenterAdmin SHOULD be able to view invitation details"""
        self.client.force_authenticate(user=self.center_admin)
        response = self.client.get(f'/api/v1/invitations/{self.invitation.id}/')
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['code'], self.invitation.code)
    
    def test_center_admin_can_update_invitation(self):
        """CenterAdmin SHOULD be able to update invitations"""
        self.client.force_authenticate(user=self.center_admin)
        response = self.client.patch(f'/api/v1/invitations/{self.invitation.id}/update/', {
            'is_active': False
        })
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.invitation.refresh_from_db()
        self.assertFalse(self.invitation.is_active)
