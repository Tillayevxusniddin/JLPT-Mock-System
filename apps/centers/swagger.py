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
  **not instantaneous**. The task permanently deletes users (and their S3 avatars),
  tenant schema (DROP SCHEMA CASCADE), invitations, contact requests, subscriptions,
  and the center record (irreversible). The task may take minutes; do not assume 
  immediate deletion.
- **Slug / subdomain:** The center's `slug` (auto-generated from name or set on
  create) determines the tenant's subdomain. Example: slug `edu1` → `edu1.mikan.uz`.
  Users access the center's app at `https://{slug}.mikan.uz`. Slug must be unique.

=============================================================================
ROLE-BASED ACCESS CONTROL (RBAC) MATRIX
=============================================================================

| Endpoint | OWNER | CENTER_ADMIN | TEACHER | STUDENT | GUEST | PUBLIC |
|----------|-------|--------------|---------|---------|-------|--------|
| **Centers (Owner)** |  |  |  |  |  |  |
| POST /owner-centers | ✓ | ✗ 403 | ✗ 403 | ✗ 403 | ✗ 403 | ✗ 401 |
| GET /owner-centers | ✓ | ✗ 403 | ✗ 403 | ✗ 403 | ✗ 403 | ✗ 401 |
| GET /owner-centers/{id} | ✓ | ✗ 403 | ✗ 403 | ✗ 403 | ✗ 403 | ✗ 401 |
| PATCH /owner-centers/{id} | ✓ | ✗ 403 | ✗ 403 | ✗ 403 | ✗ 403 | ✗ 401 |
| DELETE /owner-centers/{id} | ✓ (202) | ✗ 403 | ✗ 403 | ✗ 403 | ✗ 403 | ✗ 401 |
| **Admin Management** |  |  |  |  |  |  |
| GET /owner-center-admins | ✓ | ✗ 403 | ✗ 403 | ✗ 403 | ✗ 403 | ✗ 401 |
| GET /owner-center-admins/{id} | ✓ | ✗ 403 | ✗ 403 | ✗ 403 | ✗ 403 | ✗ 401 |
| POST /owner-center-admins | ✓ | ✗ 403 | ✗ 403 | ✗ 403 | ✗ 403 | ✗ 401 |
| PATCH /owner-center-admins/{id} | ✓ | ✗ 403 | ✗ 403 | ✗ 403 | ✗ 403 | ✗ 401 |
| DELETE /owner-center-admins/{id} | ✓ | ✗ 403 | ✗ 403 | ✗ 403 | ✗ 403 | ✗ 401 |
| **Center Admin's Own Center & Admins** |  |  |  |  |  |  |
| GET /center-admin-centers/{id} | ✗ 403 | ✓ (own) | ✗ 403 | ✗ 403 | ✗ 403 | ✗ 401 |
| PATCH /center-admin-centers/{id} | ✗ 403 | ✓ (own) | ✗ 403 | ✗ 403 | ✗ 403 | ✗ 401 |
| GET /center-admin-centers/{id}/admins | ✗ 403 | ✓ (own) | ✗ 403 | ✗ 403 | ✗ 403 | ✗ 401 |
| POST /center-admin-centers/{id}/admins/add | ✗ 403 | ✓ (own) | ✗ 403 | ✗ 403 | ✗ 403 | ✗ 401 |
| DELETE /center-admin-centers/{id}/admins/{uid} | ✗ 403 | ✓ (own) | ✗ 403 | ✗ 403 | ✗ 403 | ✗ 401 |
| **Invitations & Guests** |  |  |  |  |  |  |
| POST /invitations | ✗ 403 | ✓ | ✗ 403 | ✗ 403 | ✗ 403 | ✗ 401 |
| GET /invitations | ✗ 403 | ✓ (own center) | ✗ 403 | ✗ 403 | ✗ 403 | ✗ 401 |
| POST /invitations/{id}/approve | ✗ 403 | ✓ | ✗ 403 | ✗ 403 | ✗ 403 | ✗ 401 |
| GET /guests | ✗ 403 | ✓ (own center) | ✗ 403 | ✗ 403 | ✗ 403 | ✗ 401 |
| POST /guests/upgrade | ✗ 403 | ✓ | ✗ 403 | ✗ 403 | ✗ 403 | ✗ 401 |
| **Subscriptions** |  |  |  |  |  |  |
| GET /owner-subscriptions | ✓ | ✗ 403 | ✗ 403 | ✗ 403 | ✗ 403 | ✗ 401 |
| GET /owner-subscriptions/{id} | ✓ | ✗ 403 | ✗ 403 | ✗ 403 | ✗ 403 | ✗ 401 |
| PATCH /owner-subscriptions/{id} | ✓ | ✗ 403 | ✗ 403 | ✗ 403 | ✗ 403 | ✗ 401 |
| GET /center-admin-centers/{id}/subscription | ✗ 403 | ✓ (own) | ✗ 403 | ✗ 403 | ✗ 403 | ✗ 401 |
| **Contact Requests** |  |  |  |  |  |  |
| POST /contact-requests | ✓ | ✓ | ✓ | ✓ | ✓ | **✓** |
| GET /owner-contact-requests | ✓ | ✗ 403 | ✗ 403 | ✗ 403 | ✗ 403 | ✗ 401 |
| PATCH /owner-contact-requests/{id} | ✓ | ✗ 403 | ✗ 403 | ✗ 403 | ✗ 403 | ✗ 401 |

