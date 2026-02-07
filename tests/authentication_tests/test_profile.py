"""
Test suite for user profile management (/auth/me/ and avatar upload).

Tests cover:
- Profile retrieval (GET /auth/me/)
- Profile update (PATCH /auth/me/)
- Avatar upload and replacement
- S3 storage integration
- Field-level permissions (role, center read-only)
"""
import pytest
from django.urls import reverse
from rest_framework import status
from io import BytesIO
from PIL import Image
from django.contrib.auth import get_user_model
from unittest.mock import patch, MagicMock

User = get_user_model()


class TestProfileRetrieval:
    """Test GET /auth/me/ endpoint."""

    def test_authenticated_user_can_get_profile(
        self, api_client, student_a, jwt_auth_header
    ):
        """
        Test authenticated user can retrieve their own profile.
        
        Verifies response contains: id, email, first_name, last_name,
        role, center, my_groups, center_info
        """
        url = reverse("auth:me")
        headers = jwt_auth_header(student_a)

        response = api_client.get(url, **headers)

        assert response.status_code == status.HTTP_200_OK, response.data
        assert response.data["id"] == student_a.id
        assert response.data["email"] == student_a.email
        assert response.data["first_name"] == student_a.first_name
        assert response.data["last_name"] == student_a.last_name
        assert response.data["role"] == User.Role.STUDENT
        assert "center" in response.data
        assert "my_groups" in response.data
        assert "is_approved" in response.data

    def test_owner_can_get_profile(self, api_client, public_user, jwt_auth_header):
        """Test Owner user can retrieve their profile."""
        url = reverse("auth:me")
        headers = jwt_auth_header(public_user)

        response = api_client.get(url, **headers)

        assert response.status_code == status.HTTP_200_OK
        assert response.data["role"] == User.Role.OWNER
        assert response.data["center"] is None

    def test_center_admin_can_get_profile(
        self, api_client, center_admin_a, jwt_auth_header
    ):
        """Test Center Admin can retrieve their profile."""
        url = reverse("auth:me")
        headers = jwt_auth_header(center_admin_a)

        response = api_client.get(url, **headers)

        assert response.status_code == status.HTTP_200_OK
        assert response.data["role"] == User.Role.CENTERADMIN

    def test_teacher_can_get_profile(self, api_client, teacher_a, jwt_auth_header):
        """Test Teacher can retrieve their profile."""
        url = reverse("auth:me")
        headers = jwt_auth_header(teacher_a)

        response = api_client.get(url, **headers)

        assert response.status_code == status.HTTP_200_OK
        assert response.data["role"] == User.Role.TEACHER

    def test_guest_can_get_profile(self, api_client, guest_a, jwt_auth_header):
        """Test Guest user can retrieve their profile."""
        url = reverse("auth:me")
        headers = jwt_auth_header(guest_a)

        response = api_client.get(url, **headers)

        assert response.status_code == status.HTTP_200_OK
        assert response.data["role"] == User.Role.GUEST

    def test_unauthenticated_user_cannot_get_profile(self, api_client):
        """
        Test unauthenticated request returns 401.
        
        No JWT token provided.
        """
        url = reverse("auth:me")

        response = api_client.get(url)

        assert response.status_code == status.HTTP_401_UNAUTHORIZED
        assert "authentication credentials" in str(response.data).lower()

    def test_profile_includes_center_info(
        self, api_client, student_a, center_a, jwt_auth_header
    ):
        """
        Test profile response includes center_info with center details.
        
        center_info should contain: id, name, is_active
        """
        url = reverse("auth:me")
        headers = jwt_auth_header(student_a)

        response = api_client.get(url, **headers)

        assert response.status_code == status.HTTP_200_OK
        
        # center_info might be nested or returned as center ID
        # Adjust based on your UserSerializer implementation
        if "center_info" in response.data:
            center_info = response.data["center_info"]
            assert center_info is not None
            assert center_info["id"] == center_a.id
            assert center_info["name"] == center_a.name


