"""
Test suite for user registration via invitation system.

Tests cover:
- Valid registration with invitation codes
- Expired/claimed/invalid invitation handling
- Email uniqueness per center validation
- Same email across different centers
- Admin role registration rejection
"""
import pytest
from django.urls import reverse
from rest_framework import status
from django.contrib.auth import get_user_model

User = get_user_model()


def _get_error_detail(response, key):
    """Return error detail for a field, supporting wrapped error responses."""
    data = response.data
    if isinstance(data, dict) and "error" in data and isinstance(data["error"], dict):
        data = data["error"]
    if isinstance(data, dict):
        return data.get(key)
    return None


class TestRegistrationValidScenarios:
    """Test successful registration scenarios."""

    def test_register_with_valid_invitation_student(
        self, api_client, invitation_pending_a, center_a
    ):
        """
        Test successful registration with valid STUDENT invitation.
        
        Verifies:
        - User created with correct role and center
        - Invitation target_user updated
        - User is_approved=False (pending admin approval)
        """
        url = reverse("auth:register")
        data = {
            "email": "newstudent@example.com",
            "first_name": "New",
            "last_name": "Student",
            "password": "SecurePass123!",
            "invitation_code": "VALID-CODE-A",
        }

        response = api_client.post(url, data, format="json")

        assert response.status_code == status.HTTP_201_CREATED
        assert response.data["email"] == "newstudent@example.com"
        assert response.data["role"] == User.Role.STUDENT

        # Verify user created in database
        user = User.objects.get(email="newstudent@example.com")
        assert user.first_name == "New"
        assert user.last_name == "Student"
        assert user.role == User.Role.STUDENT
        assert user.center == center_a
        assert user.is_approved is False  # Pending approval
        assert user.is_active is True
        assert user.check_password("SecurePass123!")

        # Verify invitation updated
        invitation_pending_a.refresh_from_db()
        assert invitation_pending_a.target_user == user

    def test_register_with_valid_invitation_teacher(
        self, api_client, center_a, center_admin_a
    ):
        """Test successful registration with TEACHER invitation."""
        from apps.centers.models import Invitation
        from apps.core.tenant_utils import set_public_schema
        from django.utils import timezone
        from datetime import timedelta

        set_public_schema()

        # Create teacher invitation
        invitation = Invitation.objects.create(
            code="TEACH-COD-A",
            role="TEACHER",
            center=center_a,
            invited_by=center_admin_a,
            status="PENDING",
            expires_at=timezone.now() + timedelta(days=7),
            is_guest=False,
        )

        url = reverse("auth:register")
        data = {
            "email": "newteacher@example.com",
            "first_name": "New",
            "last_name": "Teacher",
            "password": "TeacherPass123!",
            "invitation_code": "TEACH-COD-A",
        }

        response = api_client.post(url, data, format="json")

        assert response.status_code == status.HTTP_201_CREATED
        assert response.data["role"] == User.Role.TEACHER

        user = User.objects.get(email="newteacher@example.com")
        assert user.role == User.Role.TEACHER
        assert user.center == center_a

    def test_register_with_valid_invitation_guest(
        self, api_client, center_a, center_admin_a
    ):
        """Test successful registration with GUEST invitation."""
        from apps.centers.models import Invitation
        from apps.core.tenant_utils import set_public_schema
        from django.utils import timezone
        from datetime import timedelta

        set_public_schema()

        invitation = Invitation.objects.create(
            code="GUEST-CODE-A",
            role="GUEST",
            center=center_a,
            invited_by=center_admin_a,
            status="PENDING",
            expires_at=timezone.now() + timedelta(hours=24),
            is_guest=True,
        )

        url = reverse("auth:register")
        data = {
            "email": "guestuser@example.com",
            "first_name": "Guest",
            "last_name": "User",
            "password": "GuestPass123!",
            "invitation_code": "GUEST-CODE-A",
        }

        response = api_client.post(url, data, format="json")

        assert response.status_code == status.HTTP_201_CREATED
        user = User.objects.get(email="guestuser@example.com")
        assert user.role == User.Role.GUEST