**Key Notes:**
- ✓ = Allowed
- ✗ 403 = Forbidden (user authenticated but lacks permission)
- ✗ 401 = Unauthorized (authentication required)
- **✓** = Public endpoint (no authentication required)
- (own) = Can only access own center's resource
- (202) = Returns 202 Accepted for async operations

Subscriptions & Billing:
- **Automatic FREE trial:** Every new center starts with a FREE subscription (2-month trial).
- **Plans & Pricing:** BASIC ($29.99/month), PRO ($79.99/month), ENTERPRISE ($199.99/month).
- **Auto-calculation:** When plan changes, system auto-calculates subscription dates and prices.
- **Auto-suspension:** Daily task checks FREE subscriptions; if expired, center is suspended.
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
    SubscriptionSerializer,
    SubscriptionDetailSerializer,
    SubscriptionUpdateSerializer,
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

**Response Format:**
- **Single (quantity=1):** Returns a single invitation object (not wrapped in array).
- **Bulk (quantity>1):** Returns an array of invitation objects (each with unique `code` and `expires_at` if guest).

**Invitation Types:**
- **Standard (is_guest=False):** TEACHER or STUDENT roles; no expiration.
- **Guest (is_guest=True):** Only STUDENT role; expires in 24 hours; use for one-time signup links.

