"""
Test suite for role-based permissions and access control.

Tests cover:
- UserViewSet LIST permissions (admin/teacher/student)
- UserViewSet CREATE permissions (admin only)
- UserViewSet UPDATE/DELETE permissions
- Cross-role permission boundaries
- Teacher limited to viewing students in their groups
"""
import pytest
from django.urls import reverse
from rest_framework import status
from django.contrib.auth import get_user_model

User = get_user_model()


class TestUserViewSetListPermissions:
    """Test GET /api/v1/users/ permissions."""

    def test_center_admin_can_list_all_users_in_center(
        self, api_client, center_admin_a, student_a, teacher_a, jwt_auth_header
    ):
        """
        Test Center Admin can list all users in their center.
        
        Should see all students, teachers, and other admins in their center.
        """
        url = reverse("user-list")
        headers = jwt_auth_header(center_admin_a)

        response = api_client.get(url, **headers)

        assert response.status_code == status.HTTP_200_OK
        
        # Response might be paginated
        if "results" in response.data:
            users = response.data["results"]
        else:
            users = response.data

        # Should include users from same center
        user_ids = [u["id"] for u in users]
        assert student_a.id in user_ids
        assert teacher_a.id in user_ids

    def test_center_admin_cannot_see_users_from_other_center(
        self, api_client, center_admin_a, student_b, jwt_auth_header
    ):
        """
        Test Center Admin A cannot see users from Center B.
        
        Verifies multi-tenant isolation.
        """
        url = reverse("user-list")
        headers = jwt_auth_header(center_admin_a)

        response = api_client.get(url, **headers)

        assert response.status_code == status.HTTP_200_OK

        if "results" in response.data:
            users = response.data["results"]
        else:
            users = response.data

        # Should NOT include student_b (from Center B)
        user_ids = [u["id"] for u in users]
        assert student_b.id not in user_ids

    def test_teacher_can_list_students_in_their_groups(
        self, api_client, teacher_a, jwt_auth_header
    ):
        """
        Test Teacher can list students in their teaching groups.
        
        Note: This requires GroupMembership data in tenant schema.
        If no groups exist, teacher should see empty list.
        """
        url = reverse("user-list")
        headers = jwt_auth_header(teacher_a)

        response = api_client.get(url, **headers)

        assert response.status_code == status.HTTP_200_OK

        # Without GroupMembership data, teacher sees no students
        # This test validates the endpoint works, not the data

    def test_student_cannot_list_users(
        self, api_client, student_a, jwt_auth_header
    ):
        """
        Test Student cannot access user list endpoint.
        
        Should return 403 Forbidden.
        """
        url = reverse("user-list")
        headers = jwt_auth_header(student_a)

        response = api_client.get(url, **headers)

        assert response.status_code == status.HTTP_403_FORBIDDEN
        assert (
            "only center admins or teachers" in str(response.data).lower()
            or "permission denied" in str(response.data).lower()
        )

    def test_guest_cannot_list_users(self, api_client, guest_a, jwt_auth_header):
        """Test Guest user cannot access user list."""
        url = reverse("user-list")
        headers = jwt_auth_header(guest_a)

        response = api_client.get(url, **headers)

        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_owner_cannot_list_users_without_center(
        self, api_client, public_user, jwt_auth_header
    ):
        """
        Test Owner (center=None) sees empty user list.
        
        Owner doesn't belong to a center, so queryset is empty.
        """
        url = reverse("user-list")
        headers = jwt_auth_header(public_user)

        response = api_client.get(url, **headers)

        # Might return 200 with empty list or 403 depending on implementation
        if response.status_code == status.HTTP_200_OK:
            if "results" in response.data:
                assert len(response.data["results"]) == 0
            else:
                assert len(response.data) == 0

    def test_unauthenticated_cannot_list_users(self, api_client):
        """Test unauthenticated request returns 401."""
        url = reverse("user-list")

        response = api_client.get(url)

        assert response.status_code == status.HTTP_401_UNAUTHORIZED


