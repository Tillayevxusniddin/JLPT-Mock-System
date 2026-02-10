"""
OpenAPI / Swagger documentation for the notifications app (drf-spectacular).

Real-time engagement via WebSockets and REST for notification list/mark-read.
Automated reminders (DEADLINE_APPROACHING) are sent by Celery with multi-tenant
iteration and batch debounce (one per (user, homework) pair).

================================================================================
WEBSOCKET (REAL-TIME)
================================================================================

- **URL:** `ws/notifications/` (relative to API host; e.g. `wss://api.example.com/ws/notifications/`).
- **Authentication:** JWT only. Pass via query param `?token=<access_token>` or
    header `Authorization: Bearer <access_token>`.
- **Handshake:** User identity is resolved server-side (JWTAuthMiddleware → scope["user"]).
    No user IDs appear in the URL or path.
- **Rejection codes:** 4401 if missing/invalid token; 1011 if server error.
- **Isolation:** Group name is server-controlled: `notify_{user_id}`. A user can join
    only their own group; cross-user or cross-tenant subscription is impossible.
- **Message structure:** Server sends JSON objects (one per notification). See examples below.

================================================================================
DELIVERY GUARANTEES & DEBOUNCE
================================================================================

- **transaction.on_commit():** real-time push occurs only after DB commit.
- **Debounce:** One notification per (user_id, notification_type, related_id).
- **Owner notifications:** Platform-wide; pushed via WebSocket without tenant DB row.

================================================================================
NOTIFICATION TYPES (PARTIAL LIST)
================================================================================

- Student: TASK_ASSIGNED, EXAM_OPENED, EXAM_UPDATED, EXAM_CLOSING_SOON,
    HOMEWORK_UPDATED, HOMEWORK_DEADLINE_CHANGED, DEADLINE_APPROACHING, SUBMISSION_GRADED
- Teacher: NEW_SUBMISSION, REVIEW_OVERDUE, STUDENT_JOINED_GROUP
- Center Admin: MOCK_TEST_PUBLISHED
- Owner: CONTACT_REQUEST_HIGH_PRIORITY (platform-wide)

================================================================================
REST ENDPOINTS
================================================================================

- list (filter by is_read), retrieve, partial_update (mark as read), mark-all-read (POST).
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

WS_EXAM_UPDATED_EXAMPLE = {
    "id": "990e8400-e29b-41d4-a716-446655440006",
    "user_id": 1,
    "notification_type": "EXAM_UPDATED",
    "message": "Exam 'JLPT N5 Mock - Room A' has been updated.",
    "is_read": False,
    "link": "/exams/880e8400-e29b-41d4-a716-446655440003/",
    "related_task_id": "880e8400-e29b-41d4-a716-446655440003",
    "related_submission_id": None,
    "related_group_id": None,
    "related_contact_request_id": None,
    "created_at": "2025-01-29T15:00:00Z",
    "updated_at": "2025-01-29T15:00:00Z",
}

WS_EXAM_CLOSING_SOON_EXAMPLE = {
    "id": "990e8400-e29b-41d4-a716-446655440007",
    "user_id": 1,
    "notification_type": "EXAM_CLOSING_SOON",
    "message": "Exam 'JLPT N5 Mock - Room A' will close in 1 hour.",
    "is_read": False,
    "link": "/exams/880e8400-e29b-41d4-a716-446655440003/",
    "related_task_id": "880e8400-e29b-41d4-a716-446655440003",
    "related_submission_id": None,
    "related_group_id": None,
    "related_contact_request_id": None,
    "created_at": "2025-01-29T16:00:00Z",
    "updated_at": "2025-01-29T16:00:00Z",
}

WS_DEADLINE_APPROACHING_EXAMPLE = {
    "id": "990e8400-e29b-41d4-a716-446655440008",
    "user_id": 1,
    "notification_type": "DEADLINE_APPROACHING",
    "message": "Homework 'Week 4' is due by 2025-02-05 23:59.",
    "is_read": False,
    "link": "/homeworks/660e8400-e29b-41d4-a716-446655440001/",
    "related_task_id": "660e8400-e29b-41d4-a716-446655440001",
    "related_submission_id": None,
    "related_group_id": None,
    "related_contact_request_id": None,
    "created_at": "2025-02-04T12:00:00Z",
    "updated_at": "2025-02-04T12:00:00Z",
}

WS_NEW_SUBMISSION_EXAMPLE = {
    "id": "990e8400-e29b-41d4-a716-446655440009",
    "user_id": 42,
    "notification_type": "NEW_SUBMISSION",
    "message": "A student has submitted an assignment for review.",
    "is_read": False,
    "link": None,
    "related_task_id": None,
    "related_submission_id": "aa0e8400-e29b-41d4-a716-446655440005",
    "related_group_id": None,
    "related_contact_request_id": None,
    "created_at": "2025-02-04T13:00:00Z",
    "updated_at": "2025-02-04T13:00:00Z",
}

WS_REVIEW_OVERDUE_EXAMPLE = {
    "id": "990e8400-e29b-41d4-a716-446655440010",
    "user_id": 42,
    "notification_type": "REVIEW_OVERDUE",
    "message": "A submission has been awaiting review for over 48 hours.",
    "is_read": False,
    "link": None,
    "related_task_id": None,
    "related_submission_id": "aa0e8400-e29b-41d4-a716-446655440006",
    "related_group_id": None,
    "related_contact_request_id": None,
    "created_at": "2025-02-06T09:00:00Z",
    "updated_at": "2025-02-06T09:00:00Z",
}

WS_STUDENT_JOINED_GROUP_EXAMPLE = {
    "id": "990e8400-e29b-41d4-a716-446655440011",
    "user_id": 42,
    "notification_type": "STUDENT_JOINED_GROUP",
    "message": "A new student has joined your group 'N5 Morning'.",
    "is_read": False,
    "link": "/groups/770e8400-e29b-41d4-a716-446655440002/",
    "related_task_id": None,
    "related_submission_id": None,
    "related_group_id": "770e8400-e29b-41d4-a716-446655440002",
    "related_contact_request_id": None,
    "created_at": "2025-02-06T11:00:00Z",
    "updated_at": "2025-02-06T11:00:00Z",
}

WS_MOCK_TEST_PUBLISHED_EXAMPLE = {
    "id": "990e8400-e29b-41d4-a716-446655440012",
    "user_id": 7,
    "notification_type": "MOCK_TEST_PUBLISHED",
    "message": "A teacher published mock test 'JLPT N3 Practice'.",
    "is_read": False,
    "link": "/mock-tests/880e8400-e29b-41d4-a716-446655440003/",
    "related_task_id": "880e8400-e29b-41d4-a716-446655440003",
    "related_submission_id": None,
    "related_group_id": None,
    "related_contact_request_id": None,
    "created_at": "2025-02-06T12:00:00Z",
    "updated_at": "2025-02-06T12:00:00Z",
}

WS_CONTACT_REQUEST_HIGH_PRIORITY_EXAMPLE = {
    "id": None,
    "user_id": 1,
    "notification_type": "CONTACT_REQUEST_HIGH_PRIORITY",
    "message": "High priority contact request from Jane Doe.",
    "is_read": False,
    "link": None,
    "related_task_id": None,
    "related_submission_id": None,
    "related_group_id": None,
    "related_contact_request_id": "cc0e8400-e29b-41d4-a716-446655440013",
    "created_at": None,
    "updated_at": None,
}

# Export for schema description / WebSocket docs
WEBSOCKET_DESCRIPTION = """
**WebSocket URL:** `ws/notifications/` (e.g. `wss://your-api/ws/notifications/`).

