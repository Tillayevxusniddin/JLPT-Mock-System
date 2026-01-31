"""
OpenAPI / Swagger documentation for the Centers app.

Enterprise-level API documentation for the full lifecycle of a Japanese Language
Center (tenant). All endpoints are grouped into three tags for frontend clarity.

Tags:
- **Owner – Centers / Admins / Requests:** Platform owners only (superadmin).
- **Center Admin – Invitations / Profile / Guests:** Center administrators only.
- **Public – Contact:** Open endpoints for the landing page (no auth).

Multi-tenant context:
- Center creation is **asynchronous**: a new center gets `is_ready: false` until
  background migrations complete. Creating a center triggers schema creation and
  a Celery task to run tenant migrations; when done, `is_ready` is set to true.
- Center **destroy** returns **202 Accepted** and queues a background task; it is
  **not instantaneous**. The task permanently deletes users, S3 files, tenant schema,
  invitations, contact requests, and the center record (irreversible).
- **Slug / subdomain:** The center's `slug` (auto-generated from name or set on
  create) determines the tenant's subdomain. Example: slug `edu1` → `edu1.mikan.uz`.
  Users access the center's app at `https://{slug}.mikan.uz`. Slug must be unique.
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

# -----------------------------------------------------------------------------
# Reusable responses
# -----------------------------------------------------------------------------

RESP_400 = OpenApiResponse(description="Bad Request: validation error or invalid payload.")
RESP_401 = OpenApiResponse(description="Unauthorized: authentication required.")
RESP_403 = OpenApiResponse(
    description="Forbidden: TEACHER or STUDENT cannot access this endpoint; Owner or Center Admin only.",
)
RESP_404 = OpenApiResponse(description="Not Found: center, invitation, or contact request not found.")
RESP_202 = OpenApiResponse(description="Accepted: request queued for asynchronous processing.")


# =============================================================================
# Multi-tenant overview (for schema description)
# =============================================================================

MULTI_TENANT_OVERVIEW = """
**Asynchronous center lifecycle**
- **Create center:** Returns 201. The center is created with `is_ready: false`. A background task runs tenant schema migrations; when complete, `is_ready` is set to `true`. The frontend may poll the center detail or show a "Setting up your center" state until `is_ready` is true.
- **Destroy center:** Returns **202 Accepted** (not 204). A background task is queued that permanently deletes: all center users (and their S3 avatars), the tenant PostgreSQL schema, invitations, contact requests, subscriptions, and the center record. **This operation is irreversible.** Do not assume the center is gone immediately; the task may take minutes.

**Slug and subdomain**
- Each center has a unique `slug` (e.g. `edu1`). It is auto-generated from the center name on create (or can be set). The tenant's app is accessed at `https://{slug}.mikan.uz`. Frontend should use `slug` to build tenant-specific URLs.
"""


# =============================================================================
# Center Admin – Invitations / Profile / Guests
# =============================================================================

INVITATION_CREATE_DESCRIPTION = """
**Center Admin only.** Create one or multiple invitations. Teachers and students receive **403 Forbidden**.

- **Single:** Omit `quantity` or set to `1`; response is one invitation object.
- **Bulk:** Set `quantity` between 1 and 100; response is a list of invitations (each with a unique `code`).
- **Guest invitations:** Set `is_guest=True` with `role=STUDENT`; these expire in 24 hours. Use for one-time student signup links.
"""

invitation_create_schema = extend_schema(
    tags=["Center Admin – Invitations / Profile / Guests"],
    summary="Create invitation(s)",
    description=INVITATION_CREATE_DESCRIPTION,
    request=InvitationCreateSerializer,
    responses={
        201: InvitationDetailSerializer,
        400: RESP_400,
        401: RESP_401,
        403: OpenApiResponse(
            description="Forbidden: only CENTER_ADMIN can create invitations.",
        ),
    },
    examples=[
        OpenApiExample(
            "Single TEACHER invitation",
            value={"role": "TEACHER", "is_guest": False, "quantity": 1},
            request_only=True,
        ),
        OpenApiExample(
            "Bulk STUDENT invitations (10 codes)",
            value={"role": "STUDENT", "is_guest": False, "quantity": 10},
            request_only=True,
        ),
        OpenApiExample(
            "Bulk guest STUDENT invitations (24h expiry)",
            value={"role": "STUDENT", "is_guest": True, "quantity": 5},
            request_only=True,
        ),
    ],
)

INVITATION_LIST_DESCRIPTION = """
**Center Admin only.** List invitations for the current center.

