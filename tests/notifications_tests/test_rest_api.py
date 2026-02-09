import pytest
from django.urls import reverse

from apps.notifications.models import Notification
from tests.notifications_tests.conftest import _get_error_detail


@pytest.mark.django_db
def test_is_read_filter(api_client_approved, tenant_schema, approved_student):
    Notification.objects.create(
        user_id=approved_student.id,
        notification_type=Notification.NotificationType.ANNOUNCEMENT,
        message="Unread",
        is_read=False,
    )
    Notification.objects.create(
        user_id=approved_student.id,
        notification_type=Notification.NotificationType.ANNOUNCEMENT,
        message="Read",
        is_read=True,
    )

    url = reverse("notifications-list")
    resp_unread = api_client_approved.get(url, {"is_read": "false"})
    resp_read = api_client_approved.get(url, {"is_read": "true"})

    assert resp_unread.status_code == 200
    assert resp_read.status_code == 200
    # Handle paginated response
    unread_results = resp_unread.data.get("results", resp_unread.data) if isinstance(resp_unread.data, dict) else resp_unread.data
    read_results = resp_read.data.get("results", resp_read.data) if isinstance(resp_read.data, dict) else resp_read.data
    assert all(item["is_read"] is False for item in unread_results)
    assert all(item["is_read"] is True for item in read_results)


@pytest.mark.django_db
def test_mark_all_read_only_updates_current_user(api_client_approved, tenant_schema, approved_student, unapproved_student):
    Notification.objects.create(
        user_id=approved_student.id,
        notification_type=Notification.NotificationType.ANNOUNCEMENT,
        message="A1",
        is_read=False,
    )
    Notification.objects.create(
        user_id=approved_student.id,
        notification_type=Notification.NotificationType.ANNOUNCEMENT,
        message="A2",
        is_read=False,
    )
    Notification.objects.create(
        user_id=unapproved_student.id,
        notification_type=Notification.NotificationType.ANNOUNCEMENT,
        message="B1",
        is_read=False,
    )

    url = reverse("notifications-mark-all-read")
    response = api_client_approved.post(url)

    assert response.status_code == 200
    assert response.data.get("updated") == 2
    assert Notification.objects.filter(user_id=approved_student.id, is_read=False).count() == 0
    assert Notification.objects.filter(user_id=unapproved_student.id, is_read=False).count() == 1


@pytest.mark.django_db
def test_update_read_only_field_rejected(api_client_approved, tenant_schema, approved_student):
    notification = Notification.objects.create(
        user_id=approved_student.id,
        notification_type=Notification.NotificationType.ANNOUNCEMENT,
        message="Hello",
        is_read=False,
    )

    url = reverse("notifications-detail", args=[notification.id])
    response = api_client_approved.patch(url, {"message": "Hack"}, format="json")

    assert response.status_code == 400
    assert _get_error_detail(response, "detail") is not None
