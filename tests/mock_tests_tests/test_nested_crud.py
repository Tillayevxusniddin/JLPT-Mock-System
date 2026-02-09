import pytest
from rest_framework import status

from apps.mock_tests.models import Question


@pytest.mark.django_db
def test_create_section_and_question(api_client_teacher, draft_mock_test, options_payload):
    section_response = api_client_teacher.post(
        "/api/v1/test-sections/",
        {
            "mock_test": str(draft_mock_test.id),
            "name": "Grammar",
            "section_type": "GRAMMAR_READING",
            "duration": 40,
            "order": 1,
            "total_score": 0,
        },
        format="json",
    )
    assert section_response.status_code == status.HTTP_201_CREATED
    section_id = section_response.data["id"]

    group_response = api_client_teacher.post(
        "/api/v1/question-groups/",
        {
            "section": section_id,
            "mondai_number": 1,
            "title": "Group 1",
            "instruction": "Pick one",
            "order": 1,
        },
        format="json",
    )
    assert group_response.status_code == status.HTTP_201_CREATED
    group_id = group_response.data["id"]

    question_response = api_client_teacher.post(
        "/api/v1/questions/",
        {
            "group": group_id,
            "text": "Question?",
            "question_number": 1,
            "score": 2,
            "order": 1,
            "options": options_payload,
        },
        format="json",
    )
    assert question_response.status_code == status.HTTP_201_CREATED
    assert question_response.data["correct_option_index"] == 1


@pytest.mark.django_db
def test_update_question_score_recalculates(api_client_teacher, full_hierarchy_teacher):
    question = full_hierarchy_teacher["questions"][0]
    response = api_client_teacher.patch(
        f"/api/v1/questions/{question.id}/",
        {"score": 5, "options": question.options},
        format="json",
    )
    assert response.status_code == status.HTTP_200_OK
    question.refresh_from_db()
    assert question.score == 5


@pytest.mark.django_db
def test_delete_question(api_client_teacher, full_hierarchy_teacher):
    question = full_hierarchy_teacher["questions"][0]
    response = api_client_teacher.delete(f"/api/v1/questions/{question.id}/")
    assert response.status_code == status.HTTP_204_NO_CONTENT
    assert not Question.objects.filter(id=question.id).exists()