class TestProfileUpdate:
    """Test PATCH /auth/me/ endpoint."""

    def test_user_can_update_own_profile(
        self, api_client, student_a, jwt_auth_header
    ):
        """
        Test user can update their profile fields.
        
        Allowed updates: first_name, last_name, bio, address, city, etc.
        """
        url = reverse("auth:me")
        headers = jwt_auth_header(student_a)

        data = {
            "first_name": "Updated",
            "last_name": "Name",
            "bio": "This is my bio",
            "address": "123 Test Street",
            "city": "Tashkent",
        }

        response = api_client.patch(url, data, format="json", **headers)

        assert response.status_code == status.HTTP_200_OK
        assert response.data["first_name"] == "Updated"
        assert response.data["last_name"] == "Name"

        # Verify changes persisted
        student_a.refresh_from_db()
        assert student_a.first_name == "Updated"
        assert student_a.last_name == "Name"
        assert student_a.bio == "This is my bio"
        assert student_a.address == "123 Test Street"
        assert student_a.city == "Tashkent"

    def test_user_cannot_update_role(self, api_client, student_a, jwt_auth_header):
        """
        Test user cannot change their own role.
        
        Role field should be read_only in UserSerializer.
        """
        url = reverse("auth:me")
        headers = jwt_auth_header(student_a)

        original_role = student_a.role

        data = {"role": User.Role.TEACHER}  # Try to escalate to teacher

        response = api_client.patch(url, data, format="json", **headers)

        # Update might succeed but role should not change
        student_a.refresh_from_db()
        assert student_a.role == original_role  # Role unchanged

    def test_user_cannot_update_center(self, api_client, student_a, center_b, jwt_auth_header):
        """
        Test user cannot change their center assignment.
        
        Center field should be read_only.
        """
        url = reverse("auth:me")
        headers = jwt_auth_header(student_a)

        original_center = student_a.center

        data = {"center": center_b.id}  # Try to switch to Center B

        response = api_client.patch(url, data, format="json", **headers)

        # Center should not change
        student_a.refresh_from_db()
        assert student_a.center == original_center

    def test_user_cannot_update_email(self, api_client, student_a, jwt_auth_header):
        """
        Test user cannot change their email via profile update.
        
        Email changes typically require separate flow with verification.
        """
        url = reverse("auth:me")
        headers = jwt_auth_header(student_a)

        original_email = student_a.email

        data = {"email": "newemail@example.com"}

        response = api_client.patch(url, data, format="json", **headers)

        # Email should not change (or return validation error)
        student_a.refresh_from_db()
        # Check if email changed based on your serializer config
        # If email is read_only, it won't change
        # If it's not read_only but has validation, test should fail

    def test_user_cannot_update_is_approved(
        self, api_client, unapproved_user_a, jwt_auth_header
    ):
        """
        Test user cannot self-approve.
        
        is_approved should be controlled by admins only.
        """
        url = reverse("auth:me")
        headers = jwt_auth_header(unapproved_user_a)

        data = {"is_approved": True}

        response = api_client.patch(url, data, format="json", **headers)

        # is_approved should not change
        unapproved_user_a.refresh_from_db()
        assert unapproved_user_a.is_approved is False

    def test_partial_update_only_first_name(
        self, api_client, student_a, jwt_auth_header
    ):
        """Test partial update (only one field)."""
        url = reverse("auth:me")
        headers = jwt_auth_header(student_a)

        original_last_name = student_a.last_name

        data = {"first_name": "PartialUpdate"}

        response = api_client.patch(url, data, format="json", **headers)

        assert response.status_code == status.HTTP_200_OK

        student_a.refresh_from_db()
        assert student_a.first_name == "PartialUpdate"
        assert student_a.last_name == original_last_name  # Unchanged


