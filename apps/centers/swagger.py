# apps/centers/swagger.py
"""
OpenAPI / Swagger documentation for the centers app.

Role-based API entry points:
- **Owner (Platform Admin):** All centers CRUD, suspend/activate, hard delete (202),
  center admins CRUD, contact requests CRUD.
- **Center Admin:** Own center profile, invitations (create/list/approve), guests list/upgrade.
- **Public/Guest:** Contact request creation; join via invitation (auth app).
"""
from drf_spectacular.utils import (
    OpenApiExample,
    OpenApiParameter,
    OpenApiResponse,
    extend_schema,
    extend_schema_view,
)

from apps.centers.serializers import (
    CenterAdminCreateSerializer,
    CenterAdminDetailSerializer,
    CenterAdminListSerializer,
    CenterAdminUpdateSerializer,
    CenterSerializer,
    ContactRequestCreateSerializer,
    ContactRequestListSerializer,
    ContactRequestUpdateSerializer,
    GuestListSerializer,
    GuestUpgradeSerializer,
    InvitationApproveSerializer,
    InvitationCreateSerializer,
    InvitationDetailSerializer,
    OwnerCenterListSerializer,
    OwnerCenterSerializer,
)

# ---- Reusable responses ----
RESP_400 = OpenApiResponse(description="Validation error or bad request.")
RESP_401 = OpenApiResponse(description="Authentication required.")
RESP_403 = OpenApiResponse(description="Insufficient permissions (e.g. not CENTER_ADMIN or Owner).")
RESP_404 = OpenApiResponse(description="Resource not found (e.g. center or invitation).")
RESP_202 = OpenApiResponse(description="Request accepted; processing asynchronously (e.g. center deletion).")


# =============================================================================
# CENTER ADMIN: Invitations
# =============================================================================

INVITATION_CREATE_DESCRIPTION = """
**Center Admin only.** Create one or multiple invitations (bulk via `quantity`).

- **Single:** Omit `quantity` or set to 1; returns one invitation.
- **Bulk:** Set `quantity` (1–100); returns a list of invitations.
- **Guest invitations:** Set `is_guest=True` with `role=STUDENT`; expires in 24h.
"""

invitation_create_schema = extend_schema(
    tags=["Center Admin – Invitations"],
    summary="Create invitation(s)",
    description=INVITATION_CREATE_DESCRIPTION,
    request=InvitationCreateSerializer,
    responses={
        201: InvitationDetailSerializer,
        400: RESP_400,
        401: RESP_401,
        403: RESP_403,
    },
    examples=[
        OpenApiExample(
            "Single TEACHER invitation",
            value={"role": "TEACHER", "is_guest": False, "quantity": 1},
            request_only=True,
        ),
        OpenApiExample(
            "Bulk STUDENT guest invitations",
            value={"role": "STUDENT", "is_guest": True, "quantity": 10},
            request_only=True,
        ),
    ],
)

INVITATION_LIST_DESCRIPTION = """
**Center Admin only.** List invitations for the current center.

**Filters (DjangoFilterBackend):**
- `role`: TEACHER | STUDENT
- `status`: PENDING | APPROVED | REJECTED | EXPIRED
- `is_used`: true | false (claimed vs unclaimed)
**Search:** `code`
**Ordering:** `created_at`, `expires_at` (default: -created_at)
"""

invitation_list_schema = extend_schema(
    tags=["Center Admin – Invitations"],
    summary="List invitations",
    description=INVITATION_LIST_DESCRIPTION,
    parameters=[
        OpenApiParameter(name="role", type=str, enum=["TEACHER", "STUDENT"], description="Filter by role"),
        OpenApiParameter(name="status", type=str, enum=["PENDING", "APPROVED", "REJECTED", "EXPIRED"]),
        OpenApiParameter(name="is_used", type=bool, description="true = claimed, false = unclaimed"),
        OpenApiParameter(name="search", type=str, description="Search by code"),
        OpenApiParameter(name="ordering", type=str, description="e.g. -created_at, expires_at"),
    ],
    responses={200: InvitationDetailSerializer(many=True), 401: RESP_401, 403: RESP_403},
)

