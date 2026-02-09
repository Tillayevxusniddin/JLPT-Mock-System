import pytest
from django.test.utils import CaptureQueriesContext
from django.db import connection
from rest_framework import status


@pytest.mark.django_db
def test_mock_test_retrieve_query_count(api_client_admin, full_hierarchy):
    mock_test = full_hierarchy["mock_test"]

    with CaptureQueriesContext(connection) as ctx:
        response = api_client_admin.get(f"/api/v1/mock-tests/{mock_test.id}/")

    assert response.status_code == status.HTTP_200_OK, response.data
    # Prefetch optimization reduces N+1; threshold allows for auth/tenant overhead
    assert len(ctx) <= 12
