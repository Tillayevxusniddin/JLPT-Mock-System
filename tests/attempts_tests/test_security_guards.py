import pytest
from django.urls import reverse

from apps.attempts.models import Submission


@pytest.mark.django_db(transaction=True)
def test_cross_center_submission_blocked(api_client_foreign, foreign_student, exam_assignment_open, mock_test_n4):
    submission = Submission.objects.create(
        user_id=foreign_student.id,
        exam_assignment=exam_assignment_open,
        status=Submission.Status.STARTED,
    )

    answers = {str(q.id): q.correct_option_index for q in (
        mock_test_n4["questions"]["vocab"] +
        mock_test_n4["questions"]["grammar_reading"] +
        mock_test_n4["questions"]["listening"]
    )[:1]}

    url = reverse("submissions-submit-exam")
    response = api_client_foreign.post(url, {"submission_id": str(submission.id), "answers": answers}, format="json")

    assert response.status_code == 403


@pytest.mark.django_db
def test_start_exam_does_not_expose_correct_answers(api_client_student, exam_assignment_open):
    url = reverse("submissions-start-exam")
    response = api_client_student.post(url, {"exam_assignment_id": str(exam_assignment_open.id)}, format="json")

    assert response.status_code == 201
    exam_paper = response.data.get("exam_paper") or {}
    sections = exam_paper.get("sections", [])
    for section in sections:
        for group in section.get("question_groups", []):
            for question in group.get("questions", []):
                assert "correct_option_index" not in question
                for option in question.get("options", []):
                    assert "is_correct" not in option