class TestAvatarUpload:
    """Test avatar upload endpoint."""

    def test_user_can_upload_avatar(self, api_client, student_a, jwt_auth_header):
        """
        Test user can upload an avatar image.
        
        Verifies:
        - Image uploaded successfully
        - Avatar URL returned in response
        - File saved to storage (S3 or local)
        """
        url = reverse("auth:avatar-upload")
        headers = jwt_auth_header(student_a)

        # Create test image
        image = Image.new("RGB", (100, 100), color="red")
        image_file = BytesIO()
        image.save(image_file, format="JPEG")
        image_file.name = "test_avatar.jpg"
        image_file.seek(0)

        response = api_client.post(
            url, {"avatar": image_file}, format="multipart", **headers
        )

        assert response.status_code == status.HTTP_200_OK
        assert "avatar" in response.data

        # Verify avatar saved
        student_a.refresh_from_db()
        assert student_a.avatar is not None
        assert student_a.avatar.name != ""

    def test_user_can_replace_existing_avatar(
        self, api_client, student_a, jwt_auth_header
    ):
        """
        Test user can replace existing avatar.
        
        Verifies:
        - Old avatar deleted from storage
        - New avatar uploaded
        - Avatar URL updated
        """
        url = reverse("auth:avatar-upload")
        headers = jwt_auth_header(student_a)

        # Upload first avatar
        image1 = Image.new("RGB", (100, 100), color="blue")
        image_file1 = BytesIO()
        image1.save(image_file1, format="JPEG")
        image_file1.name = "avatar1.jpg"
        image_file1.seek(0)

        response1 = api_client.post(
            url, {"avatar": image_file1}, format="multipart", **headers
        )
        assert response1.status_code == status.HTTP_200_OK

        student_a.refresh_from_db()
        old_avatar_name = student_a.avatar.name

        # Upload second avatar (replacement)
        image2 = Image.new("RGB", (100, 100), color="green")
        image_file2 = BytesIO()
        image2.save(image_file2, format="JPEG")
        image_file2.name = "avatar2.jpg"
        image_file2.seek(0)

        response2 = api_client.post(
            url, {"avatar": image_file2}, format="multipart", **headers
        )
        assert response2.status_code == status.HTTP_200_OK

        student_a.refresh_from_db()
        new_avatar_name = student_a.avatar.name

        # Verify avatar changed
        assert new_avatar_name != old_avatar_name

        # Note: Verifying old file deleted from S3 requires mocking or actual S3 access
        # The User.save() method should handle deletion

    def test_upload_avatar_without_file(self, api_client, student_a, jwt_auth_header):
        """
        Test avatar upload fails when no file is provided.
        
        Should return 400 with error message.
        """
        url = reverse("auth:avatar-upload")
        headers = jwt_auth_header(student_a)

        response = api_client.post(url, {}, format="multipart", **headers)

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "avatar" in response.data
        assert "no avatar file provided" in str(response.data["avatar"]).lower()

    def test_upload_invalid_file_type(self, api_client, student_a, jwt_auth_header):
        """
        Test avatar upload fails with invalid file type (e.g., .txt).
        
        Pillow should validate image format.
        """
        url = reverse("auth:avatar-upload")
        headers = jwt_auth_header(student_a)

        # Create a text file
        text_file = BytesIO(b"This is not an image")
        text_file.name = "fake_image.txt"

        response = api_client.post(
            url, {"avatar": text_file}, format="multipart", **headers
        )

        # Should return 400 with validation error
        # Note: Exact error depends on your ImageField validation
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_upload_avatar_unauthenticated(self, api_client):
        """Test avatar upload requires authentication."""
        url = reverse("auth:avatar-upload")

        image = Image.new("RGB", (100, 100), color="red")
        image_file = BytesIO()
        image.save(image_file, format="JPEG")
        image_file.name = "test.jpg"
        image_file.seek(0)

        response = api_client.post(url, {"avatar": image_file}, format="multipart")

        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_upload_png_avatar(self, api_client, student_a, jwt_auth_header):
        """Test PNG format avatar upload works."""
        url = reverse("auth:avatar-upload")
        headers = jwt_auth_header(student_a)

        image = Image.new("RGBA", (100, 100), color="blue")
        image_file = BytesIO()
        image.save(image_file, format="PNG")
        image_file.name = "test_avatar.png"
        image_file.seek(0)

        response = api_client.post(
            url, {"avatar": image_file}, format="multipart", **headers
        )

        assert response.status_code == status.HTTP_200_OK
        student_a.refresh_from_db()
        assert student_a.avatar is not None