**Filters:**
- `role`: TEACHER | STUDENT
- `status`: PENDING | APPROVED | REJECTED | EXPIRED
- `is_used`: true = invitation claimed (target_user set); false = unclaimed

**Search:** `code` (invitation code).

**Ordering:** `created_at`, `expires_at` (default: -created_at).
"""

invitation_list_schema = extend_schema(
    tags=["Center Admin – Invitations / Profile / Guests"],
    summary="List invitations",
    description=INVITATION_LIST_DESCRIPTION,
    parameters=[
        OpenApiParameter(name="role", type=str, enum=["TEACHER", "STUDENT"], description="Filter by invited role"),
        OpenApiParameter(name="status", type=str, enum=["PENDING", "APPROVED", "REJECTED", "EXPIRED"], description="Filter by status"),
        OpenApiParameter(name="is_used", type=bool, description="true = claimed, false = unclaimed"),
        OpenApiParameter(name="search", type=str, description="Search by invitation code"),
        OpenApiParameter(name="ordering", type=str, description="e.g. -created_at, expires_at"),
    ],
    responses={
        200: InvitationDetailSerializer(many=True),
        401: RESP_401,
        403: RESP_403,
    },
)

invitation_approve_schema = extend_schema(
    tags=["Center Admin – Invitations / Profile / Guests"],
    summary="Approve invitation",
    description="Approve a pending invitation (user must have already registered with this code). Transitions GUEST→STUDENT when the invitation was for STUDENT role.",
    request=InvitationApproveSerializer,
    examples=[
        OpenApiExample("Approve by code", value={"code": "ABC123XYZ"}, request_only=True),
    ],
    responses={
        200: OpenApiResponse(
            description="User approved; returns detail with user name.",
            examples=[OpenApiExample("Success", value={"detail": "Jane Doe approved by Center Admin."}, response_only=True)],
        ),
        400: OpenApiResponse(
            description="Invitation not found, already used, or expired.",
            examples=[
                OpenApiExample("Not found", value={"code": ["Invitation not found or already used."]}, response_only=True),
                OpenApiExample("Expired", value={"code": ["Invitation has expired."]}, response_only=True),
            ],
        ),
        401: RESP_401,
        403: OpenApiResponse(description="Only CENTER_ADMIN can approve invitations."),
        404: RESP_404,
    },
)


# =============================================================================
# Owner – Centers / Admins / Requests
# =============================================================================

CENTER_CREATE_DESCRIPTION = """
**Owner only.** Create a new center (tenant). Teachers and students receive **403 Forbidden**.

**Asynchronous setup:** The center is created with `is_ready: false`. A PostgreSQL schema is created and a background task runs tenant migrations. When the task completes, `is_ready` is set to `true`. Poll the center resource or list until `is_ready` is true before directing users to the tenant subdomain.

**Slug / subdomain:** If `slug` is not provided, it is auto-generated from `name` (e.g. "JLPT Academy" → slug `jlpt-academy`). The center will be accessible at `https://{slug}.mikan.uz`. Slug must be unique across the platform.
"""

center_create_schema = extend_schema(
    tags=["Owner – Centers / Admins / Requests"],
    summary="Create center",
    description=CENTER_CREATE_DESCRIPTION,
    request=CenterSerializer,
    responses={
        201: CenterSerializer,
        400: RESP_400,
        401: RESP_401,
        403: RESP_403,
    },
    examples=[
        OpenApiExample(
            "Center with branding and contact",
            value={
                "name": "JLPT Academy Tashkent",
                "description": "Japanese language center for N5–N1 preparation.",
                "email": "contact@jlpt.academy",
                "phone": "+998901234567",
                "website": "https://jlpt.academy",
                "address": "Tashkent, Uzbekistan",
                "primary_color": "#2563EB",
                "status": "TRIAL",
            },
            request_only=True,
        ),
        OpenApiExample(
            "Minimal center",
            value={
                "name": "My Language Center",
                "description": "",
                "status": "TRIAL",
            },
            request_only=True,
        ),
    ],
)

OWNER_CENTER_LIST_DESCRIPTION = """
**Owner only.** List all centers with teacher count and center admin emails.

**List optimization:** The API prefetches center admins (CENTER_ADMIN users) per center to avoid N+1 queries. Each item includes `centeradmin_emails` (id, email, first_name, last_name) and `teacher_count`.

**Filters:** `status` (TRIAL | ACTIVE | SUSPENDED), `is_active` (bool).

**Search:** name, description, address, email.

**Ordering:** created_at, name (default: -created_at).
"""

OWNER_CENTER_DESTROY_DESCRIPTION = """
**Owner only.** Permanently delete a center. Returns **202 Accepted** (not 204). The deletion runs **asynchronously** in a background task.