class TestUserViewSetCreatePermissions:
    """Test POST /api/v1/users/ permissions."""

    def test_center_admin_can_create_user(
        self, api_client, center_admin_a, center_a, jwt_auth_header
    ):
        """
        Test Center Admin can create new users in their center.
        
        Created user should have admin's center_id.
        """
        url = reverse("user-list")
        headers = jwt_auth_header(center_admin_a)

        data = {
            "email": "newteacher@center-a.com",
            "first_name": "New",
            "last_name": "Teacher",
            "password": "TeacherPass123!",
            "role": "TEACHER",
        }

        response = api_client.post(url, data, format="json", **headers)

        assert response.status_code == status.HTTP_201_CREATED
        assert response.data["email"] == "newteacher@center-a.com"

        # Verify user created with admin's center
        user = User.objects.get(email="newteacher@center-a.com")
        assert user.center == center_a
        assert user.role == User.Role.TEACHER
        assert user.is_approved is True  # Admin-created users auto-approved

    def test_center_admin_can_create_student(
        self, api_client, center_admin_a, jwt_auth_header
    ):
        """Test Center Admin can create student users."""
        url = reverse("user-list")
        headers = jwt_auth_header(center_admin_a)

        data = {
            "email": "newstudent@center-a.com",
            "first_name": "New",
            "last_name": "Student",
            "password": "StudentPass123!",
            "role": "STUDENT",
        }

        response = api_client.post(url, data, format="json", **headers)

        assert response.status_code == status.HTTP_201_CREATED

        user = User.objects.get(email="newstudent@center-a.com")
        assert user.role == User.Role.STUDENT

    def test_teacher_cannot_create_user(
        self, api_client, teacher_a, jwt_auth_header
    ):
        """
        Test Teacher cannot create users.
        
        Teachers are only allowed to view students (read-only).
        """
        url = reverse("user-list")
        headers = jwt_auth_header(teacher_a)

        data = {
            "email": "shouldfail@center-a.com",
            "first_name": "Should",
            "last_name": "Fail",
            "password": "Pass123!",
            "role": "STUDENT",
        }

        response = api_client.post(url, data, format="json", **headers)

        assert response.status_code == status.HTTP_403_FORBIDDEN
        assert (
            "teachers are only allowed to view" in str(response.data).lower()
            or "permission denied" in str(response.data).lower()
        )

        # Verify user NOT created
        assert not User.objects.filter(email="shouldfail@center-a.com").exists()

    def test_student_cannot_create_user(
        self, api_client, student_a, jwt_auth_header
    ):
        """Test Student cannot create users."""
        url = reverse("user-list")
        headers = jwt_auth_header(student_a)

        data = {
            "email": "shouldfail@center-a.com",
            "first_name": "Should",
            "last_name": "Fail",
            "password": "Pass123!",
            "role": "STUDENT",
        }

        response = api_client.post(url, data, format="json", **headers)

        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_center_admin_cannot_create_duplicate_email(
        self, api_client, center_admin_a, student_a, jwt_auth_header
    ):
        """
        Test Center Admin cannot create user with duplicate email in same center.
        
        Email uniqueness per center enforced.
        """
        url = reverse("user-list")
        headers = jwt_auth_header(center_admin_a)

        data = {
            "email": "student@center-a.com",  # Already exists
            "first_name": "Duplicate",
            "last_name": "Student",
            "password": "Pass123!",
            "role": "STUDENT",
        }

        response = api_client.post(url, data, format="json", **headers)

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "email" in response.data
        assert "already exists" in str(response.data["email"]).lower()