invitation_approve_schema = extend_schema(
    tags=["Center Admin – Invitations"],
    summary="Approve invitation",
    description="Approve a pending invitation (user already registered). Transitions GUEST→STUDENT when applicable.",
    request=InvitationApproveSerializer,
    responses={
        200: OpenApiResponse(description="User approved; message with user name."),
        400: RESP_400,
        401: RESP_401,
        403: RESP_403,
        404: RESP_404,
    },
)


# =============================================================================
# OWNER: Center CRUD & lifecycle
# =============================================================================

CENTER_CREATE_DESCRIPTION = """
**Owner only.** Create a new center (tenant). Triggers schema creation and async migrations;
`is_ready` becomes true when migrations complete.
"""

center_create_schema = extend_schema(
    tags=["Owner – Centers"],
    summary="Create center (standalone)",
    description=CENTER_CREATE_DESCRIPTION,
    request=CenterSerializer,
    responses={201: CenterSerializer, 400: RESP_400, 401: RESP_401, 403: RESP_403},
    examples=[
        OpenApiExample(
            "Center with branding and contact",
            value={
                "name": "JLPT Academy Tashkent",
                "description": "Japanese language center.",
                "email": "contact@jlpt.academy",
                "phone": "+998901234567",
                "website": "https://jlpt.academy",
                "address": "Tashkent, Uzbekistan",
                "primary_color": "#2563EB",
                "status": "TRIAL",
            },
            request_only=True,
        ),
    ],
)

OWNER_CENTER_LIST_DESCRIPTION = """
**Owner only.** List all centers with teacher count and center admin emails.

**Filters:** `status` (TRIAL | ACTIVE | SUSPENDED), `is_active` (bool)
**Search:** name, description, address, email
**Ordering:** created_at, name (default: -created_at)
"""

owner_center_viewset_schema = extend_schema_view(
    list=extend_schema(
        tags=["Owner – Centers"],
        summary="List all centers",
        description=OWNER_CENTER_LIST_DESCRIPTION,
        parameters=[
            OpenApiParameter(name="status", type=str, enum=["TRIAL", "ACTIVE", "SUSPENDED"]),
            OpenApiParameter(name="is_active", type=bool),
            OpenApiParameter(name="search", type=str),
            OpenApiParameter(name="ordering", type=str),
        ],
        responses={200: OwnerCenterListSerializer(many=True), 401: RESP_401, 403: RESP_403},
    ),
    retrieve=extend_schema(
        tags=["Owner – Centers"],
        summary="Get center",
        responses={200: OwnerCenterSerializer, 401: RESP_401, 403: RESP_403, 404: RESP_404},
    ),
    create=extend_schema(
        tags=["Owner – Centers"],
        summary="Create center",
        request=OwnerCenterSerializer,
        responses={201: OwnerCenterSerializer, 400: RESP_400, 401: RESP_401, 403: RESP_403},
    ),
    update=extend_schema(
        tags=["Owner – Centers"],
        summary="Update center",
        request=OwnerCenterSerializer,
        responses={200: OwnerCenterSerializer, 400: RESP_400, 401: RESP_401, 403: RESP_403, 404: RESP_404},
    ),
    partial_update=extend_schema(
        tags=["Owner – Centers"],
        summary="Partial update center",
        request=OwnerCenterSerializer,
        responses={200: OwnerCenterSerializer, 400: RESP_400, 401: RESP_401, 403: RESP_403, 404: RESP_404},
    ),
    destroy=extend_schema(
        tags=["Owner – Centers"],
        summary="Hard delete center (async)",
        description=(
            "Returns **202 Accepted**. Queues a background task that permanently deletes: "
            "all center users (and S3 avatars), tenant schema, invitations, contact requests, "
            "subscriptions, and the center record. Irreversible."
        ),
        responses={
            202: OpenApiResponse(
                description="Deletion queued.",
                examples=[
                    OpenApiExample(
                        "Accepted",
                        value={
                            "status": "deletion_queued",
                            "message": "Center 'X' is being permanently deleted. Users and Schema will be removed shortly.",
                            "center_id": 1,
                        },
                        response_only=True,
                    ),
                ],
            ),
            401: RESP_401,
            403: RESP_403,
            404: RESP_404,
        },
    ),
    suspend=extend_schema(
        tags=["Owner – Centers"],
        summary="Suspend center",
        description="Set center status to SUSPENDED and is_active to False.",
        responses={200: OpenApiResponse(description="Center suspended."), 401: RESP_401, 403: RESP_403, 404: RESP_404},
    ),
    activate=extend_schema(
        tags=["Owner – Centers"],
        summary="Activate center",
        description="Set center status to ACTIVE and is_active to True.",
        responses={200: OpenApiResponse(description="Center activated."), 401: RESP_401, 403: RESP_403, 404: RESP_404},
    ),
)