**Irreversible.** The task will:
1. **Users:** Hard-delete all users belonging to this center (including S3 avatars).
2. **Public data:** Delete invitations, contact requests (by center name), subscriptions linked to this center.
3. **Tenant schema:** DROP the PostgreSQL schema for this tenant (all tenant tables and data).
4. **Center:** Hard-delete the center record and its avatar from S3.

Do not assume the center is removed immediately; poll or avoid reusing the center id until the task has completed. Teachers and students receive **403** if they attempt this endpoint.
"""

owner_center_viewset_schema = extend_schema_view(
    list=extend_schema(
        tags=["Owner – Centers / Admins / Requests"],
        summary="List all centers",
        description=OWNER_CENTER_LIST_DESCRIPTION,
        parameters=[
            OpenApiParameter(name="status", type=str, enum=["TRIAL", "ACTIVE", "SUSPENDED"], description="Filter by center status"),
            OpenApiParameter(name="is_active", type=bool),
            OpenApiParameter(name="search", type=str, description="Search name, description, address, email"),
            OpenApiParameter(name="ordering", type=str, description="e.g. -created_at, name"),
        ],
        responses={
            200: OwnerCenterListSerializer(many=True),
            401: RESP_401,
            403: RESP_403,
        },
    ),
    retrieve=extend_schema(
        tags=["Owner – Centers / Admins / Requests"],
        summary="Get center",
        responses={200: OwnerCenterSerializer, 401: RESP_401, 403: RESP_403, 404: RESP_404},
    ),
    create=extend_schema(
        tags=["Owner – Centers / Admins / Requests"],
        summary="Create center (viewset)",
        description=CENTER_CREATE_DESCRIPTION,
        request=OwnerCenterSerializer,
        responses={201: OwnerCenterSerializer, 400: RESP_400, 401: RESP_401, 403: RESP_403},
    ),
    update=extend_schema(
        tags=["Owner – Centers / Admins / Requests"],
        summary="Update center",
        request=OwnerCenterSerializer,
        responses={200: OwnerCenterSerializer, 400: RESP_400, 401: RESP_401, 403: RESP_403, 404: RESP_404},
    ),
    partial_update=extend_schema(
        tags=["Owner – Centers / Admins / Requests"],
        summary="Partial update center",
        request=OwnerCenterSerializer,
        responses={200: OwnerCenterSerializer, 400: RESP_400, 401: RESP_401, 403: RESP_403, 404: RESP_404},
    ),
    destroy=extend_schema(
        tags=["Owner – Centers / Admins / Requests"],
        summary="Hard delete center (async, irreversible)",
        description=OWNER_CENTER_DESTROY_DESCRIPTION,
        responses={
            202: OpenApiResponse(
                description="Deletion queued; center will be permanently removed by a background task.",
                examples=[
                    OpenApiExample(
                        "Accepted",
                        value={
                            "status": "deletion_queued",
                            "message": "Center 'JLPT Academy' is being permanently deleted. Users and Schema will be removed shortly.",
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
        tags=["Owner – Centers / Admins / Requests"],
        summary="Suspend center",
        description="Set center status to SUSPENDED and is_active to False. Center users cannot log in.",
        responses={200: OpenApiResponse(description="Center suspended."), 401: RESP_401, 403: RESP_403, 404: RESP_404},
    ),
    activate=extend_schema(
        tags=["Owner – Centers / Admins / Requests"],
        summary="Activate center",
        description="Set center status to ACTIVE and is_active to True.",
        responses={200: OpenApiResponse(description="Center activated."), 401: RESP_401, 403: RESP_403, 404: RESP_404},
    ),
)


# ---- Owner: Center admins ----

center_admin_create_schema = extend_schema(
    tags=["Owner – Centers / Admins / Requests"],
    summary="Create center admin (standalone)",
    description="Create a CENTER_ADMIN user for a center. Requires center_id in path. Owner only.",
    request=CenterAdminCreateSerializer,
    responses={201: CenterAdminDetailSerializer, 400: RESP_400, 401: RESP_401, 403: RESP_403, 404: RESP_404},
    examples=[
        OpenApiExample(
            "Create admin",
            value={
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
**Owner only.** List, create, update, or delete center admins (CENTER_ADMIN users across all centers).

**Filters:** `is_active`, `is_approved`, `center` (center id).

**Search:** first_name, last_name, email.

**Ordering:** created_at, last_login (default: -created_at).
"""

