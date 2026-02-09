import asyncio
import pytest
from asgiref.sync import sync_to_async
from channels.layers import get_channel_layer
from channels.testing import WebsocketCommunicator
from rest_framework_simplejwt.tokens import RefreshToken

from config.asgi import application
from apps.notifications.serializers import NotificationSerializer
from apps.notifications.models import Notification
from apps.core.tenant_utils import schema_context


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_ws_isolation_between_users(test_center, approved_student, unapproved_student):
    @sync_to_async
    def get_token(user):
        return str(RefreshToken.for_user(user).access_token)
    
    token_a = await get_token(approved_student)
    token_b = await get_token(unapproved_student)

    comm_a = WebsocketCommunicator(application, f"/ws/notifications/?token={token_a}")
    comm_b = WebsocketCommunicator(application, f"/ws/notifications/?token={token_b}")

    connected_a, _ = await comm_a.connect()
    connected_b, _ = await comm_b.connect()

    assert connected_a is True
    assert connected_b is True

    channel_layer = get_channel_layer()
    await channel_layer.group_send(
        f"notify_{approved_student.id}",
        {"type": "send_notification", "message": {"message": "Ping"}},
    )

    data_a = await comm_a.receive_json_from(timeout=2)
    assert data_a.get("message") == "Ping"

    with pytest.raises(asyncio.TimeoutError):
        await comm_b.receive_json_from(timeout=1)

    try:
        await comm_a.disconnect()
    except (asyncio.CancelledError, Exception):
        pass
    try:
        await comm_b.disconnect()
    except (asyncio.CancelledError, Exception):
        pass


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_ws_payload_matches_serializer(test_center, approved_student):
    @sync_to_async
    def create_notification():
        with schema_context(test_center.schema_name):
            return Notification.objects.create(
                user_id=approved_student.id,
                notification_type=Notification.NotificationType.ANNOUNCEMENT,
                message="Hello",
                is_read=False,
            )
    
    @sync_to_async
    def serialize_notification(notification):
        return NotificationSerializer(notification).data
    
    @sync_to_async
    def get_token(user):
        return str(RefreshToken.for_user(user).access_token)
    
    notification = await create_notification()
    payload = await serialize_notification(notification)
    token = await get_token(approved_student)
    
    comm = WebsocketCommunicator(application, f"/ws/notifications/?token={token}")
    connected, _ = await comm.connect()
    assert connected is True

    channel_layer = get_channel_layer()
    await channel_layer.group_send(
        f"notify_{approved_student.id}",
        {"type": "send_notification", "message": payload},
    )

    received = await comm.receive_json_from(timeout=2)
    assert received["id"] == payload["id"]
    assert received["notification_type"] == payload["notification_type"]
    assert received["message"] == payload["message"]

    await comm.disconnect()
