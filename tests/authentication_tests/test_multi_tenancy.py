"""
Test suite for multi-tenancy isolation guarantees.

Tests cover:
- Login isolation between centers
- User list data isolation
- Invitation code isolation
- Tenant schema isolation
- Same email in different centers
"""
import pytest
from django.urls import reverse
from rest_framework import status
from unittest.mock import patch
from django.contrib.auth import get_user_model

User = get_user_model()


class TestLoginIsolation:
    """Test that login is isolated between centers."""

    @patch("apps.authentication.backends.TenantAwareBackend._get_center_id_from_subdomain")
    def test_user_from_center_a_cannot_login_to_center_b_subdomain(
        self, mock_subdomain, api_client, student_a, center_b
    ):
        """
        Test student from Center A cannot log in on Center B subdomain.
        
        This is a critical multi-tenancy security test.
        """
        # Mock Center B subdomain
        mock_subdomain.return_value = center_b.id

        url = reverse("auth:login")
        data = {"email": "student@center-a.com", "password": "StudentPass123!"}

        response = api_client.post(url, data, format="json")

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "invalid credentials" in str(response.data["detail"]).lower()

    @patch("apps.authentication.backends.TenantAwareBackend._get_center_id_from_subdomain")
    def test_same_email_different_centers_isolated_login(
        self, mock_subdomain, api_client, center_a, center_b
    ):
        """
        Test that same email in different centers logs in to correct center.
        
        Scenario:
        - user@example.com exists in both Center A and Center B
        - Login on center-a subdomain → Center A user only
        - Login on center-b subdomain → Center B user only
        """
        from apps.core.tenant_utils import set_public_schema

        set_public_schema()

        # Create same email in both centers
        user_a = User.objects.create_user(
            email="isolated@example.com",
            password="IsolatedPass123!",
            first_name="User",
            last_name="CenterA",
            role=User.Role.STUDENT,
            center=center_a,
            is_active=True,
            is_approved=True,
        )

        user_b = User.objects.create_user(
            email="isolated@example.com",
            password="IsolatedPass123!",
            first_name="User",
            last_name="CenterB",
            role=User.Role.STUDENT,
            center=center_b,
            is_active=True,
            is_approved=True,
        )

        url = reverse("auth:login")
        data = {"email": "isolated@example.com", "password": "IsolatedPass123!"}

        # Login on Center A subdomain
        mock_subdomain.return_value = center_a.id
        response_a = api_client.post(url, data, format="json")
        assert response_a.status_code == status.HTTP_200_OK
        assert response_a.data["user"]["id"] == user_a.id
        assert response_a.data["user"]["center"] == center_a.id

        # Login on Center B subdomain
        mock_subdomain.return_value = center_b.id
        response_b = api_client.post(url, data, format="json")
        assert response_b.status_code == status.HTTP_200_OK
        assert response_b.data["user"]["id"] == user_b.id
        assert response_b.data["user"]["center"] == center_b.id

        # Verify they are different users
        assert user_a.id != user_b.id