**Limits:** quantity must be between 1 and 100.
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
            "Single TEACHER invitation (returns object, not array)",
            value={"role": "TEACHER", "is_guest": False, "quantity": 1},
            request_only=True,
        ),
        OpenApiExample(
            "Bulk STUDENT invitations (returns array of 10)",
            value={"role": "STUDENT", "is_guest": False, "quantity": 10},
            request_only=True,
        ),
        OpenApiExample(
            "Bulk guest STUDENT invitations (24h expiry, returns array of 5)",
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

**Batch Optimization:** The API prefetches center admins (all users with role=CENTER_ADMIN and is_active=True) 
per center to avoid N+1 queries. Each item includes:
- `teacher_count`: Integer count of TEACHER users in the center (pre-calculated).
- `centeradmin_emails`: Array of center admin objects with structure: `[{"id": int, "email": str, "first_name": str, "last_name": str}, ...]`
- `center_avatar`: URL to center's avatar image (or null).
- `plan_name`: Display name of current subscription plan (e.g., "Free Trial", "Professional", "Enterprise").

**Filters:** `status` (TRIAL | ACTIVE | SUSPENDED), `is_active` (bool).

**Search:** name, description, address, email.

**Ordering:** created_at, name (default: -created_at).

**Example Response Item:**
```json
{
  "id": 1,
  "center_name": "JLPT Academy Tokyo",
  "center_avatar": "https://cdn.mikan.uz/center_avatars/center_1.jpg",
  "centeradmin_emails": [
    {"id": 10, "email": "admin1@jlpt.tokyo", "first_name": "Hiroshi", "last_name": "Tanaka"},
    {"id": 11, "email": "admin2@jlpt.tokyo", "first_name": "Yuki", "last_name": "Yamamoto"}
  ],
  "teacher_count": 5,
  "plan_name": "Professional",
  "status": "ACTIVE",
  "created_at": "2024-01-15T10:00:00Z"
}
```
"""

OWNER_CENTER_DESTROY_DESCRIPTION = """
**Owner only.** Permanently delete a center. Returns **202 Accepted** (not 204). The deletion runs **asynchronously** 
in a background Celery task and **cannot be canceled or undone**.

**Task steps (executed in order):**
1. **All center users:** Hard-delete all users with `center_id=this_center` (soft-deleted users become permanent).
   - Each user's S3 avatars are deleted.
   - No notification sent to users; access is immediately revoked.
2. **Tenant data:** DROP the PostgreSQL schema for this tenant (CASCADE).
   - All tables, data, indexes in the tenant schema are permanently deleted.
   - This is fast but irrevocable.
3. **Public data:** Delete all invitations, subscriptions, and contact requests for this center.
4. **Center record:** Hard-delete the center (and its avatar S3 file).

**Timing:** The task may take **1-5 minutes** depending on center size. Do not assume the center is removed immediately; 
the API returns 202 while the task runs in the background.

**Response:** Includes the center_id and message so the client knows which center is being deleted.

**Permission:** OWNER only. Teachers and students receive **403 Forbidden**.
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


# =============================================================================
# Owner – Subscriptions
# =============================================================================

OWNER_SUBSCRIPTION_VIEWSET_DESCRIPTION = """
**Owner only.** Manage subscriptions for all centers.

**Subscription Plans & Pricing (Auto-Calculated):**
- **FREE:** $0/month, 2-month trial. Auto-suspends center when trial expires.
- **BASIC:** $29.99/month (1-month billing cycle).
- **PRO:** $79.99/month (1-month billing cycle).
- **ENTERPRISE:** $199.99/month (1-month billing cycle).

**Plan Change Behavior:**
When Owner upgrades a center from FREE → BASIC/PRO/ENTERPRISE:
1. `plan` is updated to new plan.
2. `price` is auto-set to plan's monthly rate.
3. `starts_at` is set to current time (now).
4. `ends_at` is calculated as now + 30 days (for 1-month cycles).
5. `is_active` is set to True.
6. `auto_renew` is set to True (unless plan is FREE).
7. Center's status is updated to ACTIVE (if not already).

**Subscription Lifecycle:**
- **Creation:** Every new center automatically gets a FREE subscription with 2-month expiry.
- **Trial expiry:** A daily Celery task checks FREE subscriptions; if `ends_at < now`, center is automatically suspended.
- **Upgrade:** Owner manually upgrades plan via PATCH or POST /owner-subscriptions/{id}/upgrade/.
- **Manual downgrade:** Owner can change plan back to FREE (not recommended).

**Owner capabilities:**
- List all subscriptions with filtering by plan (FREE/BASIC/PRO/ENTERPRISE) and status (active).
- View detailed subscription info including pricing, dates, days remaining.
- Upgrade/downgrade plans via PATCH or POST upgrade action.
- Search subscriptions by center name.

**Note:** Payment integration is not yet implemented. Subscriptions are manually managed for MVP.
"""

owner_subscription_viewset_schema = extend_schema_view(
    list=extend_schema(
        tags=["Owner – Centers / Admins / Requests"],
        summary="List all subscriptions",
        description="**Owner only.** List all center subscriptions with filtering options.",
        responses={
            200: SubscriptionDetailSerializer(many=True),
            401: RESP_401,
            403: RESP_403,
        },
        parameters=[
            OpenApiParameter(name="plan", description="Filter by plan (FREE, BASIC, PRO, ENTERPRISE)"),
            OpenApiParameter(name="is_active", description="Filter by active status (true/false)"),
            OpenApiParameter(name="search", description="Search by center name"),
        ],
    ),
    retrieve=extend_schema(
        tags=["Owner – Centers / Admins / Requests"],
        summary="Get subscription details",
        description="**Owner only.** Get detailed information about a specific subscription.",
        responses={
            200: SubscriptionDetailSerializer,
            401: RESP_401,
            403: RESP_403,
            404: RESP_404,
        },
        examples=[
            OpenApiExample(
                "FREE subscription (trial)",
                value={
                    "id": 1,
                    "center_id": 1,
                    "center_name": "Test Center",
                    "plan": "FREE",
                    "plan_display": "Free Trial",
                    "price": "0.00",
                    "currency": "USD",
                    "billing_cycle": "monthly",
                    "next_billing_date": "2026-04-10",
                    "starts_at": "2026-02-10T00:00:00Z",
                    "ends_at": "2026-04-10T23:59:59Z",
                    "is_active": True,
                    "auto_renew": False,
                    "is_expired": False,
                    "days_remaining": 59,
                    "created_at": "2026-02-10T00:00:00Z",
                    "updated_at": "2026-02-10T00:00:00Z"
                },
                response_only=True,
            ),
            OpenApiExample(
                "BASIC subscription (upgraded)",
                value={
                    "id": 2,
                    "center_id": 2,
                    "center_name": "JLPT Academy",
                    "plan": "BASIC",
                    "plan_display": "Basic",
                    "price": "29.99",
                    "currency": "USD",
                    "billing_cycle": "monthly",
                    "next_billing_date": "2026-03-12",
                    "starts_at": "2026-02-10T14:30:00Z",
                    "ends_at": "2026-03-12T14:30:00Z",
                    "is_active": True,
                    "auto_renew": True,
                    "is_expired": False,
                    "days_remaining": 30,
                    "created_at": "2026-02-10T00:00:00Z",
                    "updated_at": "2026-02-10T14:30:00Z"
                },
                response_only=True,
            ),
        ],
    ),
    partial_update=extend_schema(
        tags=["Owner – Centers / Admins / Requests"],
        summary="Update subscription plan",
        description="**Owner only.** Update subscription plan (only `plan` field). Dates and pricing auto-calculated.",
        request=SubscriptionUpdateSerializer,
        responses={
            200: SubscriptionDetailSerializer,
            400: RESP_400,
            401: RESP_401,
            403: RESP_403,
            404: RESP_404,
        },
        examples=[
            OpenApiExample(
                "Upgrade FREE to BASIC",
                value={"plan": "BASIC"},
                request_only=True,
            ),
            OpenApiExample(
                "Upgrade BASIC to PRO",
                value={"plan": "PRO"},
                request_only=True,
            ),
            OpenApiExample(
                "Upgrade to ENTERPRISE",
                value={"plan": "ENTERPRISE"},
                request_only=True,
            ),
        ],
    ),
    upgrade=extend_schema(
        tags=["Owner – Centers / Admins / Requests"],
        summary="Upgrade subscription (convenience endpoint)",
        description="**Owner only.** Convenience endpoint to upgrade a subscription plan. Equivalent to PATCH but with better semantics.",
        request=SubscriptionUpdateSerializer,
        responses={
            200: OpenApiResponse(
                description="Subscription upgraded successfully; returns detail with new pricing and dates.",
                examples=[
                    OpenApiExample(
                        "Upgraded to BASIC",
                        value={
                            "detail": "Subscription upgraded to Basic",
                            "subscription": {
                                "id": 1,
                                "center_id": 1,
                                "center_name": "JLPT Academy",
                                "plan": "BASIC",
                                "plan_display": "Basic",
                                "price": "29.99",
                                "currency": "USD",
                                "billing_cycle": "monthly",
                                "starts_at": "2026-02-10T14:45:00Z",
                                "ends_at": "2026-03-12T14:45:00Z",
                                "is_active": True,
                                "auto_renew": True,
                                "days_remaining": 30,
                            }
                        },
                        response_only=True,
                    ),
                    OpenApiExample(
                        "Upgraded to ENTERPRISE",
                        value={
                            "detail": "Subscription upgraded to Enterprise",
                            "subscription": {
                                "id": 3,
                                "center_id": 3,
                                "center_name": "Tokyo Language Institute",
                                "plan": "ENTERPRISE",
                                "plan_display": "Enterprise",
                                "price": "199.99",
                                "currency": "USD",
                                "billing_cycle": "monthly",
                                "starts_at": "2026-02-10T15:00:00Z",
                                "ends_at": "2026-03-12T15:00:00Z",
                                "is_active": True,
                                "auto_renew": True,
                                "days_remaining": 30,
                            }
                        },
                        response_only=True,
                    ),
                ],
            ),
            400: RESP_400,
            401: RESP_401,
            403: RESP_403,
            404: RESP_404,
        },
        examples=[
            OpenApiExample(
                "Upgrade to PRO",
                value={"plan": "PRO"},
                request_only=True,
            ),
        ],
    ),
)


# =============================================================================
# Center Admin – Subscription Detail
# =============================================================================

CENTER_ADMIN_SUBSCRIPTION_DESCRIPTION = """
**Center Admin only.** View your center's subscription details.

This endpoint is **read-only**. Center admins cannot change their subscription plan.
To upgrade, they must contact the platform owner.

Returns:
- Current plan (FREE, BASIC, PRO, ENTERPRISE)
- Pricing and billing information
- Subscription expiry date
- Days remaining in current subscription
- Active status
"""

center_admin_subscription_detail_schema = extend_schema(
    tags=["Center Admin – Invitations / Profile / Guests"],
    summary="Get my center's subscription",
    description=CENTER_ADMIN_SUBSCRIPTION_DESCRIPTION,
    responses={
        200: SubscriptionSerializer,
        401: RESP_401,
        403: OpenApiResponse(description="Only CENTER_ADMIN can view subscription."),
        404: OpenApiResponse(description="No subscription found for your center."),
    },
)


# =============================================================================
# Center Admin – Admin Management (for managing admins in the center)
# =============================================================================

CENTERADMIN_ADMIN_LIST_DESCRIPTION = """
**Center Admin only.** List all admins in your center.

**Role-based Access:**
- **Center Admin:** Can only list admins from their own center.
- **Owner:** Use the Owner endpoint (owner-center-admins) to manage admins globally.

**Data Structure – centeradmin_emails:**
Each admin in the response is returned with the following structure:
```json
{
  "id": 10,
  "email": "admin1@center.com",
  "first_name": "Taro",
  "last_name": "Yamada",
  "center_id": 1,
  "role": "center_admin",
  "created_at": "2026-01-15T10:00:00Z",
  "is_active": true,
  "last_login": "2026-02-08T14:30:00Z"
}
```

**Search:** Filter by email, first_name, or last_name.

**Filtering & Sorting:**
- `search`: Email or name prefix search.
- `ordering`: created_at, email, last_login (default: -created_at).

**Note:** Invitations are managed separately; use the "Invitations" endpoint to invite new admins.
"""

CENTER_ADMIN_ADMIN_ADD_DESCRIPTION = """
**Center Admin only.** Add a new admin to your center.

**How it works:**
1. You provide the email address of the user to add as admin.
2. If the user doesn't exist in the system, a new inactive user is created with a random password.
3. If the user already exists, they are assigned the center_admin role for your center.
4. An invitation email is automatically sent (if email is configured).
5. The new admin must accept the invitation and set their own password.

**Input:**
- `email`: Valid email address (must be unique in the system).

**Response includes:**
- User ID, email, name (if known).
- Center assignment.
- Creation timestamp.
- Detail message confirming the invitation was sent.

**Important:**
- Each admin can only be added once to the center.
- If the email already belongs to an admin in this center, the request fails with a 400 error.
- Bulk invitations should use the center-level invitations endpoint instead.
"""

CENTER_ADMIN_ADMIN_REMOVE_DESCRIPTION = """
**Center Admin only.** Remove an admin from your center.

**Important:**
- The user is **not deleted** from the system; only their center_admin role for this center is removed.
- If the user has other roles, they can still use the system.
- You cannot remove yourself (use a different admin account).
- You cannot remove the center owner if they are also an admin.

**Response:** 204 No Content on success.
"""

center_admin_admin_list_schema = extend_schema(
    tags=["Center Admin – Admins"],
    summary="List admins in my center",
    description=CENTERADMIN_ADMIN_LIST_DESCRIPTION,
    responses={
        200: CenterAdminListSerializer(many=True),
        401: RESP_401,
        403: RESP_403,
    },
    parameters=[
        OpenApiParameter(
            name="search",
            description="Search by email, first_name, or last_name",
        ),
        OpenApiParameter(
            name="ordering",
            description="Order by created_at, email, or last_login (default: -created_at)",
        ),
    ],
    examples=[
        OpenApiExample(
            "List of center admins",
            value=[
                {
                    "id": 2,
                    "email": "admin1@center.com",
                    "first_name": "Taro",
                    "last_name": "Yamada",
                    "center_id": 1,
                    "role": "center_admin",
                    "created_at": "2026-01-15T10:00:00Z",
                    "is_active": True,
                    "last_login": "2026-02-08T14:30:00Z"
                },
                {
                    "id": 3,
                    "email": "admin2@center.com",
                    "first_name": "Hanako",
                    "last_name": "Tanaka",
                    "center_id": 1,
                    "role": "center_admin",
                    "created_at": "2026-01-20T11:00:00Z",
                    "is_active": True,
                    "last_login": "2026-02-07T09:15:00Z"
                }
            ],
            response_only=True,
        ),
    ],
)

center_admin_admin_add_schema = extend_schema(
    tags=["Center Admin – Admins"],
    summary="Add a new admin to my center",
    description=CENTER_ADMIN_ADMIN_ADD_DESCRIPTION,
    request={
        "application/json": {
            "type": "object",
            "required": ["email"],
            "properties": {
                "email": {
                    "type": "string",
                    "format": "email",
                    "description": "Email address of the user to add as admin",
                    "example": "newadmin@center.com"
                }
            }
        }
    },
    responses={
        201: OpenApiResponse(
            description="Admin added successfully; invitation sent",
            examples=[
                OpenApiExample(
                    "New admin created (inactive user)",
                    value={
                        "id": 5,
                        "email": "new.admin@center.com",
                        "first_name": "",
                        "last_name": "",
                        "center_id": 1,
                        "role": "center_admin",
                        "created_at": "2026-02-10T15:30:00Z",
                        "is_active": False,
                        "last_login": None,
                        "detail": "Admin invitation sent to new.admin@center.com"
                    },
                    response_only=True,
                ),
                OpenApiExample(
                    "Existing user assigned as admin",
                    value={
                        "id": 4,
                        "email": "existing.user@gmail.com",
                        "first_name": "John",
                        "last_name": "Doe",
                        "center_id": 1,
                        "role": "center_admin",
                        "created_at": "2026-02-10T15:35:00Z",
                        "is_active": True,
                        "last_login": "2026-02-05T10:00:00Z",
                        "detail": "User assigned to center as admin. Notification sent."
                    },
                    response_only=True,
                ),
            ],
        ),
        400: OpenApiResponse(
            description="Validation error (email invalid, already admin for this center, etc.)",
            examples=[
                OpenApiExample(
                    "Already admin",
                    value={"email": ["This user is already an admin for this center."]},
                    response_only=True,
                ),
                OpenApiExample(
                    "Invalid email",
                    value={"email": ["Enter a valid email address."]},
                    response_only=True,
                ),
            ],
        ),
        401: RESP_401,
        403: RESP_403,
    },
    examples=[
        OpenApiExample(
            "Add new admin by email",
            value={"email": "newadmin@center.com"},
            request_only=True,
        ),
    ],
)

center_admin_admin_remove_schema = extend_schema(
    tags=["Center Admin – Admins"],
    summary="Remove admin from my center",
    description=CENTER_ADMIN_ADMIN_REMOVE_DESCRIPTION,
    responses={
        204: None,
        401: RESP_401,
        403: RESP_403,
        404: RESP_404,
    },
)
