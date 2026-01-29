# apps/groups/swagger.py
"""
OpenAPI / Swagger documentation for the groups app.

Groups and memberships live in the **tenant schema**; users live in the **public schema**.
List view pre-fetches all teachers in one public-schema query (teacher_map) to avoid N+1.

Role-based visibility:
- **CENTER_ADMIN:** Full access to all groups and memberships in the center.
- **TEACHER:** Only groups they are assigned to (role_in_group=TEACHER).
- **STUDENT:** Only groups they are a member of (role_in_group=STUDENT).
"""
from drf_spectacular.utils import (
    OpenApiExample,
    OpenApiParameter,
    OpenApiResponse,
    extend_schema,
    extend_schema_view,
)

from apps.groups.serializers import (
    BulkGroupMembershipSerializer,
    GroupListSerializer,
    GroupMembershipSerializer,
    GroupSerializer,
)

RESP_400 = OpenApiResponse(description="Validation error (e.g. group full, user not in center, duplicate membership).")
RESP_401 = OpenApiResponse(description="Authentication required.")
RESP_403 = OpenApiResponse(description="Insufficient permissions (e.g. not in this group).")
RESP_404 = OpenApiResponse(description="Group or membership not found.")


# ---- Group viewset ----

GROUPS_LIST_DESCRIPTION = """
List groups. **Visibility:**
- **CENTER_ADMIN:** All groups in the center.
- **TEACHER:** Only groups where they are assigned as teacher.
- **STUDENT:** Only groups where they are a member.

Teachers are fetched from the public schema in a single batch (no N+1).
"""
GROUPS_RETRIEVE_DESCRIPTION = "Retrieve a group. Same visibility as list."
GROUPS_CREATE_DESCRIPTION = "Create a group. **CENTER_ADMIN only.** Optionally assign teachers via `teacher_ids`."
GROUPS_UPDATE_DESCRIPTION = "Update a group. **CENTER_ADMIN** or **TEACHER** assigned to this group."
GROUPS_DESTROY_DESCRIPTION = "Delete a group. **CENTER_ADMIN only.**"
GROUPS_MEMBERS_DESCRIPTION = "List members (students + teachers) of the group. Users are loaded from public schema."

group_viewset_schema = extend_schema_view(
    list=extend_schema(
        tags=["Groups"],
        summary="List groups",
        description=GROUPS_LIST_DESCRIPTION,
        parameters=[
            OpenApiParameter(name="search", type=str, description="Search name, description"),
            OpenApiParameter(name="ordering", type=str, description="e.g. -created_at, name"),
        ],
        responses={
            200: GroupListSerializer(many=True),
            401: RESP_401,
            403: RESP_403,
        },
    ),
    retrieve=extend_schema(
        tags=["Groups"],
        summary="Get group",
        description=GROUPS_RETRIEVE_DESCRIPTION,
        responses={
            200: GroupSerializer,
            401: RESP_401,
            403: RESP_403,
            404: RESP_404,
        },
    ),
    create=extend_schema(
        tags=["Groups"],
        summary="Create group",
        description=GROUPS_CREATE_DESCRIPTION,
        request=GroupSerializer,
        responses={
            201: GroupSerializer,
            400: RESP_400,
            401: RESP_401,
            403: RESP_403,
        },
    ),
    update=extend_schema(
        tags=["Groups"],
        summary="Update group",
        description=GROUPS_UPDATE_DESCRIPTION,
        request=GroupSerializer,
        responses={
            200: GroupSerializer,
            400: RESP_400,
            401: RESP_401,
            403: RESP_403,
            404: RESP_404,
        },
    ),
    partial_update=extend_schema(
        tags=["Groups"],
        summary="Partial update group",
        request=GroupSerializer,
        responses={
            200: GroupSerializer,
            400: RESP_400,
            401: RESP_401,
            403: RESP_403,
            404: RESP_404,
        },
    ),
    destroy=extend_schema(
        tags=["Groups"],
        summary="Delete group",
        description=GROUPS_DESTROY_DESCRIPTION,
        responses={204: OpenApiResponse(description="Group deleted."), 401: RESP_401, 403: RESP_403, 404: RESP_404},
    ),
    members=extend_schema(
        tags=["Groups"],
        summary="List group members",
        description=GROUPS_MEMBERS_DESCRIPTION,
        responses={
            200: OpenApiResponse(description="Paginated list of users (students + teachers + center admins)."),
            401: RESP_401,
            403: RESP_403,
            404: RESP_404,
        },
    ),
)