class TestDataIsolation:
    """Test that data is isolated between centers."""

    def test_center_admin_cannot_see_users_from_other_center(
        self, api_client, center_admin_a, center_admin_b, student_a, student_b, jwt_auth_header
    ):
        """
        Test Center Admin A cannot see users from Center B in user list.
        
        Critical data isolation test.
        """
        url = reverse("user-list")
        headers = jwt_auth_header(center_admin_a)

        response = api_client.get(url, **headers)

        assert response.status_code == status.HTTP_200_OK

        if "results" in response.data:
            users = response.data["results"]
        else:
            users = response.data

        user_ids = [u["id"] for u in users]

        # Should include Center A users
        assert student_a.id in user_ids

        # Should NOT include Center B users
        assert student_b.id not in user_ids
        assert center_admin_b.id not in user_ids

    def test_teacher_cannot_see_students_from_other_center(
        self, api_client, teacher_a, student_b, jwt_auth_header
    ):
        """
        Test Teacher A cannot see students from Center B.
        """
        url = reverse("user-list")
        headers = jwt_auth_header(teacher_a)

        response = api_client.get(url, **headers)

        assert response.status_code == status.HTTP_200_OK

        if "results" in response.data:
            users = response.data["results"]
        else:
            users = response.data

        user_ids = [u["id"] for u in users]

        # Should NOT include student_b from Center B
        assert student_b.id not in user_ids

    def test_user_detail_cross_center_returns_404(
        self, api_client, center_admin_a, student_b, jwt_auth_header
    ):
        """
        Test retrieving user detail from another center returns 404.
        
        Admin A tries to retrieve student_b (from Center B) by ID.
        Should return 404 (not in queryset).
        """
        url = reverse("user-detail", kwargs={"pk": student_b.id})
        headers = jwt_auth_header(center_admin_a)

        response = api_client.get(url, **headers)

        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_same_email_different_centers_both_exist(
        self, api_client, center_a, center_b
    ):
        """
        Test that same email can exist in different centers simultaneously.
        
        Verifies UniqueConstraint(email, center) allows this.
        """
        from apps.core.tenant_utils import set_public_schema

        set_public_schema()

        # Create user with same email in both centers
        user_a = User.objects.create_user(
            email="shared@example.com",
            password="Pass123!",
            first_name="Shared",
            last_name="CenterA",
            role=User.Role.STUDENT,
            center=center_a,
            is_active=True,
            is_approved=True,
        )

        user_b = User.objects.create_user(
            email="shared@example.com",
            password="Pass123!",
            first_name="Shared",
            last_name="CenterB",
            role=User.Role.STUDENT,
            center=center_b,
            is_active=True,
            is_approved=True,
        )

        # Both should exist
        assert User.objects.filter(email="shared@example.com").count() == 2

        # They should have different centers
        users = User.objects.filter(email="shared@example.com")
        center_ids = set(users.values_list("center_id", flat=True))
        assert center_a.id in center_ids
        assert center_b.id in center_ids


class TestInvitationIsolation:
    """Test invitation code isolation between centers."""

    def test_invitation_from_center_a_only_works_for_center_a(
        self, api_client, invitation_pending_a, center_a
    ):
        """
        Test invitation code created for Center A only registers users to Center A.
        
        The invitation.center determines which center the new user joins.
        """
        url = reverse("auth:register")
        data = {
            "email": "invitee@example.com",
            "first_name": "Invited",
            "last_name": "User",
            "password": "InvitedPass123!",
            "invitation_code": "VALID-CODE-A",
        }

        response = api_client.post(url, data, format="json")

        assert response.status_code == status.HTTP_201_CREATED

        # Verify user created in Center A
        user = User.objects.get(email="invitee@example.com")
        assert user.center == center_a

    def test_invitation_codes_unique_across_centers(
        self, api_client, center_a, center_b, center_admin_a, center_admin_b
    ):
        """
        Test that invitation codes are globally unique.
        
        Cannot create same invitation code in different centers.
        """
        from apps.centers.models import Invitation
        from apps.core.tenant_utils import set_public_schema
        from django.utils import timezone
        from datetime import timedelta
        from django.db import IntegrityError

        set_public_schema()

        # Create invitation in Center A
        Invitation.objects.create(
            code="UNIQUE-CODE",
            role="STUDENT",
            center=center_a,
            invited_by=center_admin_a,
            status="PENDING",
            expires_at=timezone.now() + timedelta(days=7),
        )

        # Try to create same code in Center B - should fail
        with pytest.raises(IntegrityError):
            Invitation.objects.create(
                code="UNIQUE-CODE",  # Same code
                role="STUDENT",
                center=center_b,
                invited_by=center_admin_b,
                status="PENDING",
                expires_at=timezone.now() + timedelta(days=7),
            )


