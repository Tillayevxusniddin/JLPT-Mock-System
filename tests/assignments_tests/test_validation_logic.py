import pytest
from datetime import timedelta
from django.utils import timezone
from rest_framework import status

from .conftest import _get_error_detail


@pytest.mark.django_db(transaction=True)
def test_draft_mock_test_rejected_for_exam(
    api_client_teacher_a,
    group_a,
    membership_teacher_a,
    draft_mock_test,
):
    payload = {
        "title": "Draft Exam",
        "description": "Should fail",
        "mock_test": str(draft_mock_test.id),
        "status": "CLOSED",
        "assigned_group_ids": [str(group_a.id)],
    }
    response = api_client_teacher_a.post("/api/v1/exam-assignments/", payload, format="json")
    assert response.status_code == status.HTTP_400_BAD_REQUEST
    err = _get_error_detail(response, "mock_test") or _get_error_detail(response, "detail")
    assert err is not None


@pytest.mark.django_db(transaction=True)
def test_homework_past_deadline_rejected(
    api_client_teacher_a,
    group_a,
    membership_teacher_a,
    published_mock_test,
):
    payload = {
        "title": "Past Homework",
        "description": "Past deadline",
        "deadline": (timezone.now() - timedelta(days=1)).isoformat(),
        "mock_test_ids": [str(published_mock_test.id)],
        "assigned_group_ids": [str(group_a.id)],
        "assigned_user_ids": [],
        "show_results_immediately": True,
    }
    response = api_client_teacher_a.post("/api/v1/homework-assignments/", payload, format="json")
    assert response.status_code == status.HTTP_400_BAD_REQUEST
    err = _get_error_detail(response, "deadline")
    assert err is not None


@pytest.mark.django_db(transaction=True)
def test_cross_tenant_user_rejected(
    api_client_teacher_a,
    group_a,
    membership_teacher_a,
    published_mock_test,
    foreign_student,
):
    payload = {
        "title": "Cross Tenant Homework",
        "description": "Foreign user",
        "deadline": (timezone.now() + timedelta(days=2)).isoformat(),
        "mock_test_ids": [str(published_mock_test.id)],
        "assigned_group_ids": [str(group_a.id)],
        "assigned_user_ids": [foreign_student.id],
        "show_results_immediately": True,
    }
    response = api_client_teacher_a.post("/api/v1/homework-assignments/", payload, format="json")
    assert response.status_code == status.HTTP_400_BAD_REQUEST
    err = _get_error_detail(response, "assigned_user_ids")
    assert err is not None