class TestRegistrationInvalidScenarios:
    """Test registration failure scenarios."""

    def test_register_with_expired_invitation(self, api_client, invitation_expired_a):
        """
        Test registration fails with expired invitation.
        
        Verifies:
        - 400 error returned
        - Error message indicates expiration
        - No user created
        """
        url = reverse("auth:register")
        data = {
            "email": "shouldfail@example.com",
            "first_name": "Should",
            "last_name": "Fail",
            "password": "SecurePass123!",
            "invitation_code": "EXPIRE-COD-A",
        }

        response = api_client.post(url, data, format="json")

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        err = _get_error_detail(response, "invitation_code")
        assert err is not None
        assert "expired" in str(err).lower()

        # Verify no user created
        assert not User.objects.filter(email="shouldfail@example.com").exists()

    def test_register_with_already_claimed_invitation(
        self, api_client, invitation_claimed_a
    ):
        """
        Test registration fails with already claimed invitation.
        
        Verifies:
        - 400 error returned
        - Error message indicates invitation already claimed
        """
        url = reverse("auth:register")
        data = {
            "email": "anotherstudent@example.com",
            "first_name": "Another",
            "last_name": "Student",
            "password": "SecurePass123!",
            "invitation_code": "CLAIM-COD-A",
        }

        response = api_client.post(url, data, format="json")

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        err = _get_error_detail(response, "invitation_code")
        assert err is not None
        assert "already claimed" in str(err).lower()

        assert not User.objects.filter(email="anotherstudent@example.com").exists()

    def test_register_with_invalid_invitation_code(self, api_client):
        """Test registration fails with non-existent invitation code."""
        url = reverse("auth:register")
        data = {
            "email": "invalid@example.com",
            "first_name": "Invalid",
            "last_name": "Code",
            "password": "SecurePass123!",
            "invitation_code": "INVALID-CODE-123",
        }

        response = api_client.post(url, data, format="json")

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        err = _get_error_detail(response, "invitation_code")
        assert err is not None
        assert "invalid" in str(err).lower()

    def test_register_with_admin_role_invitation(
        self, api_client, invitation_admin_role_a
    ):
        """
        Test registration fails with CENTER_ADMIN or OWNER invitation.
        
        Admin roles should not be allowed via public registration API.
        """
        url = reverse("auth:register")
        data = {
            "email": "admin@example.com",
            "first_name": "Admin",
            "last_name": "User",
            "password": "AdminPass123!",
            "invitation_code": "ADMIN-COD-A",
        }

        response = api_client.post(url, data, format="json")

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        err = _get_error_detail(response, "invitation_code")
        assert err is not None
        assert (
            "administrators cannot register" in str(err).lower()
            or "contact system support" in str(err).lower()
        )

    def test_register_duplicate_email_same_center(
        self, api_client, student_a, center_a, center_admin_a
    ):
        """
        Test registration fails when email already exists in the same center.
        
        Verifies UniqueConstraint(email, center) enforcement.
        """
        from apps.centers.models import Invitation
        from apps.core.tenant_utils import set_public_schema
        from django.utils import timezone
        from datetime import timedelta

        set_public_schema()

        # Create new invitation for same center
        invitation = Invitation.objects.create(
            code="DUPL-TEST-1",
            role="STUDENT",
            center=center_a,
            invited_by=center_admin_a,
            status="PENDING",
            expires_at=timezone.now() + timedelta(days=7),
        )

        url = reverse("auth:register")
        data = {
            "email": "student@center-a.com",  # Already exists
            "first_name": "Duplicate",
            "last_name": "Student",
            "password": "SecurePass123!",
            "invitation_code": "DUPL-TEST-1",
        }

        response = api_client.post(url, data, format="json")

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        err = _get_error_detail(response, "email")
        assert err is not None
        assert "already exists" in str(err).lower()