**Authentication:** JWT via query param `?token=<access_token>` or header `Authorization: Bearer <access_token>`.
User is resolved from the token (scope["user"]); no user IDs in the URL.

**Isolation:** Each user is added only to group `notify_{user_id}` (server-controlled). Users cannot join another user's channel.

**Server → client JSON (one object per notification):**
- `id`, `user_id`, `notification_type`, `message`, `is_read`, `link`, `related_task_id`, `related_submission_id`, `related_group_id`, `related_contact_request_id`, `created_at`, `updated_at`.

**Examples:** TASK_ASSIGNED, EXAM_OPENED, DEADLINE_APPROACHING, SUBMISSION_GRADED, NEW_SUBMISSION, REVIEW_OVERDUE.
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
                "DEADLINE_APPROACHING (24h window)",
                value=[WS_DEADLINE_APPROACHING_EXAMPLE],
                response_only=True,
            ),
            OpenApiExample(
                "SUBMISSION_GRADED (link to results)",
                value=[WS_SUBMISSION_GRADED_EXAMPLE],
                response_only=True,
            ),
            OpenApiExample(
                "NEW_SUBMISSION (teacher alert)",
                value=[WS_NEW_SUBMISSION_EXAMPLE],
                response_only=True,
            ),
            OpenApiExample(
                "REVIEW_OVERDUE (48h pending)",
                value=[WS_REVIEW_OVERDUE_EXAMPLE],
                response_only=True,
            ),
            OpenApiExample(
                "STUDENT_JOINED_GROUP",
                value=[WS_STUDENT_JOINED_GROUP_EXAMPLE],
                response_only=True,
            ),
            OpenApiExample(
                "MOCK_TEST_PUBLISHED",
                value=[WS_MOCK_TEST_PUBLISHED_EXAMPLE],
                response_only=True,
            ),
            OpenApiExample(
                "CONTACT_REQUEST_HIGH_PRIORITY (owner)",
                value=[WS_CONTACT_REQUEST_HIGH_PRIORITY_EXAMPLE],
                response_only=True,
            ),
            OpenApiExample(
                "EXAM_UPDATED (schedule change)",
                value=[WS_EXAM_UPDATED_EXAMPLE],
                response_only=True,
            ),
            OpenApiExample(
                "EXAM_CLOSING_SOON (1 hour reminder)",
                value=[WS_EXAM_CLOSING_SOON_EXAMPLE],
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