owner_center_admin_viewset_schema = extend_schema_view(
    list=extend_schema(
        tags=["Owner – Centers / Admins / Requests"],
        summary="List center admins",
        description=OWNER_CENTER_ADMIN_DESCRIPTION,
        parameters=[
            OpenApiParameter(name="is_active", type=bool),
            OpenApiParameter(name="is_approved", type=bool),
            OpenApiParameter(name="center", type=int, description="Filter by center id"),
            OpenApiParameter(name="search", type=str, description="Search first_name, last_name, email"),
            OpenApiParameter(name="ordering", type=str, description="e.g. -created_at, last_login"),
        ],
        responses={200: CenterAdminListSerializer(many=True), 401: RESP_401, 403: RESP_403},
    ),
    retrieve=extend_schema(
        tags=["Owner – Centers / Admins / Requests"],
        summary="Get center admin",
        responses={200: CenterAdminDetailSerializer, 401: RESP_401, 403: RESP_403, 404: RESP_404},
    ),
    create=extend_schema(
        tags=["Owner – Centers / Admins / Requests"],
        summary="Create center admin",
        description="Requires center_id (or center) in request body. Owner only.",
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
    ),
    update=extend_schema(
        tags=["Owner – Centers / Admins / Requests"],
        summary="Update center admin",
        request=CenterAdminUpdateSerializer,
        responses={200: CenterAdminDetailSerializer, 400: RESP_400, 401: RESP_401, 403: RESP_403, 404: RESP_404},
    ),
    partial_update=extend_schema(
        tags=["Owner – Centers / Admins / Requests"],
        summary="Partial update center admin",
        request=CenterAdminUpdateSerializer,
        responses={200: CenterAdminDetailSerializer, 400: RESP_400, 401: RESP_401, 403: RESP_403, 404: RESP_404},
    ),
    destroy=extend_schema(
        tags=["Owner – Centers / Admins / Requests"],
        summary="Delete center admin (soft delete)",
        responses={200: OpenApiResponse(description="Center admin soft-deleted."), 401: RESP_401, 403: RESP_403, 404: RESP_404},
    ),
)


# =============================================================================
# Center Admin – Invitations / Profile / Guests (profile & avatar)
# =============================================================================

center_admin_center_viewset_schema = extend_schema_view(
    retrieve=extend_schema(
        tags=["Center Admin – Invitations / Profile / Guests"],
        summary="Get my center",
        description="Center Admin retrieves their own center profile. TEACHER/STUDENT receive 403.",
        responses={200: CenterSerializer, 401: RESP_401, 403: RESP_403, 404: RESP_404},
    ),
    update=extend_schema(
        tags=["Center Admin – Invitations / Profile / Guests"],
        summary="Update my center",
        request=CenterSerializer,
        responses={200: CenterSerializer, 400: RESP_400, 401: RESP_401, 403: RESP_403, 404: RESP_404},
    ),
    partial_update=extend_schema(
        tags=["Center Admin – Invitations / Profile / Guests"],
        summary="Partial update my center",
        request=CenterSerializer,
        responses={200: CenterSerializer, 400: RESP_400, 401: RESP_401, 403: RESP_403, 404: RESP_404},
    ),
)

center_avatar_upload_schema = extend_schema(
    tags=["Center Admin – Invitations / Profile / Guests"],
    summary="Upload center avatar",
    description="Upload or replace the current center's avatar. **Content-Type:** multipart/form-data; field name: `avatar`. Center Admin only.",
    request={
        "multipart/form-data": {
            "type": "object",
            "required": ["avatar"],
            "properties": {
                "avatar": {"type": "string", "format": "binary", "description": "Image file (field name: avatar)"},
            },
        }
    },
    responses={200: CenterSerializer, 400: RESP_400, 401: RESP_401, 403: RESP_403, 404: RESP_404},
)


# =============================================================================
# Public – Contact
# =============================================================================

CONTACT_REQUEST_CREATE_DESCRIPTION = """
**Public (no authentication).** Submit a contact or join request for a center. Used on the landing page.

Duplicate check: if a request with the same center_name + phone_number (or same phone_number) already exists with status PENDING or CONTACTED, the API returns 400. No auth required.
"""

