"""
OpenAPI / Swagger documentation for the Groups app.

Enterprise-level API documentation for Class Groups and Group Memberships. Groups
and memberships live in the **tenant schema**; user details (names, avatars) are
fetched from the **public schema**. The list endpoint is optimized to batch-fetch
all teachers in one public-schema query to avoid N+1 schema switching.

Tags:
- **Groups:** CRUD for class groups; list members; role-based visibility.
- **Group Memberships:** Add/remove members; bulk add; filter by group/user/role.

=============================================================================
ROLE-BASED ACCESS CONTROL & VISIBILITY MATRIX
=============================================================================

GROUP VISIBILITY (List & Retrieve):
- **CENTER_ADMIN:** Sees ALL groups in the center (no filtering).
- **TEACHER:** Sees ONLY groups where they have role_in_group=TEACHER.
  - Teachers are filtered by querying GroupMembership(user_id, role_in_group=TEACHER).
  - If a teacher is removed from all groups, they see zero groups.
  - Cannot see groups where they are students.
- **STUDENT:** Sees ONLY groups where they have role_in_group=STUDENT.
  - Students are filtered similarly: GroupMembership(user_id, role_in_group=STUDENT).
  - If a student belongs to multiple groups, they see all of them.
  - Cannot see groups where they are not assigned.

CROSS-ROLE SCENARIOS:
- A user can be BOTH TEACHER and STUDENT in the SAME group.
- Teachers see a group via TEACHER role; students don't see it.
- Students see a group via STUDENT role; teachers don't see it.
- Each role has separate visibility scope.

GROUP MODIFICATION PERMISSIONS:
| Action | CENTER_ADMIN | TEACHER | STUDENT |
|--------|--------------|---------|---------|
| CREATE | ✓ 201 | ✗ 403 | ✗ 403 |
| LIST | ✓ all | ✓ owns (teacher) | ✓ owns (student) |
| RETRIEVE | ✓ any | ✓ if teaches | ✓ if belongs |
| UPDATE | ✓ any | ✓ if teaches | ✗ 403 |
| DELETE | ✓ any | ✗ 403 (even if teaches) | ✗ 403 |

Note: Teachers can UPDATE groups they teach, but cannot DELETE any group.
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

# =============================================================================
# DATA CONSTRAINTS & UNIQUE CONSTRAINTS
# =============================================================================

UNIQUE_CONSTRAINTS = """
**Group Name Uniqueness:**
Groups have a UNIQUE constraint on the `name` field within each center.
Attempting to create or update a group with a duplicate name returns **400 Bad Request**:
{"name": ["A group with this name already exists."]}

**GroupMembership Uniqueness:**
GroupMembership has a UNIQUE constraint on (user_id, group_id, role_in_group).
Attempting to add a user with a duplicate role to a group returns **400 Bad Request**:
{"detail": "This user is already a member of this group with this role."}

Note: A user CAN be BOTH STUDENT and TEACHER in the same group (different roles, not duplicate).
"""

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
- **TEACHER:** Sees **only** groups where they have role_in_group=TEACHER.
  - Filtered by: `GroupMembership.objects.filter(user_id=request.user.id, role_in_group=TEACHER)`.
  - If a teacher is removed from all groups, the list is empty.
  - Teachers cannot see groups where they are students.
- **STUDENT:** Sees **only** groups where they have role_in_group=STUDENT.
  - Filtered by: `GroupMembership.objects.filter(user_id=request.user.id, role_in_group=STUDENT)`.
  - Students cannot see groups where they are not assigned.

**Cross-schema batch optimization (critical):**
Teacher details (names, avatars, first_name, last_name) are fetched from the **public schema**
in a **single batch** for all groups on the page. This avoids N+1 schema switching.

Example:
- WITHOUT optimization: 20 groups = 20 schema switches (20 public-schema queries).
- WITH optimization: 20 groups = 1 schema switch (1 public-schema query).

The `context['teacher_map']` is pre-populated in list view:
```
teacher_map = {
  'group_id_1': [{'id': 10, 'first_name': 'Taro', ...}, {'id': 11, 'first_name': 'Hanako', ...}],
  'group_id_2': [{'id': 5, 'first_name': 'Yuki', ...}],
  ...
}
```
Each list item includes a `teachers` array populated from this map.

**Search:** `name`, `description`.  
**Ordering:** `created_at`, `name` (default: -created_at).
**Pagination:** Standard DRF pagination (default 20 per page).
"""

GROUPS_RETRIEVE_DESCRIPTION = """
Retrieve a single group. Same visibility rules as list: CENTER_ADMIN sees any group;
TEACHER only groups they teach; STUDENT only groups they are in.
"""

