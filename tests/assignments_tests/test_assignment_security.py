import pytest
from rest_framework import status

from .conftest import _get_error_detail


@pytest.mark.django_db(transaction=True)
def test_teacher_boundary_cannot_assign_other_group(
    api_client_teacher_a,
    group_b,
    published_mock_test,
):
    payload = {
        "title": "Exam Boundary",
        "description": "Teacher A tries Group B",
        "mock_test": str(published_mock_test.id),
        "status": "CLOSED",
        "assigned_group_ids": [str(group_b.id)],
    }
    response = api_client_teacher_a.post("/api/v1/exam-assignments/", payload, format="json")
    assert response.status_code == status.HTTP_400_BAD_REQUEST
    err = _get_error_detail(response, "assigned_group_ids")
    assert err is not None


@pytest.mark.django_db(transaction=True)
def test_teacher_cannot_edit_or_delete_assignment_of_other_teacher(
    api_client_teacher_a,
    exam_assignment_b,
):
    patch_response = api_client_teacher_a.patch(
        f"/api/v1/exam-assignments/{exam_assignment_b.id}/",
        {"title": "Unauthorized Update"},
        format="json",
    )
    assert patch_response.status_code == status.HTTP_404_NOT_FOUND

    delete_response = api_client_teacher_a.delete(
        f"/api/v1/exam-assignments/{exam_assignment_b.id}/"
    )
    assert delete_response.status_code == status.HTTP_404_NOT_FOUND


@pytest.mark.django_db(transaction=True)
def test_center_admin_can_manage_all_assignments(
    api_client_admin,
    exam_assignment_b,
    published_mock_test,
):
    patch_response = api_client_admin.patch(
        f"/api/v1/exam-assignments/{exam_assignment_b.id}/",
        {
            "title": "Admin Update",
            "description": "Updated by admin",
            "mock_test": str(published_mock_test.id),
            "status": "OPEN",
            "assigned_group_ids": [str(exam_assignment_b.assigned_groups.first().id)],
        },
        format="json",
    )
    assert patch_response.status_code == status.HTTP_200_OK

    delete_response = api_client_admin.delete(
        f"/api/v1/exam-assignments/{exam_assignment_b.id}/"
    )
    assert delete_response.status_code == status.HTTP_204_NO_CONTENT
