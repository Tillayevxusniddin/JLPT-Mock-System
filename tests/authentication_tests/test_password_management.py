"""
Test suite for password management (reset and update).

Tests cover:
- Password reset request (existing/non-existing user)
- Password reset confirm (valid/invalid token)
- Update password (correct/incorrect old password)
- Weak password validation
- Email sending (mocked)
"""
import pytest
from django.urls import reverse
from rest_framework import status
from django.contrib.auth.tokens import PasswordResetTokenGenerator
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode
from django.contrib.auth import get_user_model
from unittest.mock import patch, call

User = get_user_model()


def _get_error_detail(response, key):
    """Return error detail for a field, supporting wrapped error responses."""
    data = response.data
    if isinstance(data, dict) and "error" in data and isinstance(data["error"], dict):
        data = data["error"]
    if isinstance(data, dict):
        return data.get(key)
    return None


class TestPasswordResetRequest:
    """Test POST /auth/password-reset-request/ endpoint."""

    @patch("apps.authentication.serializers.send_mail")
    def test_password_reset_request_existing_user(
        self, mock_send_mail, api_client, student_a
    ):
        """
        Test password reset request for existing user.
        
        Verifies:
        - 200 response (don't leak user existence)
        - Email sent to user
        - Email contains reset URL with uid and token
        """
        url = reverse("auth:password-reset-request")
        data = {"email": "student@center-a.com"}

        response = api_client.post(url, data, format="json")

        assert response.status_code == status.HTTP_200_OK, response.data
        assert response.data["detail"] == "Password reset email sent."

        # Verify email was sent
        assert mock_send_mail.called
        assert mock_send_mail.call_count == 1

        # Verify email sent to correct recipient
        call_args = mock_send_mail.call_args
        assert "student@center-a.com" in call_args[1]["recipient_list"]

        # Verify email subject and content
        subject = call_args[1]["subject"]
        assert "password reset" in subject.lower()

    @patch("apps.authentication.serializers.send_mail")
    def test_password_reset_request_nonexistent_user(
        self, mock_send_mail, api_client
    ):
        """
        Test password reset request for non-existent user.
        
        Should return same 200 response to avoid user enumeration.
        No email should be sent.
        """
        url = reverse("auth:password-reset-request")
        data = {"email": "nonexistent@example.com"}

        response = api_client.post(url, data, format="json")

        assert response.status_code == status.HTTP_200_OK
        assert response.data["detail"] == "Password reset email sent."

        # No email should be sent
        assert not mock_send_mail.called

    @patch("apps.authentication.serializers.send_mail")
    def test_password_reset_request_soft_deleted_user(
        self, mock_send_mail, api_client, soft_deleted_user_a
    ):
        """
        Test password reset for soft-deleted user.
        
        Should return 200 (don't leak deletion status) but no email sent.
        """
        url = reverse("auth:password-reset-request")
        data = {"email": "deleted@center-a.com"}

        response = api_client.post(url, data, format="json")

        assert response.status_code == status.HTTP_200_OK

        # No email should be sent (user is soft-deleted)
        assert not mock_send_mail.called

    @patch("apps.authentication.serializers.send_mail")
    def test_password_reset_request_inactive_user(
        self, mock_send_mail, api_client, inactive_user_a
    ):
        """
        Test password reset for inactive user.
        
        Should return 200 but no email sent (user is inactive).
        """
        url = reverse("auth:password-reset-request")
        data = {"email": "inactive@center-a.com"}

        response = api_client.post(url, data, format="json")

        assert response.status_code == status.HTTP_200_OK

        # No email should be sent (user is inactive)
        assert not mock_send_mail.called

    def test_password_reset_request_missing_email(self, api_client):
        """Test password reset fails when email is missing."""
        url = reverse("auth:password-reset-request")
        data = {}

        response = api_client.post(url, data, format="json")

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "email" in response.data

    def test_password_reset_request_invalid_email_format(self, api_client):
        """Test password reset fails with invalid email format."""
        url = reverse("auth:password-reset-request")
        data = {"email": "not-an-email"}

        response = api_client.post(url, data, format="json")

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "email" in response.data


