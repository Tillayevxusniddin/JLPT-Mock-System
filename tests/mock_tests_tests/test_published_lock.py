import pytest
from rest_framework import status

from apps.mock_tests.models import TestSection, QuestionGroup, Question
from .conftest import _get_error_detail


@pytest.mark.django_db
def test_update_published_mock_test_blocked(api_client_admin, published_mock_test):
    response = api_client_admin.patch(
        f"/api/v1/mock-tests/{published_mock_test.id}/",
        {"title": "New Title"},
        format="json",
    )
    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert "Cannot modify a published test" in str(_get_error_detail(response))


@pytest.mark.django_db
def test_create_section_for_published_mock_test_blocked(api_client_admin, published_mock_test):
    response = api_client_admin.post(
        "/api/v1/test-sections/",
        {
            "mock_test": str(published_mock_test.id),
            "name": "Blocked",
            "section_type": "VOCAB",
            "duration": 20,
            "order": 1,
            "total_score": 0,
        },
        format="json",
    )
    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert "Cannot modify a published test" in str(_get_error_detail(response))


@pytest.mark.django_db
def test_update_child_of_published_mock_test_blocked(api_client_admin, published_mock_test, options_payload):
    section = TestSection.objects.create(
        mock_test=published_mock_test,
        name="Section",
        section_type=TestSection.SectionType.VOCAB,
        duration=20,
        order=1,
        total_score=0,
    )
    group = QuestionGroup.objects.create(
        section=section,
        mondai_number=1,
        title="Group",
        instruction="",
        order=1,
    )
    question = Question.objects.create(
        group=group,
        text="Q",
        question_number=1,
        score=1,
        order=1,
        options=options_payload,
        correct_option_index=1,
    )

    response = api_client_admin.patch(
        f"/api/v1/questions/{question.id}/",
        {"text": "Updated", "options": options_payload},
        format="json",
    )
    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert "Cannot modify a published test" in str(_get_error_detail(response))
