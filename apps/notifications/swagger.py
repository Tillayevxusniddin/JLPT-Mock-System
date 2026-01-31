"""
OpenAPI / Swagger documentation for the notifications app (drf-spectacular).

Real-time engagement via WebSockets and REST for notification list/mark-read.
Automated reminders (DEADLINE_APPROACHING) are sent by Celery with multi-tenant
iteration and batch debounce (one per (user, homework) pair).

**WebSocket (master-level):**
- **URL:** `ws/notifications/` (relative to API host; e.g. `wss://api.example.com/ws/notifications/`).
- **Authentication:** JWT only. Pass via query param `?token=<access_token>` or
  header `Authorization: Bearer <access_token>`. User identity is taken **only** from
  the server (JWTAuthMiddleware → scope["user"]). No user IDs in the URL.
- **Isolation:** Group name is server-controlled: `notify_{user_id}`. A user is added
  only to their own channel; they cannot subscribe to another user's or tenant's channel.
- **Message structure:** Server sends JSON objects (one per notification). See examples below.

**REST:** list (filter by is_read), retrieve, partial_update (mark as read), mark-all-read (POST).
**Signals:** All notification triggers use transaction.on_commit() so the real-time push
happens only after the DB transaction commits.
"""
from drf_spectacular.utils import (
    OpenApiExample,
    OpenApiParameter,
    OpenApiResponse,
    extend_schema,
    extend_schema_view,
)

from .serializers import NotificationSerializer

RESP_400 = OpenApiResponse(
    description="Validation error: e.g. only is_read can be updated; other fields are read-only.",
    examples=[
        OpenApiExample(
            "Invalid field update",
            value={"detail": "Only 'is_read' field can be updated."},
            response_only=True,
        ),
    ],
)
RESP_401 = OpenApiResponse(description="Authentication required.")
RESP_403 = OpenApiResponse(description="Permission denied.")
RESP_404 = OpenApiResponse(description="Notification not found.")

# ---- WebSocket message examples (for documentation) ----
WS_TASK_ASSIGNED_EXAMPLE = {
    "id": "550e8400-e29b-41d4-a716-446655440000",
    "user_id": 1,
    "notification_type": "TASK_ASSIGNED",
    "message": "New homework 'Week 3' has been assigned to you.",
    "is_read": False,
    "link": "/homeworks/660e8400-e29b-41d4-a716-446655440001/",
    "related_task_id": "660e8400-e29b-41d4-a716-446655440001",
    "related_submission_id": None,
    "related_group_id": None,
    "related_contact_request_id": None,
    "created_at": "2025-01-29T12:00:00Z",
    "updated_at": "2025-01-29T12:00:00Z",
}

WS_EXAM_OPENED_EXAMPLE = {
    "id": "770e8400-e29b-41d4-a716-446655440002",
    "user_id": 1,
    "notification_type": "EXAM_OPENED",
    "message": "Exam 'JLPT N5 Mock - Room A' is now open.",
    "is_read": False,
    "link": "/exams/880e8400-e29b-41d4-a716-446655440003/",
    "related_task_id": "880e8400-e29b-41d4-a716-446655440003",
    "related_submission_id": None,
    "related_group_id": None,
    "related_contact_request_id": None,
    "created_at": "2025-01-29T09:00:00Z",
    "updated_at": "2025-01-29T09:00:00Z",
}

WS_SUBMISSION_GRADED_EXAMPLE = {
    "id": "990e8400-e29b-41d4-a716-446655440004",
    "user_id": 1,
    "notification_type": "SUBMISSION_GRADED",
    "message": "Your homework submission for 'Week 3' has been graded.",
    "is_read": False,
    "link": "/homeworks/660e8400-e29b-41d4-a716-446655440001/results/",
    "related_task_id": "660e8400-e29b-41d4-a716-446655440001",
    "related_submission_id": "aa0e8400-e29b-41d4-a716-446655440005",
    "related_group_id": None,
    "related_contact_request_id": None,
    "created_at": "2025-01-29T14:00:00Z",
    "updated_at": "2025-01-29T14:00:00Z",
}

