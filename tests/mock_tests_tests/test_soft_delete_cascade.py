import pytest
from rest_framework import status

from apps.mock_tests.models import MockTest, TestSection, QuestionGroup, Question


@pytest.mark.django_db(transaction=True)
def test_soft_delete_cascades_to_children(api_client_admin, full_hierarchy):
    mock_test = full_hierarchy["mock_test"]
    response = api_client_admin.delete(f"/api/v1/mock-tests/{mock_test.id}/")
    assert response.status_code == status.HTTP_204_NO_CONTENT

    assert MockTest.all_objects.filter(id=mock_test.id, deleted_at__isnull=False).exists()
    assert TestSection.all_objects.filter(mock_test=mock_test, deleted_at__isnull=False).exists()
    assert QuestionGroup.all_objects.filter(section__mock_test=mock_test, deleted_at__isnull=False).exists()
    assert Question.all_objects.filter(group__section__mock_test=mock_test, deleted_at__isnull=False).exists()