GROUPS_CREATE_DESCRIPTION = """
Create a new group. **CENTER_ADMIN only.** Teachers and students receive **403 Forbidden**.

**Constraints:**
- Group name is **unique per center** (UniqueConstraint on name field).
- `max_students` defaults to 30; must be > 0 if provided.
- `is_active` defaults to True.

**Optional:** Pass `teacher_ids` (list of user IDs) to assign teachers immediately.
- All IDs must belong to the same center as the requester.
- All users must have role TEACHER (not STUDENT or GUEST).
- Teachers are created via bulk insert; `teacher_count` is auto-updated.

**403 Scenarios:**
- TEACHER user attempting to create → 403 Forbidden
- STUDENT user attempting to create → 403 Forbidden

**400 Error Examples:**
- Duplicate group name: "A group with this name already exists."
- Teacher user not found: "Some users were not found."
- Teacher from another center: "User {id} belongs to another center."
- User is not TEACHER: "User {id} is not a TEACHER."
"""

GROUPS_UPDATE_DESCRIPTION = """
Update a group. **CENTER_ADMIN** can update any group. **TEACHER** can update only
groups where they have role_in_group=TEACHER. Students receive **403**.

**403 Scenarios (specific):**
- TEACHER user updating a group they don't teach → 403 Forbidden
- TEACHER user updating a group where they are student only → 403 Forbidden
- STUDENT user attempting any update → 403 Forbidden

**400 Error Examples:**
- Duplicate group name: "A group with this name already exists."
- Database integrity error: "Database integrity error." (rare)

**Note:** Teachers CAN update the groups they teach (name, description, max_students, is_active).
Teachers CANNOT delete any group (only CENTER_ADMIN can delete).
"""

GROUPS_PARTIAL_UPDATE_DESCRIPTION = "Partial update. Same permissions as full update."

GROUPS_DESTROY_DESCRIPTION = """
Delete a group. **CENTER_ADMIN only.** Teachers and students receive **403 Forbidden**.

**403 Scenarios:**
- TEACHER user attempting delete (even if they teach the group) → 403 Forbidden
- STUDENT user attempting delete → 403 Forbidden

**Behavior:** When deleted, all GroupMembership records and GroupMembershipHistory 
are cascaded deleted (GROUP_DELETION via CASCADE).

**Response:** 200 OK with message (not 204 No Content). See response examples.
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
                description="Validation error (e.g. duplicate group name, invalid teacher_ids, user not TEACHER).",
                examples=[
                    OpenApiExample("Duplicate name", value={"name": ["A group with this name already exists."]}, response_only=True),
                    OpenApiExample("User not in center", value={"teacher_ids": ["User 5 belongs to another center."]}, response_only=True),
                    OpenApiExample("User not TEACHER", value={"teacher_ids": ["User 3 is not a TEACHER."]}, response_only=True),
                    OpenApiExample("User not found", value={"teacher_ids": ["Some users were not found."]}, response_only=True),
                ],
            ),
            401: RESP_401,
            403: OpenApiResponse(description="Only CENTER_ADMIN can create groups. TEACHER/STUDENT receive 403."),
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
            200: OpenApiResponse(
                description="Group deleted successfully.",
                examples=[
                    OpenApiExample("Success", value={"message": "Group deleted successfully."}, response_only=True),
                ],
            ),
            401: RESP_401,
            403: OpenApiResponse(description="Only CENTER_ADMIN can delete groups. TEACHER/STUDENT receive 403."),
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
- **CENTER_ADMIN:** All memberships in the center (no filtering).
- **TEACHER:** Only memberships in groups they teach (role_in_group=TEACHER).
  - Teachers see both student and teacher memberships in their groups.
  - Teachers cannot see memberships in groups where they don't teach.
- **STUDENT:** Only their own memberships (groups they are in).
  - Students can only see themselves, not other students in their groups (privacy).

**Member Role Meanings:**
- `role_in_group=STUDENT`: User is a student in the group.
- `role_in_group=TEACHER`: User is a teacher in the group.
- A user can have BOTH roles in the SAME group (e.g., teaching one group, studying in another).

**Filters (DjangoFilterBackend + query params):**
- `group_id` (UUID): Filter by group.
- `user_id` (int): Filter by user.
- `role_in_group`: STUDENT | TEACHER

**Ordering:** `created_at`, `role_in_group` (default: -created_at).
"""