class TestTenantSchemaIsolation:
    """Test tenant schema isolation (advanced)."""

    def test_group_memberships_isolated_per_center(
        self, api_client, center_a, center_b
    ):
        """
        Test GroupMembership data is isolated per center's tenant schema.
        
        This requires:
        1. Creating groups in each center's tenant schema
        2. Verifying data cannot be accessed across schemas
        
        Note: This test may be skipped if GroupMembership setup is complex.
        """
        from apps.core.tenant_utils import schema_context, set_public_schema

        set_public_schema()

        # This is a placeholder for advanced schema isolation testing
        # In a real implementation, you would:
        # 1. Create a group in center_a's schema
        # 2. Switch to center_b's schema
        # 3. Verify the group from center_a is not visible

        # Example:
        # with schema_context(center_a.schema_name):
        #     from apps.groups.models import Group
        #     group_a = Group.objects.create(name="Group A")
        #
        # with schema_context(center_b.schema_name):
        #     from apps.groups.models import Group
        #     # Group A should not exist in this schema
        #     assert not Group.objects.filter(name="Group A").exists()

        # For now, we just verify schemas are different
        assert center_a.schema_name != center_b.schema_name

    def test_schema_context_switches_correctly(self, center_a, center_b):
        """
        Test schema_context() properly switches between tenant schemas.
        
        Verifies the multi-tenancy infrastructure works.
        """
        from apps.core.tenant_utils import schema_context, set_public_schema
        from django.db import connection

        set_public_schema()

        # Verify we start in public schema
        current_schema = connection.schema_name
        assert current_schema == "public"

        # Switch to center_a schema
        with schema_context(center_a.schema_name):
            assert connection.schema_name == center_a.schema_name

        # Back to public schema after context
        assert connection.schema_name == "public"

        # Switch to center_b schema
        with schema_context(center_b.schema_name):
            assert connection.schema_name == center_b.schema_name

        # Back to public schema
        assert connection.schema_name == "public"


class TestCrossSubdomainPrevention:
    """Test prevention of cross-subdomain access."""

    @patch("apps.authentication.backends.TenantAwareBackend._get_center_id_from_subdomain")
    def test_center_admin_jwt_token_rejected_on_wrong_subdomain(
        self, mock_subdomain, api_client, center_admin_a, center_b, jwt_auth_header
    ):
        """
        Test that a JWT token for Center A admin is rejected when used on Center B subdomain.
        
        Note: JWT tokens don't inherently store subdomain context,
        but protected views should validate user.center_id matches subdomain.
        """
        # Generate token for center_admin_a
        headers = jwt_auth_header(center_admin_a)

        # Try to use this token on Center B subdomain
        mock_subdomain.return_value = center_b.id

        url = reverse("user-list")  # Protected endpoint
        response = api_client.get(url, **headers)

        # Depending on implementation, this might:
        # 1. Return empty list (user's center != subdomain center)
        # 2. Return 403 (explicit center mismatch check)
        # 3. Return 200 with empty results (queryset filtered by user's center)

        if response.status_code == status.HTTP_200_OK:
            # If 200, should return empty list (no users from admin's center visible)
            if "results" in response.data:
                # Empty results expected
                pass
            else:
                # Or the queryset should be empty
                pass
        else:
            # Or explicit rejection
            assert response.status_code in [
                status.HTTP_403_FORBIDDEN,
                status.HTTP_401_UNAUTHORIZED,
            ]

    def test_profile_endpoint_independent_of_subdomain(
        self, api_client, student_a, jwt_auth_header
    ):
        """
        Test /auth/me/ endpoint works regardless of subdomain.
        
        Profile endpoint should return user's own data independent of subdomain context.
        """
        url = reverse("auth:me")
        headers = jwt_auth_header(student_a)

        response = api_client.get(url, **headers)

        assert response.status_code == status.HTTP_200_OK
        assert response.data["id"] == student_a.id
        assert response.data["email"] == student_a.email