class TestUserViewSetUpdatePermissions:
    """Test PUT/PATCH /api/v1/users/{id}/ permissions."""

    def test_center_admin_can_update_user_is_active(
        self, api_client, center_admin_a, student_a, jwt_auth_header
    ):
        """
        Test Center Admin can update user's is_active field.
        
        Can activate or deactivate users in their center.
        """
        url = reverse("user-detail", kwargs={"pk": student_a.id})
        headers = jwt_auth_header(center_admin_a)

        data = {"is_active": False}

        response = api_client.patch(url, data, format="json", **headers)

        assert response.status_code == status.HTTP_200_OK

        student_a.refresh_from_db()
        assert student_a.is_active is False

    def test_center_admin_can_update_user_is_approved(
        self, api_client, center_admin_a, unapproved_user_a, jwt_auth_header
    ):
        """
        Test Center Admin can approve pending users.
        
        is_approved field can be toggled.
        """
        url = reverse("user-detail", kwargs={"pk": unapproved_user_a.id})
        headers = jwt_auth_header(center_admin_a)

        data = {"is_approved": True}

        response = api_client.patch(url, data, format="json", **headers)

        assert response.status_code == status.HTTP_200_OK

        unapproved_user_a.refresh_from_db()
        assert unapproved_user_a.is_approved is True

    def test_center_admin_cannot_update_user_role(
        self, api_client, center_admin_a, student_a, jwt_auth_header
    ):
        """
        Test Center Admin cannot change user's role.
        
        Role field should be read_only in UserManagementSerializer.
        """
        url = reverse("user-detail", kwargs={"pk": student_a.id})
        headers = jwt_auth_header(center_admin_a)

        original_role = student_a.role

        data = {"role": User.Role.TEACHER}  # Try to escalate to teacher

        response = api_client.patch(url, data, format="json", **headers)

        # Update might succeed but role should not change
        student_a.refresh_from_db()
        assert student_a.role == original_role

    def test_center_admin_cannot_update_user_in_other_center(
        self, api_client, center_admin_a, student_b, jwt_auth_header
    ):
        """
        Test Center Admin A cannot update users in Center B.
        
        Should return 404 (user not in queryset).
        """
        url = reverse("user-detail", kwargs={"pk": student_b.id})
        headers = jwt_auth_header(center_admin_a)

        data = {"is_active": False}

        response = api_client.patch(url, data, format="json", **headers)

        assert response.status_code == status.HTTP_404_NOT_FOUND

        # Verify student_b NOT modified
        student_b.refresh_from_db()
        assert student_b.is_active is True

    def test_teacher_cannot_update_user(
        self, api_client, teacher_a, student_a, jwt_auth_header
    ):
        """
        Test Teacher cannot update users.
        
        Teachers have read-only access.
        """
        url = reverse("user-detail", kwargs={"pk": student_a.id})
        headers = jwt_auth_header(teacher_a)

        data = {"is_active": False}

        response = api_client.patch(url, data, format="json", **headers)

        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_student_cannot_update_other_user(
        self, api_client, student_a, student_b, jwt_auth_header
    ):
        """Test Student cannot update other users."""
        url = reverse("user-detail", kwargs={"pk": student_b.id})
        headers = jwt_auth_header(student_a)

        data = {"is_active": False}

        response = api_client.patch(url, data, format="json", **headers)

        assert response.status_code == status.HTTP_403_FORBIDDEN


