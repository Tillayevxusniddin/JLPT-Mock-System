"""
OpenAPI / Swagger documentation for the Groups app.

Enterprise-level API documentation for Class Groups and Group Memberships. Groups
and memberships live in the **tenant schema**; user details (names, avatars) are
fetched from the **public schema**. The list endpoint is optimized to batch-fetch
all teachers in one public-schema query to avoid N+1 schema switching.

Tags:
- **Groups:** CRUD for class groups; list members; role-based visibility.
- **Group Memberships:** Add/remove members; bulk add; filter by group/user/role.

Role-based visibility:
- **CENTER_ADMIN:** Full access to all groups and memberships in the center.
- **TEACHER:** Only groups where they are assigned as teacher; can update those groups; cannot create/destroy groups.
- **STUDENT:** Only groups they belong to (read-only for list/retrieve).
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

# -----------------------------------------------------------------------------
# Reusable responses
# -----------------------------------------------------------------------------

RESP_400 = OpenApiResponse(
    description="Bad Request: validation error (e.g. group full, duplicate membership, user not in center).",
)
RESP_401 = OpenApiResponse(description="Unauthorized: authentication required.")
RESP_403 = OpenApiResponse(
    description="Forbidden: STUDENT/TEACHER attempting unauthorized create/update/destroy.",
)
RESP_404 = OpenApiResponse(description="Not Found: group or membership not found.")


# =============================================================================
# Groups
# =============================================================================

GROUPS_LIST_DESCRIPTION = """
List class groups. **Role-based visibility:**
- **CENTER_ADMIN:** Sees **all** groups in the center.
- **TEACHER:** Sees **only** groups where they are assigned as teacher (`role_in_group=TEACHER`).
- **STUDENT:** Sees **only** groups they belong to (`role_in_group=STUDENT`).

**Cross-schema performance:** Teacher details (names, avatars) are fetched from the
**public schema** in a **single batch** for all groups on the page. This avoids
N+1 schema switching: e.g. 20 groups = 1 public-schema query instead of 20.
Each list item includes a `teachers` array built from this pre-fetched data.

**Search:** `name`, `description`.  
**Ordering:** `created_at`, `name` (default: -created_at).
"""

GROUPS_RETRIEVE_DESCRIPTION = """
Retrieve a single group. Same visibility rules as list: CENTER_ADMIN sees any group;
TEACHER only groups they teach; STUDENT only groups they are in.
"""

GROUPS_CREATE_DESCRIPTION = """
Create a new group. **CENTER_ADMIN only.** Teachers and students receive **403 Forbidden**.

**Optional:** Pass `teacher_ids` (list of user ids) to assign teachers to the group
immediately. All ids must belong to the same center and have role TEACHER.
"""

GROUPS_UPDATE_DESCRIPTION = """
Update a group. **CENTER_ADMIN** can update any group; **TEACHER** can update only
groups where they are assigned as teacher. Students receive **403**.
"""

GROUPS_PARTIAL_UPDATE_DESCRIPTION = "Partial update. Same permissions as full update."

GROUPS_DESTROY_DESCRIPTION = """
Delete a group. **CENTER_ADMIN only.** Teachers and students receive **403 Forbidden**.
"""

GROUPS_MEMBERS_DESCRIPTION = """
List members (students and teachers) of the group. Center admins of the same center
are also included. User details are loaded from the **public schema**. Same
visibility as list: only callable for groups the current user can see.
"""

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
            400: OpenApiResponse(
                description="Validation error (e.g. duplicate group name, invalid teacher_ids).",
                examples=[
                    OpenApiExample("Duplicate name", value={"name": ["A group with this name already exists."]}, response_only=True),
                    OpenApiExample("User not in center", value={"teacher_ids": ["User 5 belongs to another center."]}, response_only=True),
                ],
            ),
            401: RESP_401,
            403: OpenApiResponse(description="Only CENTER_ADMIN can create groups."),
        },
        examples=[
            OpenApiExample(
                "Create group with teachers",
                value={
                    "name": "N5 Prep 2024",
                    "description": "JLPT N5 preparation class.",
                    "max_students": 30,
                    "is_active": True,
                    "teacher_ids": [10, 11],
                },
                request_only=True,
            ),
            OpenApiExample(
                "Create group without teachers",
                value={
                    "name": "N4 Morning",
                    "description": "",
                    "max_students": 25,
                },
                request_only=True,
            ),
        ],
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
        description=GROUPS_PARTIAL_UPDATE_DESCRIPTION,
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
        responses={
            204: OpenApiResponse(description="Group deleted."),
            401: RESP_401,
            403: RESP_403,
            404: RESP_404,
        },
    ),
    members=extend_schema(
        tags=["Groups"],
        summary="List group members",
        description=GROUPS_MEMBERS_DESCRIPTION,
        responses={
            200: OpenApiResponse(
                description="Paginated list of users (students + teachers + center admins).",
            ),
            401: RESP_401,
            403: RESP_403,
            404: RESP_404,
        },
    ),
)


# =============================================================================
# Group Memberships
# =============================================================================

MEMBERSHIP_LIST_DESCRIPTION = """
List group memberships. **Role-based visibility:**
- **CENTER_ADMIN:** All memberships in the center.
- **TEACHER:** Only memberships in groups they teach.
- **STUDENT:** Only their own memberships (groups they belong to).