MEMBERSHIP_CREATE_DESCRIPTION = """
Add one member to a group. **CENTER_ADMIN only.** Teachers and students receive **403 Forbidden**.

**Constraints (validated in order):**
1. User must exist (cross-schema check in public schema).
2. User must belong to the same center as requester.
3. For `role_in_group=STUDENT`:
   - User must have role STUDENT or GUEST (not TEACHER).
   - Group must not be full: `group.student_count < group.max_students`.
4. For `role_in_group=TEACHER`:
   - User must have role TEACHER (not STUDENT).
5. Duplicate membership: Same (user_id, group_id, role_in_group) returns **400**.

**400 Error Examples:**
- Group full: "Group is full (max 30 students)."
- Duplicate membership: "This user is already a member of this group with this role."
- User not in center: "User belongs to a different center."
- User is not TEACHER: "User role must be TEACHER to be added as a teacher."
- User cannot be STUDENT: "User role must be STUDENT or GUEST."

**403 Scenarios:**
- TEACHER attempting to add member → 403 Forbidden
- STUDENT attempting to add member → 403 Forbidden
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
**CENTER_ADMIN only.** Add multiple members to a group in one atomic request.

**Request Format:**
- `group_id` (UUID): Target group.
- `members` (array of objects): List of 1-100 members to add.
  - Each member object: `{"user_id": int, "role_in_group": "STUDENT" | "TEACHER"}`
  - Both fields required.

**Behavior (atomic, with deduplication):**
1. Duplicate members within the request are deduplicated automatically.
2. Existing members in the group are skipped (no error, included in `skipped_count`).
3. Role validation applied to each user (STUDENT check, TEACHER check, same as single add).
4. Max students check applied: if adding would exceed `group.max_students`, returns **400**.
5. All valid members are created in one bulk insert.
6. `student_count` and `teacher_count` are updated atomically.

**Response Fields:**
- `group_id` (UUID): The target group.
- `created_count` (int): Number of new memberships successfully created.
- `skipped_count` (int): Number of members skipped (already existed or duplicated in request).
- `created_user_ids` (array of int): User IDs of newly created members.

**Example: Request has users 1, 2, 2 (duplicate). User 3 already in group.**
- Result: `created_count: 2, skipped_count: 2, created_user_ids: [1, 2]`

**400 Error Examples:**
- Group full: "Group allows at most 30 students. Adding 5 would make 32."
- User not in center: "User 99 belongs to different center."
- Invalid role: "Item 0: role_in_group must be STUDENT or TEACHER."
- User not found: "Some users not found."

**403 Scenarios:**
- TEACHER attempting bulk add → 403 Forbidden
- STUDENT attempting bulk add → 403 Forbidden
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
            OpenApiParameter(name="group_id", type=str, description="Filter by group UUID"),
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
                description="Bulk add completed. Returns count of created, skipped, and user IDs.",
                examples=[
                    OpenApiExample(
                        "All new members (no skips)",
                        value={
                            "group_id": "550e8400-e29b-41d4-a716-446655440000",
                            "created_count": 3,
                            "skipped_count": 0,
                            "created_user_ids": [10, 11, 12],
                        },
                        response_only=True,
                    ),
                    OpenApiExample(
                        "Mixed (some already existed)",
                        value={
                            "group_id": "550e8400-e29b-41d4-a716-446655440000",
                            "created_count": 2,
                            "skipped_count": 1,
                            "created_user_ids": [10, 11],
                        },
                        response_only=True,
                    ),
                    OpenApiExample(
                        "All skipped (duplicates in request + existing)",
                        value={
                            "group_id": "550e8400-e29b-41d4-a716-446655440000",
                            "created_count": 0,
                            "skipped_count": 2,
                            "created_user_ids": [],
                        },
                        response_only=True,
                    ),
                ],
            ),
            400: OpenApiResponse(
                description="Group full, user not in center, validation error, or invalid request format.",
                examples=[
                    OpenApiExample("Group full", value={"group": "Group allows at most 30 students. Adding 5 would make 32."}, response_only=True),
                    OpenApiExample("User not in center", value={"non_field_errors": ["User 99 belongs to different center."]}, response_only=True),
                    OpenApiExample("Invalid role format", value={"members": "Item 0: role_in_group must be STUDENT or TEACHER."}, response_only=True),
                    OpenApiExample("User not found", value={"non_field_errors": ["Some users not found."]}, response_only=True),
                    OpenApiExample("Missing user_id", value={"members": "Item 1 must have 'user_id'."}, response_only=True),
                ],
            ),
            401: RESP_401,
            403: OpenApiResponse(description="Only CENTER_ADMIN can bulk add. TEACHER/STUDENT receive 403."),
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
            OpenApiExample(
                "Bulk add with deduplication",
                value={
                    "group_id": "550e8400-e29b-41d4-a716-446655440000",
                    "members": [
                        {"user_id": 5, "role_in_group": "STUDENT"},
                        {"user_id": 5, "role_in_group": "STUDENT"},  # Duplicate in request
                        {"user_id": 6, "role_in_group": "STUDENT"},
                    ],
                },
                request_only=True,
            ),
        ],
    ),
)