class TestRegistrationEdgeCases:
    """Test edge cases and special scenarios."""

    def test_register_same_email_different_centers(
        self, api_client, center_a, center_b, center_admin_a, center_admin_b
    ):
        """
        Test that same email can be registered in different centers.
        
        This is allowed by UniqueConstraint(email, center).
        """
        from apps.centers.models import Invitation
        from apps.core.tenant_utils import set_public_schema
        from django.utils import timezone
        from datetime import timedelta

        set_public_schema()

        # Create invitations for both centers
        invitation_a = Invitation.objects.create(
            code="SAME-EMAIL-A",
            role="STUDENT",
            center=center_a,
            invited_by=center_admin_a,
            status="PENDING",
            expires_at=timezone.now() + timedelta(days=7),
        )

        invitation_b = Invitation.objects.create(
            code="SAME-EMAIL-B",
            role="STUDENT",
            center=center_b,
            invited_by=center_admin_b,
            status="PENDING",
            expires_at=timezone.now() + timedelta(days=7),
        )

        url = reverse("auth:register")

        # Register in Center A
        data_a = {
            "email": "sameemail@example.com",
            "first_name": "User",
            "last_name": "CenterA",
            "password": "SecurePass123!",
            "invitation_code": "SAME-EMAIL-A",
        }
        response_a = api_client.post(url, data_a, format="json")
        assert response_a.status_code == status.HTTP_201_CREATED

        # Register same email in Center B - should succeed
        data_b = {
            "email": "sameemail@example.com",
            "first_name": "User",
            "last_name": "CenterB",
            "password": "SecurePass123!",
            "invitation_code": "SAME-EMAIL-B",
        }
        response_b = api_client.post(url, data_b, format="json")
        assert response_b.status_code == status.HTTP_201_CREATED

        # Verify both users exist with different centers
        users = User.objects.filter(email="sameemail@example.com")
        assert users.count() == 2
        assert set(users.values_list("center_id", flat=True)) == {
            center_a.id,
            center_b.id,
        }

    def test_register_with_missing_required_fields(self, api_client):
        """Test registration fails when required fields are missing."""
        url = reverse("auth:register")

        # Missing first_name
        data = {
            "email": "test@example.com",
            "last_name": "User",
            "password": "SecurePass123!",
            "invitation_code": "SOME-CODE",
        }
        response = api_client.post(url, data, format="json")
        assert response.status_code == status.HTTP_400_BAD_REQUEST

        # Missing password
        data = {
            "email": "test@example.com",
            "first_name": "Test",
            "last_name": "User",
            "invitation_code": "SOME-CODE",
        }
        response = api_client.post(url, data, format="json")
        assert response.status_code == status.HTTP_400_BAD_REQUEST

        # Missing invitation_code
        data = {
            "email": "test@example.com",
            "first_name": "Test",
            "last_name": "User",
            "password": "SecurePass123!",
        }
        response = api_client.post(url, data, format="json")
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_register_with_weak_password(self, api_client, invitation_pending_a):
        """Test registration fails with weak password."""
        url = reverse("auth:register")
        data = {
            "email": "weakpass@example.com",
            "first_name": "Weak",
            "last_name": "Password",
            "password": "123",  # Too short
            "invitation_code": "VALID-CODE-A",
        }

        response = api_client.post(url, data, format="json")

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        # Password validation might be in 'password' or 'non_field_errors'
        err = _get_error_detail(response, "password")
        non_field = _get_error_detail(response, "non_field_errors")
        assert err is not None or non_field is not None

    def test_register_with_invalid_email_format(self, api_client, invitation_pending_a):
        """Test registration fails with invalid email format."""
        url = reverse("auth:register")
        data = {
            "email": "not-an-email",
            "first_name": "Invalid",
            "last_name": "Email",
            "password": "SecurePass123!",
            "invitation_code": "VALID-CODE-A",
        }

        response = api_client.post(url, data, format="json")

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        err = _get_error_detail(response, "email")
        assert err is not None

    def test_registration_race_condition_prevention(
        self, api_client, invitation_pending_a
    ):
        """
        Test that invitation can only be claimed once (race condition protection).
        
        The serializer uses select_for_update() to prevent double claiming.
        """
        url = reverse("auth:register")
        data = {
            "email": "racetest@example.com",
            "first_name": "Race",
            "last_name": "Test",
            "password": "SecurePass123!",
            "invitation_code": "VALID-CODE-A",
        }

        # First registration should succeed
        response = api_client.post(url, data, format="json")
        assert response.status_code == status.HTTP_201_CREATED

        # Second attempt with same invitation code should fail
        data["email"] = "another@example.com"
        response = api_client.post(url, data, format="json")
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        err = _get_error_detail(response, "invitation_code")
        assert err is not None
        assert "already claimed" in str(err).lower()