# Export for schema description / WebSocket docs
WEBSOCKET_DESCRIPTION = """
**WebSocket URL:** `ws/notifications/` (e.g. `wss://your-api/ws/notifications/`).

**Authentication:** JWT via query param `?token=<access_token>` or header `Authorization: Bearer <access_token>`.
User is resolved from the token (scope["user"]); no user IDs in the URL.

**Isolation:** Each user is added only to group `notify_{user_id}` (server-controlled). Users cannot join another user's channel.

**Server → client JSON (one object per notification):**
- `id`, `user_id`, `notification_type`, `message`, `is_read`, `link`, `related_task_id`, `related_submission_id`, `related_group_id`, `related_contact_request_id`, `created_at`, `updated_at`.

**Example (TASK_ASSIGNED):** link to homework. **Example (EXAM_OPENED):** link to exam room. **Example (SUBMISSION_GRADED):** link to results.
"""

notification_viewset_schema = extend_schema_view(
    list=extend_schema(
        tags=["Notifications"],
        summary="List notifications",
        description=(
            "List notifications for the current user (tenant-scoped; user_id = request.user.id). "
            "Filter by is_read. Lightweight serializer (no N+1)."
        ),
        parameters=[
            OpenApiParameter(
                name="is_read",
                type=bool,
                description="Filter by read status (true = read only, false = unread only).",
            ),
            OpenApiParameter(name="ordering", type=str, description="e.g. -created_at"),
        ],
        responses={200: NotificationSerializer(many=True), 401: RESP_401, 403: RESP_403},
        examples=[
            OpenApiExample(
                "TASK_ASSIGNED (link to homework)",
                value=[WS_TASK_ASSIGNED_EXAMPLE],
                response_only=True,
            ),
            OpenApiExample(
                "EXAM_OPENED (link to exam room)",
                value=[WS_EXAM_OPENED_EXAMPLE],
                response_only=True,
            ),
            OpenApiExample(
                "SUBMISSION_GRADED (link to results)",
                value=[WS_SUBMISSION_GRADED_EXAMPLE],
                response_only=True,
            ),
        ],
    ),
    retrieve=extend_schema(
        tags=["Notifications"],
        summary="Get notification",
        responses={200: NotificationSerializer, 401: RESP_401, 403: RESP_403, 404: RESP_404},
    ),
    update=extend_schema(
        tags=["Notifications"],
        summary="Full update (is_read only)",
        description="PUT with {\"is_read\": true}. Only is_read is writable; other fields return 400.",
        request=NotificationSerializer,
        responses={200: NotificationSerializer, 400: RESP_400, 401: RESP_401, 403: RESP_403, 404: RESP_404},
        examples=[
            OpenApiExample("Mark read", value={"is_read": True}, request_only=True),
        ],
    ),
    partial_update=extend_schema(
        tags=["Notifications"],
        summary="Mark as read",
        description="PATCH with {\"is_read\": true} to mark one notification as read. Only is_read is writable.",
        request=NotificationSerializer,
        responses={200: NotificationSerializer, 400: RESP_400, 401: RESP_401, 403: RESP_403, 404: RESP_404},
        examples=[
            OpenApiExample("Mark read", value={"is_read": True}, request_only=True),
        ],
    ),
    mark_all_read=extend_schema(
        tags=["Notifications"],
        summary="Mark all as read",
        description="POST to mark all unread notifications for the current user as read. Returns count of updated.",
        responses={
            200: OpenApiResponse(
                description="Count of notifications marked as read.",
                examples=[
                    OpenApiExample("Success", value={"updated": 5}, response_only=True),
                ],
            ),
            401: RESP_401,
            403: RESP_403,
        },
    ),
)

notification_websocket_description = WEBSOCKET_DESCRIPTION
