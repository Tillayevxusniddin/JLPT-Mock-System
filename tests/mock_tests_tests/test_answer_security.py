import pytest
from rest_framework import status


@pytest.mark.django_db
def test_student_cannot_see_correct_answers_in_mock_test(api_client_student, full_hierarchy_published):
    mock_test = full_hierarchy_published["mock_test"]
    response = api_client_student.get(f"/api/v1/mock-tests/{mock_test.id}/")
    assert response.status_code == status.HTTP_200_OK

    sections = response.data.get("sections", [])
    assert sections
    questions = sections[0]["question_groups"][0]["questions"]
    assert questions

    for q in questions:
        assert "correct_option_index" not in q
        for opt in q.get("options", []):
            assert "is_correct" not in opt


@pytest.mark.django_db
def test_guest_cannot_see_correct_answers_in_quiz(api_client_guest, quiz_with_question):
    quiz = quiz_with_question["quiz"]
    response = api_client_guest.get(f"/api/v1/quizzes/{quiz.id}/")
    assert response.status_code == status.HTTP_200_OK

    questions = response.data.get("questions", [])
    assert questions
    for q in questions:
        assert "correct_option_index" not in q
        for opt in q.get("options", []):
            assert "is_correct" not in opt


@pytest.mark.django_db
def test_teacher_can_see_correct_answers(api_client_teacher, full_hierarchy_published):
    mock_test = full_hierarchy_published["mock_test"]
    response = api_client_teacher.get(f"/api/v1/mock-tests/{mock_test.id}/")
    assert response.status_code == status.HTTP_200_OK

    questions = response.data["sections"][0]["question_groups"][0]["questions"]
    assert "correct_option_index" in questions[0]
    assert any("is_correct" in opt for opt in questions[0].get("options", []))
