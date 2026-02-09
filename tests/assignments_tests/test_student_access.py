import pytest
from datetime import timedelta
from django.utils import timezone
from rest_framework import status

from apps.assignments.models import HomeworkAssignment


@pytest.mark.django_db(transaction=True)
def test_student_group_visibility(
    api_client_student_a,
    exam_assignment_a,
    exam_assignment_b,
    membership_student_a,
):
    response = api_client_student_a.get("/api/v1/exam-assignments/")
    assert response.status_code == status.HTTP_200_OK
    data = response.data.get("results") if isinstance(response.data, dict) else response.data
    ids = {item["id"] for item in data}
    assert str(exam_assignment_a.id) in ids
    assert str(exam_assignment_b.id) not in ids
    assert data[0].get("created_by") is not None

    detail = api_client_student_a.get(f"/api/v1/exam-assignments/{exam_assignment_a.id}/")
    assert detail.status_code == status.HTTP_200_OK
    assert detail.data.get("created_by") is not None


@pytest.mark.django_db(transaction=True)
def test_student_individual_assignment_visibility(
    api_client_student_b,
    student_b,
    teacher_a,
    published_mock_test,
):
    assignment = HomeworkAssignment.objects.create(
        title="Individual Homework",
        description="Assigned by user id",
        deadline=timezone.now() + timedelta(days=3),
        created_by_id=teacher_a.id,
        show_results_immediately=True,
    )
    assignment.mock_tests.set([published_mock_test.id])
    assignment.assigned_user_ids = [student_b.id]
    assignment.save(update_fields=["assigned_user_ids"])

    response = api_client_student_b.get("/api/v1/homework-assignments/")
    assert response.status_code == status.HTTP_200_OK
    data = response.data.get("results") if isinstance(response.data, dict) else response.data
    ids = {item["id"] for item in data}
    assert str(assignment.id) in ids
    assert data[0].get("created_by") is not None

    detail = api_client_student_b.get(f"/api/v1/homework-assignments/{assignment.id}/")
    assert detail.status_code == status.HTTP_200_OK
    assert detail.data.get("created_by") is not None


@pytest.mark.django_db(transaction=True)
def test_guest_only_sees_assigned_user_homework(
    api_client_guest,
    teacher_a,
    guest_user,
    published_mock_test,
    group_a,
):
    assignment = HomeworkAssignment.objects.create(
        title="Guest Homework",
        description="Assigned to guest",
        deadline=timezone.now() + timedelta(days=2),
        created_by_id=teacher_a.id,
        show_results_immediately=True,
    )
    assignment.mock_tests.set([published_mock_test.id])
    assignment.assigned_groups.set([group_a.id])
    assignment.assigned_user_ids = [guest_user.id]
    assignment.save(update_fields=["assigned_user_ids"])

    response = api_client_guest.get("/api/v1/homework-assignments/")
    assert response.status_code == status.HTTP_200_OK
    data = response.data.get("results") if isinstance(response.data, dict) else response.data
    ids = {item["id"] for item in data}
    assert str(assignment.id) in ids


@pytest.mark.django_db(transaction=True)
def test_resource_integrity_student_list_hides_unpublished_mock_test(
    api_client_student_a,
    exam_assignment_a,
    membership_student_a,
    published_mock_test,
):
    response = api_client_student_a.get("/api/v1/exam-assignments/")
    assert response.status_code == status.HTTP_200_OK
    data = response.data.get("results") if isinstance(response.data, dict) else response.data
    ids = {item["id"] for item in data}
    assert str(exam_assignment_a.id) in ids

    published_mock_test.status = published_mock_test.Status.DRAFT
    published_mock_test.save(update_fields=["status"])

    response = api_client_student_a.get("/api/v1/exam-assignments/")
    assert response.status_code == status.HTTP_200_OK
    data = response.data.get("results") if isinstance(response.data, dict) else response.data
    ids = {item["id"] for item in data}
    assert str(exam_assignment_a.id) not in ids