class TestUserViewSetDeletePermissions:
    """Test DELETE /api/v1/users/{id}/ permissions."""

    def test_center_admin_can_soft_delete_user(
        self, api_client, center_admin_a, jwt_auth_header, center_a
    ):
        """
        Test Center Admin can soft delete users.
        
        Soft delete sets deleted_at timestamp.
        """
        from apps.core.tenant_utils import set_public_schema

        set_public_schema()

        # Create a user to delete
        user_to_delete = User.objects.create_user(
            email="todelete@center-a.com",
            password="Pass123!",
            first_name="To",
            last_name="Delete",
            role=User.Role.STUDENT,
            center=center_a,
            is_active=True,
            is_approved=True,
        )

        url = reverse("user-detail", kwargs={"pk": user_to_delete.id})
        headers = jwt_auth_header(center_admin_a)

        response = api_client.delete(url, **headers)

        assert response.status_code == status.HTTP_204_NO_CONTENT

        # Verify user soft-deleted
        user_to_delete.refresh_from_db()
        assert user_to_delete.deleted_at is not None

    def test_center_admin_cannot_delete_user_from_other_center(
        self, api_client, center_admin_a, student_b, jwt_auth_header
    ):
        """
        Test Center Admin A cannot delete users from Center B.
        
        Should return 404.
        """
        url = reverse("user-detail", kwargs={"pk": student_b.id})
        headers = jwt_auth_header(center_admin_a)

        response = api_client.delete(url, **headers)

        assert response.status_code == status.HTTP_404_NOT_FOUND

        # Verify student_b NOT deleted
        student_b.refresh_from_db()
        assert student_b.deleted_at is None

    def test_teacher_cannot_delete_user(
        self, api_client, teacher_a, student_a, jwt_auth_header
    ):
        """Test Teacher cannot delete users."""
        url = reverse("user-detail", kwargs={"pk": student_a.id})
        headers = jwt_auth_header(teacher_a)

        response = api_client.delete(url, **headers)

        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_student_cannot_delete_user(
        self, api_client, student_a, jwt_auth_header, center_a
    ):
        """Test Student cannot delete users."""
        from apps.core.tenant_utils import set_public_schema

        set_public_schema()

        other_student = User.objects.create_user(
            email="other@center-a.com",
            password="Pass123!",
            first_name="Other",
            last_name="Student",
            role=User.Role.STUDENT,
            center=center_a,
            is_active=True,
            is_approved=True,
        )

        url = reverse("user-detail", kwargs={"pk": other_student.id})
        headers = jwt_auth_header(student_a)

        response = api_client.delete(url, **headers)

        assert response.status_code == status.HTTP_403_FORBIDDEN


class TestCrossRolePermissions:
    """Test permission boundaries across different roles."""

    def test_student_cannot_access_teacher_only_endpoints(
        self, api_client, student_a, jwt_auth_header
    ):
        """
        Test Student cannot access teacher-only views.
        
        If you have specific teacher-only endpoints, test them here.
        """
        # Example: If you have a teacher-specific endpoint
        # url = reverse("teacher-specific-view")
        # headers = jwt_auth_header(student_a)
        # response = api_client.get(url, **headers)
        # assert response.status_code == status.HTTP_403_FORBIDDEN
        pass  # Placeholder - add teacher-specific endpoint tests

    def test_teacher_has_read_only_access_to_user_list(
        self, api_client, teacher_a, jwt_auth_header
    ):
        """
        Test Teacher can only READ (list, retrieve) users, not create/update/delete.
        
        Already tested above, but consolidated here for clarity.
        """
        # List - should work
        url = reverse("user-list")
        headers = jwt_auth_header(teacher_a)
        response = api_client.get(url, **headers)
        assert response.status_code == status.HTTP_200_OK

        # Create - should fail
        create_data = {
            "email": "new@center-a.com",
            "first_name": "New",
            "last_name": "User",
            "password": "Pass123!",
            "role": "STUDENT",
        }
        response = api_client.post(url, create_data, format="json", **headers)
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_owner_access_patterns(self, api_client, public_user, jwt_auth_header):
        """
        Test Owner role access patterns.
        
        Owner can access owner-specific endpoints but not center-specific ones.
        """
        # Owner accessing user list (no center) - should return empty
        url = reverse("user-list")
        headers = jwt_auth_header(public_user)
        response = api_client.get(url, **headers)
        
        # Depending on implementation, might be 200 with empty list
        # or 403 if owner needs a center
        assert response.status_code in [
            status.HTTP_200_OK,
            status.HTTP_403_FORBIDDEN,
        ]