# =============================================================================
# OWNER: Center admins
# =============================================================================

center_admin_create_schema = extend_schema(
    tags=["Owner – Center Admins"],
    summary="Create center admin",
    description="Create a CENTER_ADMIN user for a center. Requires center_id in body (or path).",
    request=CenterAdminCreateSerializer,
    responses={201: CenterAdminDetailSerializer, 400: RESP_400, 401: RESP_401, 403: RESP_403, 404: RESP_404},
    examples=[
        OpenApiExample(
            "Create admin",
            value={
                "center_id": 1,
                "email": "admin@center.com",
                "first_name": "Admin",
                "last_name": "User",
                "password": "securePass123",
            },
            request_only=True,
        ),
    ],
)

OWNER_CENTER_ADMIN_DESCRIPTION = """
**Owner only.** List/create/update/delete center admins (CENTER_ADMIN users).

**Filters:** `is_active`, `is_approved`, `center`
**Search:** first_name, last_name, email
**Ordering:** created_at, last_login (default: -created_at)
"""

owner_center_admin_viewset_schema = extend_schema_view(
    list=extend_schema(
        tags=["Owner – Center Admins"],
        summary="List center admins",
        description=OWNER_CENTER_ADMIN_DESCRIPTION,
        parameters=[
            OpenApiParameter(name="is_active", type=bool),
            OpenApiParameter(name="is_approved", type=bool),
            OpenApiParameter(name="center", type=int),
            OpenApiParameter(name="search", type=str),
            OpenApiParameter(name="ordering", type=str),
        ],
        responses={200: CenterAdminListSerializer(many=True), 401: RESP_401, 403: RESP_403},
    ),
    retrieve=extend_schema(
        tags=["Owner – Center Admins"],
        summary="Get center admin",
        responses={200: CenterAdminDetailSerializer, 401: RESP_401, 403: RESP_403, 404: RESP_404},
    ),
    create=extend_schema(
        tags=["Owner – Center Admins"],
        summary="Create center admin",
        request=CenterAdminCreateSerializer,
        responses={201: CenterAdminDetailSerializer, 400: RESP_400, 401: RESP_401, 403: RESP_403, 404: RESP_404},
    ),
    update=extend_schema(
        tags=["Owner – Center Admins"],
        summary="Update center admin",
        request=CenterAdminUpdateSerializer,
        responses={200: CenterAdminDetailSerializer, 400: RESP_400, 401: RESP_401, 403: RESP_403, 404: RESP_404},
    ),
    partial_update=extend_schema(
        tags=["Owner – Center Admins"],
        summary="Partial update center admin",
        request=CenterAdminUpdateSerializer,
        responses={200: CenterAdminDetailSerializer, 400: RESP_400, 401: RESP_401, 403: RESP_403, 404: RESP_404},
    ),
    destroy=extend_schema(
        tags=["Owner – Center Admins"],
        summary="Delete center admin (soft delete)",
        responses={200: OpenApiResponse(description="Center admin deleted."), 401: RESP_401, 403: RESP_403, 404: RESP_404},
    ),
)


# =============================================================================
# CENTER ADMIN: Own center profile
# =============================================================================

center_admin_center_viewset_schema = extend_schema_view(
    retrieve=extend_schema(
        tags=["Center Admin – My Center"],
        summary="Get my center",
        description="Center Admin retrieves their own center profile.",
        responses={200: CenterSerializer, 401: RESP_401, 403: RESP_403, 404: RESP_404},
    ),
    update=extend_schema(
        tags=["Center Admin – My Center"],
        summary="Update my center",
        request=CenterSerializer,
        responses={200: CenterSerializer, 400: RESP_400, 401: RESP_401, 403: RESP_403, 404: RESP_404},
    ),
    partial_update=extend_schema(
        tags=["Center Admin – My Center"],
        summary="Partial update my center",
        request=CenterSerializer,
        responses={200: CenterSerializer, 400: RESP_400, 401: RESP_401, 403: RESP_403, 404: RESP_404},
    ),
)

