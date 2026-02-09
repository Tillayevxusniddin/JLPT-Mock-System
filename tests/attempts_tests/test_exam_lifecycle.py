import pytest
from datetime import timedelta
from django.urls import reverse
from django.utils import timezone

from tests.attempts_tests.conftest import _get_error_detail

from apps.attempts.models import Submission
from apps.attempts.services import StartExamService


@pytest.mark.django_db(transaction=True)
def test_race_condition_start_exam_creates_single_submission(student_user, exam_assignment_open):
    submission1, _ = StartExamService.start_exam(student_user, str(exam_assignment_open.id))
    submission2, _ = StartExamService.start_exam(student_user, str(exam_assignment_open.id))

    assert submission1.id == submission2.id
    assert Submission.objects.filter(
        user_id=student_user.id,
        exam_assignment=exam_assignment_open,
    ).count() == 1


@pytest.mark.django_db(transaction=True)
def test_resume_does_not_reset_started_at(student_user, exam_assignment_open):
    submission, _ = StartExamService.start_exam(student_user, str(exam_assignment_open.id))
    fixed_time = timezone.now() - timedelta(minutes=20)
    submission.started_at = fixed_time
    submission.save(update_fields=["started_at"])

    resumed, _ = StartExamService.start_exam(student_user, str(exam_assignment_open.id))
    resumed.refresh_from_db()

    assert resumed.id == submission.id
    assert resumed.started_at == fixed_time


@pytest.mark.django_db
def test_graded_submission_is_immutable(api_client_admin, graded_submission):
    url = reverse("submissions-detail", args=[graded_submission.id])
    response = api_client_admin.patch(url, {"status": Submission.Status.STARTED}, format="json")

    assert response.status_code == 400
    assert _get_error_detail(response, "detail") is not None