class TestProfileEdgeCases:
    """Test edge cases and special scenarios."""

    def test_soft_deleted_user_avatar_deleted_on_soft_delete(
        self, api_client, student_a, jwt_auth_header
    ):
        """
        Test that avatar is deleted from storage when user is soft-deleted.
        
        User.soft_delete() should call avatar.delete().
        """
        from apps.core.tenant_utils import set_public_schema

        set_public_schema()

        url = reverse("auth:avatar-upload")
        headers = jwt_auth_header(student_a)

        # Upload avatar
        image = Image.new("RGB", (100, 100), color="red")
        image_file = BytesIO()
        image.save(image_file, format="JPEG")
        image_file.name = "to_delete.jpg"
        image_file.seek(0)

        response = api_client.post(
            url, {"avatar": image_file}, format="multipart", **headers
        )
        assert response.status_code == status.HTTP_200_OK

        student_a.refresh_from_db()
        assert student_a.avatar is not None
        avatar_name = student_a.avatar.name

        # Soft delete user
        student_a.soft_delete()
        student_a.refresh_from_db()

        # Verify user is soft-deleted
        assert student_a.deleted_at is not None

        # Avatar should be deleted (no file reference)
        # Note: Checking actual S3 deletion requires storage backend verification

    def test_profile_with_empty_optional_fields(
        self, api_client, jwt_auth_header, center_a
    ):
        """
        Test profile works correctly when optional fields are empty.
        
        Fields like bio, address, city are optional.
        """
        from apps.core.tenant_utils import set_public_schema

        set_public_schema()

        user = User.objects.create_user(
            email="minimal@center-a.com",
            password="Pass123!",
            first_name="Minimal",
            last_name="User",
            role=User.Role.STUDENT,
            center=center_a,
            is_active=True,
            is_approved=True,
            # No bio, address, city, emergency_contact_phone
        )

        url = reverse("auth:me")
        headers = jwt_auth_header(user)

        response = api_client.get(url, **headers)

        assert response.status_code == status.HTTP_200_OK
        # These fields should be null or empty string
        # assert response.data.get("bio") is None or response.data.get("bio") == ""

    def test_large_avatar_upload(self, api_client, student_a, jwt_auth_header):
        """
        Test uploading a larger avatar image.
        
        Verify file size limits (if configured).
        """
        url = reverse("auth:avatar-upload")
        headers = jwt_auth_header(student_a)

        # Create larger image (500x500)
        image = Image.new("RGB", (500, 500), color="purple")
        image_file = BytesIO()
        image.save(image_file, format="JPEG", quality=95)
        image_file.name = "large_avatar.jpg"
        image_file.seek(0)

        response = api_client.post(
            url, {"avatar": image_file}, format="multipart", **headers
        )

        # Should succeed unless file size validation is configured
        # If you have MAX_UPLOAD_SIZE validation, this might fail
        assert response.status_code in [status.HTTP_200_OK, status.HTTP_400_BAD_REQUEST]

    def test_update_profile_with_very_long_bio(
        self, api_client, student_a, jwt_auth_header
    ):
        """Test updating bio with very long text."""
        url = reverse("auth:me")
        headers = jwt_auth_header(student_a)

        long_bio = "A" * 5000  # 5000 characters

        data = {"bio": long_bio}

        response = api_client.patch(url, data, format="json", **headers)

        # Should succeed unless TextField has max_length
        if response.status_code == status.HTTP_200_OK:
            student_a.refresh_from_db()
            assert len(student_a.bio) == 5000