center_avatar_upload_schema = extend_schema(
    tags=["Center Admin – My Center"],
    summary="Upload center avatar",
    description="Multipart form; field name: `avatar`.",
    request={"multipart/form-data": {"type": "object", "properties": {"avatar": {"type": "string", "format": "binary"}}, "required": ["avatar"]}},
    responses={200: CenterSerializer, 400: RESP_400, 401: RESP_401, 403: RESP_403, 404: RESP_404},
)


# =============================================================================
# PUBLIC: Contact requests
# =============================================================================

CONTACT_REQUEST_CREATE_DESCRIPTION = """
**Public (no auth).** Submit a contact/join request for a center. Duplicate check by center_name + phone_number.
"""

contact_request_create_schema = extend_schema(
    tags=["Public – Contact"],
    summary="Create contact request",
    description=CONTACT_REQUEST_CREATE_DESCRIPTION,
    request=ContactRequestCreateSerializer,
    responses={201: ContactRequestListSerializer, 400: RESP_400},
    examples=[
        OpenApiExample(
            "Request to join",
            value={
                "center_name": "JLPT Academy",
                "full_name": "John Doe",
                "phone_number": "+998901234567",
                "message": "I would like to join as a student.",
            },
            request_only=True,
        ),
    ],
)


# =============================================================================
# OWNER: Contact requests
# =============================================================================

OWNER_CONTACT_REQUEST_DESCRIPTION = """
**Owner only.** List/retrieve/update/delete contact requests.

**Filters:** `status` (PENDING | CONTACTED | RESOLVED | REJECTED)
**Search:** full_name, phone, message (and email if present)
**Ordering:** created_at, status (default: -created_at)
"""

owner_contact_request_viewset_schema = extend_schema_view(
    list=extend_schema(
        tags=["Owner – Contact Requests"],
        summary="List contact requests",
        description=OWNER_CONTACT_REQUEST_DESCRIPTION,
        parameters=[
            OpenApiParameter(name="status", type=str, enum=["PENDING", "CONTACTED", "RESOLVED", "REJECTED"]),
            OpenApiParameter(name="search", type=str),
            OpenApiParameter(name="ordering", type=str),
        ],
        responses={200: ContactRequestListSerializer(many=True), 401: RESP_401, 403: RESP_403},
    ),
    retrieve=extend_schema(
        tags=["Owner – Contact Requests"],
        summary="Get contact request",
        responses={200: ContactRequestListSerializer, 401: RESP_401, 403: RESP_403, 404: RESP_404},
    ),
    partial_update=extend_schema(
        tags=["Owner – Contact Requests"],
        summary="Update contact request (e.g. status)",
        request=ContactRequestUpdateSerializer,
        responses={200: ContactRequestListSerializer, 400: RESP_400, 401: RESP_401, 403: RESP_403, 404: RESP_404},
    ),
    destroy=extend_schema(
        tags=["Owner – Contact Requests"],
        summary="Delete contact request (soft delete)",
        responses={200: OpenApiResponse(description="Contact request deleted."), 401: RESP_401, 403: RESP_403, 404: RESP_404},
    ),
)


# =============================================================================
# CENTER ADMIN: Guests
# =============================================================================

GUEST_LIST_DESCRIPTION = """
**Center Admin only.** List GUEST users in the current center.

**Search:** email, first_name, last_name
**Ordering:** created_at, email (default: -created_at)
"""

guest_list_schema = extend_schema(
    tags=["Center Admin – Guests"],
    summary="List guests",
    description=GUEST_LIST_DESCRIPTION,
    parameters=[
        OpenApiParameter(name="search", type=str),
        OpenApiParameter(name="ordering", type=str),
    ],
    responses={200: GuestListSerializer(many=True), 401: RESP_401, 403: RESP_403},
)

guest_upgrade_schema = extend_schema(
    tags=["Center Admin – Guests"],
    summary="Upgrade guest to student",
    description="Convert a GUEST user to STUDENT; creates an APPROVED invitation and sets is_approved=True.",
    request=GuestUpgradeSerializer,
    responses={
        200: OpenApiResponse(
            description="Guest upgraded; returns detail and user payload.",
        ),
        400: RESP_400,
        401: RESP_401,
        403: RESP_403,
    },
    examples=[
        OpenApiExample("Request", value={"user_id": 42}, request_only=True),
    ],
)