# ---- Group membership viewset ----

MEMBERSHIP_LIST_DESCRIPTION = """
List memberships. **Visibility:** Same as groups (CENTER_ADMIN all, TEACHER their groups, STUDENT their groups).

**Filters:** `group_id` (UUID), `user_id` (int), `role_in_group` (STUDENT | TEACHER)
**Ordering:** created_at, role_in_group (default: -created_at)
"""
MEMBERSHIP_CREATE_DESCRIPTION = "Add one member to a group. **CENTER_ADMIN only.** Enforces max_students and same-center."
MEMBERSHIP_DESTROY_DESCRIPTION = "Remove a member. **CENTER_ADMIN only.** Students get a history record (REMOVED)."
BULK_ADD_DESCRIPTION = """
**CENTER_ADMIN only.** Add multiple members in one request. Fully atomic; enforces max_students and dedupes.
Duplicate (user_id, role) in the same request are ignored. Existing members are skipped.
"""

group_membership_viewset_schema = extend_schema_view(
    list=extend_schema(
        tags=["Group Memberships"],
        summary="List memberships",
        description=MEMBERSHIP_LIST_DESCRIPTION,
        parameters=[
            OpenApiParameter(name="group_id", type=str, format="uuid", description="Filter by group"),
            OpenApiParameter(name="user_id", type=int),
            OpenApiParameter(name="role_in_group", type=str, enum=["STUDENT", "TEACHER"]),
            OpenApiParameter(name="ordering", type=str),
        ],
        responses={
            200: GroupMembershipSerializer(many=True),
            401: RESP_401,
            403: RESP_403,
        },
    ),
    create=extend_schema(
        tags=["Group Memberships"],
        summary="Add member",
        description=MEMBERSHIP_CREATE_DESCRIPTION,
        request=GroupMembershipSerializer,
        responses={
            201: GroupMembershipSerializer,
            400: RESP_400,
            401: RESP_401,
            403: RESP_403,
        },
    ),
    destroy=extend_schema(
        tags=["Group Memberships"],
        summary="Remove member",
        description=MEMBERSHIP_DESTROY_DESCRIPTION,
        responses={
            200: OpenApiResponse(description="Student removed (history recorded) or teacher removed."),
            400: RESP_400,
            401: RESP_401,
            403: RESP_403,
            404: RESP_404,
        },
    ),
    bulk_add=extend_schema(
        tags=["Group Memberships"],
        summary="Bulk add members",
        description=BULK_ADD_DESCRIPTION,
        request=BulkGroupMembershipSerializer,
        responses={
            201: OpenApiResponse(
                description="Created count, skipped count, and created_user_ids.",
                examples=[
                    OpenApiExample(
                        "Success",
                        value={
                            "group_id": "550e8400-e29b-41d4-a716-446655440000",
                            "created_count": 2,
                            "skipped_count": 0,
                            "created_user_ids": [10, 11],
                        },
                        response_only=True,
                    ),
                ],
            ),
            400: RESP_400,
            401: RESP_401,
            403: RESP_403,
        },
        examples=[
            OpenApiExample(
                "Request body",
                value={
                    "group_id": "550e8400-e29b-41d4-a716-446655440000",
                    "members": [
                        {"user_id": 1, "role_in_group": "STUDENT"},
                        {"user_id": 2, "role_in_group": "STUDENT"},
                        {"user_id": 3, "role_in_group": "TEACHER"},
                    ],
                },
                request_only=True,
            ),
        ],
    ),
)