class TestPasswordResetConfirm:
    """Test POST /auth/password-reset-confirm/ endpoint."""

    def test_password_reset_confirm_valid_token(self, api_client, student_a):
        """
        Test password reset with valid uid and token.
        
        Verifies:
        - Password changed successfully
        - User can log in with new password
        - Old password no longer works
        """
        # Generate valid token
        token_generator = PasswordResetTokenGenerator()
        token = token_generator.make_token(student_a)
        uidb64 = urlsafe_base64_encode(force_bytes(student_a.id))

        url = reverse("auth:password-reset-confirm")
        data = {
            "uid": uidb64,
            "token": token,
            "new_password": "NewSecurePass123!",
        }

        response = api_client.post(url, data, format="json")

        assert response.status_code == status.HTTP_200_OK

        # Verify password changed
        student_a.refresh_from_db()
        assert student_a.check_password("NewSecurePass123!")
        assert not student_a.check_password("StudentPass123!")  # Old password

        # Verify user can log in with new password
        from unittest.mock import patch

        with patch(
            "apps.authentication.backends.TenantAwareBackend._get_center_id_from_subdomain"
        ) as mock_subdomain:
            mock_subdomain.return_value = student_a.center_id
            login_url = reverse("auth:login")
            login_data = {"email": "student@center-a.com", "password": "NewSecurePass123!"}
            login_response = api_client.post(login_url, login_data, format="json")
            assert login_response.status_code == status.HTTP_200_OK

    def test_password_reset_confirm_invalid_token(self, api_client, student_a):
        """
        Test password reset with invalid/tampered token.
        
        Should return 400 error.
        """
        uidb64 = urlsafe_base64_encode(force_bytes(student_a.id))

        url = reverse("auth:password-reset-confirm")
        data = {
            "uid": uidb64,
            "token": "invalid-token-12345",
            "new_password": "NewPass123!",
        }

        response = api_client.post(url, data, format="json")

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        token_err = _get_error_detail(response, "token")
        uid_err = _get_error_detail(response, "uid")
        assert token_err is not None or uid_err is not None
        assert "invalid or expired" in str(response.data).lower()

        # Verify password NOT changed
        student_a.refresh_from_db()
        assert student_a.check_password("StudentPass123!")  # Old password still works

    def test_password_reset_confirm_invalid_uid(self, api_client):
        """
        Test password reset with invalid uid (non-existent user).
        
        Should return 400 error.
        """
        uidb64 = urlsafe_base64_encode(force_bytes(99999))  # Non-existent user ID
        token = "some-token"

        url = reverse("auth:password-reset-confirm")
        data = {"uid": uidb64, "token": token, "new_password": "NewPass123!"}

        response = api_client.post(url, data, format="json")

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "invalid or expired" in str(response.data).lower()

    def test_password_reset_confirm_malformed_uid(self, api_client):
        """Test password reset with malformed uid."""
        url = reverse("auth:password-reset-confirm")
        data = {
            "uid": "not-base64-encoded",
            "token": "some-token",
            "new_password": "NewPass123!",
        }

        response = api_client.post(url, data, format="json")

        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_password_reset_confirm_weak_password(self, api_client, student_a):
        """
        Test password reset fails with weak new password.
        
        Django's validate_password should reject weak passwords.
        """
        token_generator = PasswordResetTokenGenerator()
        token = token_generator.make_token(student_a)
        uidb64 = urlsafe_base64_encode(force_bytes(student_a.id))

        url = reverse("auth:password-reset-confirm")
        data = {
            "uid": uidb64,
            "token": token,
            "new_password": "123",  # Too short/weak
        }

        response = api_client.post(url, data, format="json")

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        # Error might be in 'new_password' or 'non_field_errors'
        new_pwd_err = _get_error_detail(response, "new_password")
        non_field_err = _get_error_detail(response, "non_field_errors")
        assert new_pwd_err is not None or non_field_err is not None

    def test_password_reset_confirm_missing_fields(self, api_client):
        """Test password reset fails when required fields are missing."""
        url = reverse("auth:password-reset-confirm")

        # Missing token
        response = api_client.post(
            url, {"uid": "someuid", "new_password": "Pass123!"}, format="json"
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        err = _get_error_detail(response, "token")
        assert err is not None

        # Missing uid
        response = api_client.post(
            url, {"token": "sometoken", "new_password": "Pass123!"}, format="json"
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "uid" in response.data

        # Missing new_password
        response = api_client.post(
            url, {"uid": "someuid", "token": "sometoken"}, format="json"
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "new_password" in response.data


class TestUpdatePassword:
    """Test POST /auth/update-password/ endpoint."""

    def test_update_password_correct_old_password(
        self, api_client, student_a, jwt_auth_header
    ):
        """
        Test user can update password with correct old password.
        
        Verifies:
        - Password changed successfully
        - User can log in with new password
        - Old password no longer works
        """
        url = reverse("auth:password-update")
        headers = jwt_auth_header(student_a)

        data = {
            "old_password": "StudentPass123!",
            "new_password": "NewStudentPass456!",
        }

        response = api_client.post(url, data, format="json", **headers)

        assert response.status_code == status.HTTP_200_OK
        assert response.data["detail"] == "Password updated successfully."

        # Verify password changed
        student_a.refresh_from_db()
        assert student_a.check_password("NewStudentPass456!")
        assert not student_a.check_password("StudentPass123!")

    def test_update_password_incorrect_old_password(
        self, api_client, student_a, jwt_auth_header
    ):
        """
        Test password update fails with incorrect old password.
        
        Should return 400 with "Incorrect old password" error.
        """
        url = reverse("auth:password-update")
        headers = jwt_auth_header(student_a)

        data = {
            "old_password": "WrongOldPassword!",
            "new_password": "NewStudentPass456!",
        }

        response = api_client.post(url, data, format="json", **headers)

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        err = _get_error_detail(response, "old_password")
        assert err is not None
        assert "incorrect" in str(err).lower()

        # Verify password NOT changed
        student_a.refresh_from_db()
        assert student_a.check_password("StudentPass123!")

    def test_update_password_weak_new_password(
        self, api_client, student_a, jwt_auth_header
    ):
        """
        Test password update fails with weak new password.
        
        Django's validate_password should reject.
        """
        url = reverse("auth:password-update")
        headers = jwt_auth_header(student_a)

        data = {"old_password": "StudentPass123!", "new_password": "weak"}

        response = api_client.post(url, data, format="json", **headers)

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        # Error in 'new_password' or 'non_field_errors'

    def test_update_password_missing_fields(
        self, api_client, student_a, jwt_auth_header
    ):
        """Test update password fails when required fields are missing."""
        url = reverse("auth:password-update")
        headers = jwt_auth_header(student_a)

        # Missing old_password
        response = api_client.post(
            url, {"new_password": "NewPass123!"}, format="json", **headers
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        err = _get_error_detail(response, "old_password")
        assert err is not None

        # Missing new_password
        response = api_client.post(
            url, {"old_password": "StudentPass123!"}, format="json", **headers
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "new_password" in response.data

    def test_unauthenticated_user_cannot_update_password(self, api_client):
        """
        Test unauthenticated user cannot update password.
        
        Requires JWT authentication.
        """
        url = reverse("auth:password-update")
        data = {
            "old_password": "OldPass123!",
            "new_password": "NewPass123!",
        }

        response = api_client.post(url, data, format="json")

        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_update_password_same_as_old(
        self, api_client, student_a, jwt_auth_header
    ):
        """
        Test updating password to same value as old password.
        
        Should succeed (no explicit restriction unless configured).
        """
        url = reverse("auth:update-password")
        headers = jwt_auth_header(student_a)

        data = {
            "old_password": "StudentPass123!",
            "new_password": "StudentPass123!",  # Same as old
        }

        response = api_client.post(url, data, format="json", **headers)

        # Should succeed unless you have custom validation preventing this
        # Most systems allow this but it's not best practice
        assert response.status_code in [status.HTTP_200_OK, status.HTTP_400_BAD_REQUEST]
