import pytest
from rest_framework import status

from apps.mock_tests.models import MockTest, TestSection, QuestionGroup, Question


@pytest.mark.django_db(transaction=True)
def test_clone_creates_deep_copy(api_client_teacher, full_hierarchy_teacher):
    source = full_hierarchy_teacher["mock_test"]
    response = api_client_teacher.post(f"/api/v1/mock-tests/{source.id}/clone/")
    assert response.status_code == status.HTTP_201_CREATED

    cloned_id = response.data["id"]
    assert str(source.id) != cloned_id

    cloned = MockTest.objects.get(id=cloned_id)
    assert cloned.status == MockTest.Status.DRAFT

    source_sections = list(TestSection.objects.filter(mock_test=source))
    cloned_sections = list(TestSection.objects.filter(mock_test=cloned))
    assert len(source_sections) == len(cloned_sections)
    assert {s.id for s in source_sections}.isdisjoint({s.id for s in cloned_sections})

    source_groups = list(QuestionGroup.objects.filter(section__mock_test=source))
    cloned_groups = list(QuestionGroup.objects.filter(section__mock_test=cloned))
    assert len(source_groups) == len(cloned_groups)
    assert {g.id for g in source_groups}.isdisjoint({g.id for g in cloned_groups})

    source_questions = list(Question.objects.filter(group__section__mock_test=source))
    cloned_questions = list(Question.objects.filter(group__section__mock_test=cloned))
    assert len(source_questions) == len(cloned_questions)
    assert {q.id for q in source_questions}.isdisjoint({q.id for q in cloned_questions})