**Filters (DjangoFilterBackend + query params):**
- `group_id` (UUID): Filter by group.
- `user_id` (int): Filter by user.
- `role_in_group`: STUDENT | TEACHER

**Ordering:** `created_at`, `role_in_group` (default: -created_at).
"""

MEMBERSHIP_CREATE_DESCRIPTION = """
Add one member to a group. **CENTER_ADMIN only.** Teachers and students receive **403 Forbidden**.

**Constraints:**
- User must belong to the same center (cross-tenant check).
- For `role_in_group=STUDENT`: user must be STUDENT or GUEST; group must not be full (`student_count < max_students`).
- For `role_in_group=TEACHER`: user must have role TEACHER.
- Duplicate (same user + group + role) returns **400**.
"""

MEMBERSHIP_CREATE_400_EXAMPLES = [
    OpenApiExample("Group full", value={"group": "Group is full (max 30 students)."}, response_only=True),
    OpenApiExample("Duplicate membership", value={"detail": "This user is already a member of this group with this role."}, response_only=True),
    OpenApiExample("User not in center", value={"non_field_errors": ["User belongs to a different center."]}, response_only=True),
    OpenApiExample("User not TEACHER", value={"non_field_errors": ["User role must be TEACHER to be added as a teacher."]}, response_only=True),
]

MEMBERSHIP_DESTROY_DESCRIPTION = """
Remove a member from a group. **CENTER_ADMIN only.**

**Behavior:** For both **STUDENT** and **TEACHER**, the membership is deleted and a record is
created in **GroupMembershipHistory** (reason: REMOVED). This preserves a consistent audit trail.
"""

BULK_ADD_DESCRIPTION = """
**CENTER_ADMIN only.** Add multiple members to a group in one request.

**Behavior:** Fully atomic. Duplicate (user_id, role_in_group) within the request
are deduplicated; existing members in the group are skipped. Enforces `max_students`:
if adding the requested students would exceed the group limit, returns **400** with
"Group allows at most X students...".

**Request body:** `group_id` (UUID) and `members` (list of `{ "user_id": int, "role_in_group": "STUDENT" | "TEACHER" }`).
**Response:** `group_id`, `created_count`, `skipped_count`, `created_user_ids`.
"""

BULK_ADD_400_EXAMPLES = [
    OpenApiExample("Group full", value={"group": "Group allows at most 30 students. Adding 5 would make 32."}, response_only=True),
    OpenApiExample("User not in center", value={"non_field_errors": ["User 99 belongs to different center."]}, response_only=True),
]

group_membership_viewset_schema = extend_schema_view(
    list=extend_schema(
        tags=["Group Memberships"],
        summary="List memberships",
        description=MEMBERSHIP_LIST_DESCRIPTION,
        parameters=[
            OpenApiParameter(name="group_id", type=str, format="uuid", description="Filter by group UUID"),
            OpenApiParameter(name="user_id", type=int, description="Filter by user id"),
            OpenApiParameter(name="role_in_group", type=str, enum=["STUDENT", "TEACHER"], description="Filter by role in group"),
            OpenApiParameter(name="ordering", type=str, description="e.g. -created_at, role_in_group"),
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
            400: OpenApiResponse(
                description="Validation error: group full, duplicate membership, user not in center, or invalid role.",
                examples=MEMBERSHIP_CREATE_400_EXAMPLES,
            ),
            401: RESP_401,
            403: OpenApiResponse(description="Only CENTER_ADMIN can add members."),
        },
        examples=[
            OpenApiExample(
                "Add student",
                value={"group_id": "550e8400-e29b-41d4-a716-446655440000", "user_id": 42, "role_in_group": "STUDENT"},
                request_only=True,
            ),
            OpenApiExample(
                "Add teacher",
                value={"group_id": "550e8400-e29b-41d4-a716-446655440000", "user_id": 10, "role_in_group": "TEACHER"},
                request_only=True,
            ),
        ],
    ),
    destroy=extend_schema(
        tags=["Group Memberships"],
        summary="Remove member",
        description=MEMBERSHIP_DESTROY_DESCRIPTION,
        responses={
            200: OpenApiResponse(
                description="Student removed (history recorded) or teacher removed.",
                examples=[
                    OpenApiExample("Student", value={"message": "Student removed."}, response_only=True),
                    OpenApiExample("Teacher", value={"message": "Teacher removed from group."}, response_only=True),
                ],
            ),
            400: OpenApiResponse(description="Invalid role."),
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
                            "skipped_count": 1,
                            "created_user_ids": [10, 11],
                        },
                        response_only=True,
                    ),
                ],
            ),
            400: OpenApiResponse(
                description="Group full, user not in center, or validation error.",
                examples=BULK_ADD_400_EXAMPLES,
            ),
            401: RESP_401,
            403: OpenApiResponse(description="Only CENTER_ADMIN can bulk add."),
        },
        examples=[
            OpenApiExample(
                "Bulk add (mixed roles)",
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
            OpenApiExample(
                "Bulk add students only",
                value={
                    "group_id": "550e8400-e29b-41d4-a716-446655440000",
                    "members": [
                        {"user_id": 10, "role_in_group": "STUDENT"},
                        {"user_id": 11, "role_in_group": "STUDENT"},
                    ],
                },
                request_only=True,
            ),
        ],
    ),
)