contact_request_create_schema = extend_schema(
    tags=["Public – Contact"],
    summary="Create contact request",
    description=CONTACT_REQUEST_CREATE_DESCRIPTION,
    request=ContactRequestCreateSerializer,
    responses={
        201: ContactRequestListSerializer,
        400: OpenApiResponse(
            description="Validation error or duplicate request.",
            examples=[
                OpenApiExample(
                    "Duplicate",
                    value={"detail": "You have already contacted us. We will get back to you soon."},
                    response_only=True,
                ),
            ],
        ),
    },
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
# Owner – Contact requests
# =============================================================================

OWNER_CONTACT_REQUEST_DESCRIPTION = """
**Owner only.** List, retrieve, update, or delete contact requests from the landing page.

**Filters:** `status` (PENDING | CONTACTED | RESOLVED | REJECTED).

**Search:** full_name, phone_number, message, center_name.

**Ordering:** created_at, status (default: -created_at).
"""

owner_contact_request_viewset_schema = extend_schema_view(
    list=extend_schema(
        tags=["Owner – Centers / Admins / Requests"],
        summary="List contact requests",
        description=OWNER_CONTACT_REQUEST_DESCRIPTION,
        parameters=[
            OpenApiParameter(name="status", type=str, enum=["PENDING", "CONTACTED", "RESOLVED", "REJECTED"]),
            OpenApiParameter(name="search", type=str, description="Search full_name, phone_number, message, center_name"),
            OpenApiParameter(name="ordering", type=str, description="e.g. -created_at, status"),
        ],
        responses={200: ContactRequestListSerializer(many=True), 401: RESP_401, 403: RESP_403},
    ),
    retrieve=extend_schema(
        tags=["Owner – Centers / Admins / Requests"],
        summary="Get contact request",
        responses={200: ContactRequestListSerializer, 401: RESP_401, 403: RESP_403, 404: RESP_404},
    ),
    partial_update=extend_schema(
        tags=["Owner – Centers / Admins / Requests"],
        summary="Update contact request (e.g. status)",
        request=ContactRequestUpdateSerializer,
        responses={200: ContactRequestListSerializer, 400: RESP_400, 401: RESP_401, 403: RESP_403, 404: RESP_404},
    ),
    destroy=extend_schema(
        tags=["Owner – Centers / Admins / Requests"],
        summary="Delete contact request (soft delete)",
        responses={200: OpenApiResponse(description="Contact request deleted."), 401: RESP_401, 403: RESP_403, 404: RESP_404},
    ),
)


# =============================================================================
# Center Admin – Guests
# =============================================================================

GUEST_LIST_DESCRIPTION = """
**Center Admin only.** List GUEST users in the current center. TEACHER and STUDENT receive **403 Forbidden**.

**Search:** email, first_name, last_name.

**Ordering:** created_at, email (default: -created_at).
"""

guest_list_schema = extend_schema(
    tags=["Center Admin – Invitations / Profile / Guests"],
    summary="List guests",
    description=GUEST_LIST_DESCRIPTION,
    parameters=[
        OpenApiParameter(name="search", type=str, description="Search email, first_name, last_name"),
        OpenApiParameter(name="ordering", type=str, description="e.g. -created_at, email"),
    ],
    responses={200: GuestListSerializer(many=True), 401: RESP_401, 403: RESP_403},
)

GUEST_UPGRADE_DESCRIPTION = """
**Center Admin only.** Convert a GUEST user to STUDENT. The user must belong to the same center as the requester. Sends payload with `user_id` (the GUEST user's id). Returns the updated user object and a success message.
"""

guest_upgrade_schema = extend_schema(
    tags=["Center Admin – Invitations / Profile / Guests"],
    summary="Upgrade guest to student",
    description=GUEST_UPGRADE_DESCRIPTION,
    request=GuestUpgradeSerializer,
    responses={
        200: OpenApiResponse(
            description="Guest upgraded to STUDENT; returns detail and full user payload.",
            examples=[
                OpenApiExample(
                    "Success",
                    value={
                        "detail": "Guest user 'Jane Doe' has been upgraded to STUDENT.",
                        "user": {
                            "id": 42,
                            "email": "jane@example.com",
                            "first_name": "Jane",
                            "last_name": "Doe",
                            "role": "STUDENT",
                            "is_approved": True,
                        },
                    },
                    response_only=True,
                ),
            ],
        ),
        400: OpenApiResponse(
            description="User not found, not a GUEST, or belongs to another center.",
            examples=[
                OpenApiExample("Not guest", value={"user_id": ["User not found or is not a GUEST."]}, response_only=True),
                OpenApiExample("Wrong center", value={"user_id": ["User belongs to a different center."]}, response_only=True),
            ],
        ),
        401: RESP_401,
        403: OpenApiResponse(description="Only CENTER_ADMIN can upgrade guests."),
    },
    examples=[
        OpenApiExample(
            "Upgrade by user id",
            value={"user_id": 42},
            request_only=True,
        ),
    ],
)
