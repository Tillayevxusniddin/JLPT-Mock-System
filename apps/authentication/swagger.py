"""
OpenAPI / Swagger documentation for the Authentication app.

Master-level integration guide for Frontend developers. All request/response
examples, error scenarios, and role-based behavior are documented here.

Multi-tenant context:
- Login and Register are tenant-aware: main domain (Owner) vs subdomain (Center).
- Email uniqueness is per center: same email can exist in different centers.
- UserViewSet: CENTER_ADMIN sees all center users (full CRUD); TEACHER sees only
  students in groups they teach (list/retrieve only). GUEST/STUDENT cannot access
  UserViewSet (403).
"""
from drf_spectacular.utils import (
    OpenApiExample,
    OpenApiParameter,
    OpenApiResponse,
    extend_schema,
    extend_schema_view,
)

from apps.authentication.serializers import (
    LoginSerializer,
    LogoutRequestSerializer,
    PasswordResetConfirmSerializer,
    PasswordResetRequestSerializer,
    RegisterSerializer,
    UpdatePasswordSerializer,
    UserCreateSerializer,
    UserListSerializer,
    UserManagementSerializer,
    UserSerializer,
)


# -----------------------------------------------------------------------------
# Reusable response blocks
# -----------------------------------------------------------------------------

RESP_400_INVALID = OpenApiResponse(
    description="Bad Request: validation error or invalid payload.",
)
RESP_401_UNAUTHORIZED = OpenApiResponse(
    description="Unauthorized: missing, invalid, or expired JWT.",
)
RESP_403_FORBIDDEN = OpenApiResponse(
    description="Forbidden: authenticated but insufficient permissions.",
)
RESP_429_THROTTLED = OpenApiResponse(
    description="Too Many Requests: rate limit or Axes lockout. Retry after the indicated delay.",
)


# =============================================================================
# Register
# =============================================================================

REGISTER_DESCRIPTION = """
Register a new user using an **invitation code** issued by a center.

**Subdomain context:** Call this from the center's subdomain (e.g. `edu1.mikan.uz`) so the
invitation is resolved in that center's context. The same invitation code cannot be used on
a different subdomain.

**Email uniqueness:** Email must be unique **within that center only**. The same email can
exist in another center. Duplicate email in the same center returns `400`.

**Flow:** Registration is atomic. After success, the user must wait for a center
administrator to approve the account before they can log in.
"""

register_schema = extend_schema(
    tags=["Authentication"],
    summary="Register with invitation code",
    description=REGISTER_DESCRIPTION,
    request=RegisterSerializer,
    examples=[
        OpenApiExample(
            "Valid registration (student)",
            value={
                "email": "student@example.com",
                "first_name": "Jane",
                "last_name": "Doe",
                "password": "SecurePass123!",
                "invitation_code": "INV-abc123xyz789",
            },
            request_only=True,
        ),
        OpenApiExample(
            "Minimal (only required fields)",
            value={
                "email": "newuser@center.edu",
                "password": "min6chars",
                "invitation_code": "INV-xyz",
            },
            request_only=True,
        ),
    ],
    responses={
        201: OpenApiResponse(
            description="Registration successful; account pending center admin approval.",
            examples=[
                OpenApiExample(
                    "Success",
                    value={
                        "detail": "Registration successful. Please wait for center administrator approval.",
                        "email": "student@example.com",
                        "role": "STUDENT",
                    },
                    response_only=True,
                ),
            ],
        ),
        400: OpenApiResponse(
            description="Validation error. See body for field-specific messages.",
            examples=[
                OpenApiExample(
                    "Invalid invitation code",
                    value={"invitation_code": ["Invalid code."]},
                    response_only=True,
                ),
                OpenApiExample(
                    "Invitation already claimed",
                    value={"invitation_code": ["Invitation already claimed."]},
                    response_only=True,
                ),
                OpenApiExample(
                    "Invitation expired",
                    value={"invitation_code": ["Invitation expired."]},
                    response_only=True,
                ),
                OpenApiExample(
                    "Email already exists in this center",
                    value={"email": ["A user with this email already exists in this center."]},
                    response_only=True,
                ),
                OpenApiExample(
                    "Admin invitation (cannot register via API)",
                    value={
                        "invitation_code": [
                            "Administrators cannot register via public API. Please contact system support."
                        ]
                    },
                    response_only=True,
                ),
            ],
        ),
        429: RESP_429_THROTTLED,
    },
)


# =============================================================================
# Login
# =============================================================================

LOGIN_DESCRIPTION = """
Obtain JWT **access** and **refresh** tokens for the authenticated user.

**Subdomain context (critical for frontend):**
- **Main domain** (e.g. `api.mikan.uz`, `mikan.uz`): Only users with **no center** (Owner) can log in.
- **Subdomain** (e.g. `edu1.mikan.uz`): Only users belonging to the center whose **slug** matches the subdomain (here `edu1`) can log in.

Same email can exist in multiple centers; the **host** determines which account is used. Always call Login from the same origin the user selected (main site vs center site).

**Security:** Invalid credentials, disabled account, or pending approval return `401`. Brute-force protection (Axes + throttle) applies; too many failures return `429`.
"""

login_schema = extend_schema(
    tags=["Authentication"],
    summary="Login (JWT)",
    description=LOGIN_DESCRIPTION,
    request=LoginSerializer,
    examples=[
        OpenApiExample(
            "Center user (subdomain: edu1.mikan.uz)",
            value={
                "email": "teacher@edu1.com",
                "password": "yourSecurePassword",
            },
            request_only=True,
        ),
        OpenApiExample(
            "Owner (main domain: api.mikan.uz)",
            value={
                "email": "owner@mikan.uz",
                "password": "ownerPassword",
            },
            request_only=True,
        ),
    ],
    responses={
        200: OpenApiResponse(
            description="Login successful; returns access token, refresh token, and user object.",
            examples=[
                OpenApiExample(
                    "Success",
                    value={
                        "access": "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9...",
                        "refresh": "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9...",
                        "user": {
                            "id": 1,
                            "email": "teacher@edu1.com",
                            "first_name": "John",
                            "last_name": "Doe",
                            "avatar": None,
                            "role": "TEACHER",
                            "center": 1,
                            "center_info": {"id": 1, "name": "Edu Center", "is_active": True},
                            "my_groups": [{"id": 1, "name": "N5 Prep", "role": "TEACHER"}],
                            "is_approved": True,
                            "created_at": "2024-01-15T10:00:00Z",
                            "updated_at": "2024-01-20T12:00:00Z",
                        },
                    },
                    response_only=True,
                ),
            ],
        ),
        400: OpenApiResponse(
            description="Bad Request: missing or invalid fields.",
            examples=[
                OpenApiExample(
                    "Missing email",
                    value={"email": ["This field is required."]},
                    response_only=True,
                ),
                OpenApiExample(
                    "Invalid email format",
                    value={"email": ["Enter a valid email address."]},
                    response_only=True,
                ),
            ],
        ),
        401: OpenApiResponse(
            description="Unauthorized: invalid credentials or account not eligible to log in.",
            examples=[
                OpenApiExample(
                    "Invalid credentials",
                    value={"detail": "Invalid credentials."},
                    response_only=True,
                ),
                OpenApiExample(
                    "Account pending approval",
                    value={"detail": "Account pending approval."},
                    response_only=True,
                ),
                OpenApiExample(
                    "Account disabled",
                    value={"detail": "User account is disabled."},
                    response_only=True,
                ),
                OpenApiExample(
                    "Center suspended",
                    value={"detail": "This center is currently suspended. Please contact support."},
                    response_only=True,
                ),
            ],
        ),
        429: RESP_429_THROTTLED,
    },
)


# =============================================================================
# Me (current user)
# =============================================================================

ME_GET_DESCRIPTION = """
Return the full profile of the currently authenticated user (from JWT).

Includes `center_info`, `my_groups` (groups in the tenant schema), and read-only
fields such as `role`, `center`, `is_approved`. Any authenticated user (Owner,
CENTER_ADMIN, TEACHER, STUDENT, GUEST) can call this.
"""

ME_UPDATE_DESCRIPTION = """
Update the current user's profile. Only writable fields can be sent: `first_name`,
`last_name`, `avatar` (URL cleared if omitted), `address`, `bio`, `city`,
`emergency_contact_phone`. `email`, `role`, `center`, `is_approved` are read-only.

**GUEST users:** Can update their own profile (e.g. name, bio). They cannot access
UserViewSet (center user management); that is restricted to CENTER_ADMIN and TEACHER.
"""

me_schema_view = extend_schema_view(
    get=extend_schema(
        tags=["Authentication"],
        summary="Get current user",
        description=ME_GET_DESCRIPTION,
        responses={
            200: UserSerializer,
            401: RESP_401_UNAUTHORIZED,
        },
    ),
    put=extend_schema(
        tags=["Authentication"],
        summary="Update current user (full)",
        description=ME_UPDATE_DESCRIPTION,
        request=UserSerializer,
        examples=[
            OpenApiExample(
                "Update profile",
                value={
                    "first_name": "Jane",
                    "last_name": "Smith",
                    "bio": "JLPT N5 student.",
                    "city": "Tashkent",
                },
                request_only=True,
            ),
        ],
        responses={
            200: UserSerializer,
            400: RESP_400_INVALID,
            401: RESP_401_UNAUTHORIZED,
        },
    ),
    patch=extend_schema(
        tags=["Authentication"],
        summary="Update current user (partial)",
        description=ME_UPDATE_DESCRIPTION,
        request=UserSerializer,
        examples=[
            OpenApiExample(
                "Partial update",
                value={"first_name": "Jane", "last_name": "Smith"},
                request_only=True,
            ),
        ],
        responses={
            200: UserSerializer,
            400: RESP_400_INVALID,
            401: RESP_401_UNAUTHORIZED,
        },
    ),
)


# =============================================================================
# Logout
# =============================================================================

LOGOUT_DESCRIPTION = """
Blacklist the given **refresh** token so it can no longer be used to obtain new
access tokens. Call this when the user explicitly logs out.

**Request body:** Must include the `refresh` token (the same string returned by
`POST /api/v1/auth/login/`). The access token does not need to be sent; it will
expire naturally. Sending the refresh token here prevents its reuse.
"""

logout_schema = extend_schema(
    tags=["Authentication"],
    summary="Logout (blacklist refresh token)",
    description=LOGOUT_DESCRIPTION,
    request=LogoutRequestSerializer,
    examples=[
        OpenApiExample(
            "Logout request",
            value={"refresh": "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9..."},
            request_only=True,
        ),
    ],
    responses={
        205: OpenApiResponse(
            description="Successfully logged out; refresh token blacklisted.",
            examples=[
                OpenApiExample(
                    "Success",
                    value={"detail": "Successfully logged out."},
                    response_only=True,
                ),
            ],
        ),
        400: OpenApiResponse(
            description="Missing or invalid refresh token.",
            examples=[
                OpenApiExample(
                    "Refresh token required",
                    value={"detail": "Refresh token is required."},
                    response_only=True,
                ),
                OpenApiExample(
                    "Invalid or expired token",
                    value={"detail": "Invalid or expired token."},
                    response_only=True,
                ),
            ],
        ),
        401: RESP_401_UNAUTHORIZED,
    },
)


# =============================================================================
# Update password (authenticated)
# =============================================================================

UPDATE_PASSWORD_DESCRIPTION = """
Change the authenticated user's password. Requires the current password for
verification. New password must pass Django's password validation (length,
complexity).
"""

update_password_schema = extend_schema(
    tags=["Authentication"],
    summary="Change password",
    description=UPDATE_PASSWORD_DESCRIPTION,
    request=UpdatePasswordSerializer,
    examples=[
        OpenApiExample(
            "Change password",
            value={
                "old_password": "currentPassword123",
                "new_password": "NewSecurePassword456!",
            },
            request_only=True,
        ),
    ],
    responses={
        200: OpenApiResponse(
            description="Password updated successfully.",
            examples=[
                OpenApiExample(
                    "Success",
                    value={"detail": "Password updated successfully."},
                    response_only=True,
                ),
            ],
        ),
        400: OpenApiResponse(
            description="Validation error: wrong old password or new password invalid.",
            examples=[
                OpenApiExample(
                    "Incorrect old password",
                    value={"old_password": ["Incorrect old password."]},
                    response_only=True,
                ),
                OpenApiExample(
                    "New password too common",
                    value={"new_password": ["This password is too common."]},
                    response_only=True,
                ),
            ],
        ),
        401: RESP_401_UNAUTHORIZED,
    },
)


# =============================================================================
# Password reset request
# =============================================================================

PASSWORD_RESET_REQUEST_DESCRIPTION = """
Request a password reset email for the given email address.

**Security:** The API always returns the same success message whether the email
exists or not, to avoid leaking account existence. If the email exists and is
active, a time-limited reset link is sent. Throttled per IP (e.g. 5 requests/hour).
"""

password_reset_request_schema = extend_schema(
    tags=["Authentication"],
    summary="Request password reset email",
    description=PASSWORD_RESET_REQUEST_DESCRIPTION,
    request=PasswordResetRequestSerializer,
    examples=[
        OpenApiExample(
            "Request reset",
            value={"email": "user@example.com"},
            request_only=True,
        ),
    ],
    responses={
        200: OpenApiResponse(
            description="If the email exists, a reset link was sent. Same message either way.",
            examples=[
                OpenApiExample(
                    "Success",
                    value={"detail": "Password reset email sent."},
                    response_only=True,
                ),
            ],
        ),
        400: OpenApiResponse(
            description="Invalid email format.",
            examples=[
                OpenApiExample(
                    "Invalid email",
                    value={"email": ["Enter a valid email address."]},
                    response_only=True,
                ),
            ],
        ),
        429: RESP_429_THROTTLED,
    },
)


# =============================================================================
# Password reset confirm
# =============================================================================

PASSWORD_RESET_CONFIRM_DESCRIPTION = """
Set a new password using the `uid` and `token` from the reset email link.

**Security:** `uid` is a base64-encoded user id; `token` is time-limited. Invalid
or expired links return a generic error. Do not reveal whether the link was
invalid or the user not found. Throttled.
"""

password_reset_confirm_schema = extend_schema(
    tags=["Authentication"],
    summary="Confirm password reset",
    description=PASSWORD_RESET_CONFIRM_DESCRIPTION,
    request=PasswordResetConfirmSerializer,
    examples=[
        OpenApiExample(
            "Confirm reset (from email link)",
            value={
                "uid": "MQ",
                "token": "abc123-def456-...",
                "new_password": "NewSecurePassword123!",
            },
            request_only=True,
        ),
    ],
    responses={
        201: OpenApiResponse(
            description="Password reset successfully; user can log in with new password.",
        ),
        400: OpenApiResponse(
            description="Invalid or expired link, or new password validation failed.",
            examples=[
                OpenApiExample(
                    "Invalid or expired link",
                    value={"uid": ["Invalid or expired link."]},
                    response_only=True,
                ),
                OpenApiExample(
                    "Invalid token",
                    value={"token": ["Invalid or expired link."]},
                    response_only=True,
                ),
            ],
        ),
        429: RESP_429_THROTTLED,
    },
)


# =============================================================================
# UserViewSet (center user management)
# =============================================================================

USERS_LIST_DESCRIPTION = """
List users in the **current center** (tenant). The center is determined by the
authenticated user's JWT (their `center_id`).

**Role-based visibility:**
- **CENTER_ADMIN:** Sees **all** users in the center (all roles). Can filter by
  `role`, `is_active`, `is_approved`; search by `first_name`, `last_name`, `email`;
  order by `created_at`, `last_login`, `first_name`, `last_name`, `email`.
- **TEACHER:** Sees **only students** (and GUESTs) who are in groups they teach.
  Same filters/search/ordering apply to this subset. Teachers cannot create,
  update, or delete users (403 on those actions).
- **STUDENT / GUEST:** Cannot access this endpoint (403). Use `GET /api/v1/auth/me/`
  for own profile.
"""

USERS_RETRIEVE_DESCRIPTION = """
Retrieve a single user in the current center. Same visibility rules as list:
CENTER_ADMIN sees any center user; TEACHER sees only students in their groups.
"""

USERS_CREATE_DESCRIPTION = """
Create a new user in the center. **CENTER_ADMIN only.** Teachers receive 403.

Email must be unique within the center. Required: `email`, `first_name`, `last_name`,
`role` (TEACHER or STUDENT), `password`. Optional: `avatar`, `is_active`.
"""

USERS_UPDATE_DESCRIPTION = """
Full update of a center user. **CENTER_ADMIN only.** Teachers receive 403.
Writable: `first_name`, `last_name`, `avatar`, `is_active`, `is_approved`.
"""

USERS_PARTIAL_UPDATE_DESCRIPTION = """
Partial update of a center user. **CENTER_ADMIN only.** Teachers receive 403.
"""

USERS_DESTROY_DESCRIPTION = """
Soft-delete a user in the center. **CENTER_ADMIN only.** Teachers receive 403.
The user is marked deleted and excluded from default querysets; they cannot log in.
"""

user_viewset_schema = extend_schema_view(
    list=extend_schema(
        tags=["Users"],
        summary="List center users",
        description=USERS_LIST_DESCRIPTION,
        parameters=[
            OpenApiParameter(name="role", type=str, enum=["CENTER_ADMIN", "TEACHER", "STUDENT", "GUEST"]),
            OpenApiParameter(name="is_active", type=bool),
            OpenApiParameter(name="is_approved", type=bool),
            OpenApiParameter(name="search", description="Search first_name, last_name, email"),
            OpenApiParameter(name="ordering", description="e.g. -created_at, first_name"),
        ],
        responses={
            200: UserListSerializer(many=True),
            401: RESP_401_UNAUTHORIZED,
            403: OpenApiResponse(
                description="Forbidden: STUDENT/GUEST cannot list users; only CENTER_ADMIN and TEACHER.",
            ),
        },
    ),
    retrieve=extend_schema(
        tags=["Users"],
        summary="Get center user",
        description=USERS_RETRIEVE_DESCRIPTION,
        responses={
            200: UserManagementSerializer,
            401: RESP_401_UNAUTHORIZED,
            403: RESP_403_FORBIDDEN,
            404: OpenApiResponse(description="User not found or not visible to this role."),
        },
    ),
    create=extend_schema(
        tags=["Users"],
        summary="Create center user",
        description=USERS_CREATE_DESCRIPTION,
        request=UserCreateSerializer,
        examples=[
            OpenApiExample(
                "Create teacher",
                value={
                    "email": "newteacher@center.edu",
                    "first_name": "Alice",
                    "last_name": "Teacher",
                    "role": "TEACHER",
                    "password": "TempPass123!",
                    "is_active": True,
                },
                request_only=True,
            ),
            OpenApiExample(
                "Create student",
                value={
                    "email": "student@center.edu",
                    "first_name": "Bob",
                    "last_name": "Student",
                    "role": "STUDENT",
                    "password": "StudentPass1",
                },
                request_only=True,
            ),
        ],
        responses={
            201: UserManagementSerializer,
            400: OpenApiResponse(
                description="Validation error (e.g. email already exists in this center).",
                examples=[
                    OpenApiExample(
                        "Duplicate email in center",
                        value={"email": ["A user with this email already exists in this center."]},
                        response_only=True,
                    ),
                ],
            ),
            401: RESP_401_UNAUTHORIZED,
            403: OpenApiResponse(
                description="Forbidden: TEACHER cannot create users; CENTER_ADMIN only.",
            ),
        },
    ),
    update=extend_schema(
        tags=["Users"],
        summary="Update center user",
        description=USERS_UPDATE_DESCRIPTION,
        request=UserManagementSerializer,
        examples=[
            OpenApiExample(
                "Update user",
                value={
                    "first_name": "Alice",
                    "last_name": "Updated",
                    "is_active": True,
                    "is_approved": True,
                },
                request_only=True,
            ),
        ],
        responses={
            200: UserManagementSerializer,
            400: RESP_400_INVALID,
            401: RESP_401_UNAUTHORIZED,
            403: OpenApiResponse(
                description="Forbidden: TEACHER cannot update users; CENTER_ADMIN only.",
            ),
            404: OpenApiResponse(description="User not found."),
        },
    ),
    partial_update=extend_schema(
        tags=["Users"],
        summary="Partially update center user",
        description=USERS_PARTIAL_UPDATE_DESCRIPTION,
        request=UserManagementSerializer,
        examples=[
            OpenApiExample(
                "Partial update",
                value={"is_approved": True},
                request_only=True,
            ),
        ],
        responses={
            200: UserManagementSerializer,
            400: RESP_400_INVALID,
            401: RESP_401_UNAUTHORIZED,
            403: OpenApiResponse(
                description="Forbidden: TEACHER cannot update users; CENTER_ADMIN only.",
            ),
            404: OpenApiResponse(description="User not found."),
        },
    ),
    destroy=extend_schema(
        tags=["Users"],
        summary="Delete center user",
        description=USERS_DESTROY_DESCRIPTION,
        responses={
            204: OpenApiResponse(description="User soft-deleted."),
            401: RESP_401_UNAUTHORIZED,
            403: OpenApiResponse(
                description="Forbidden: TEACHER cannot delete users; CENTER_ADMIN only.",
            ),
            404: OpenApiResponse(description="User not found."),
        },
    ),
)


# =============================================================================
# Avatar upload
# =============================================================================

AVATAR_UPLOAD_DESCRIPTION = """
Upload or replace the **authenticated user's** avatar image.

**Content-Type:** `multipart/form-data`. The form field name must be `avatar`.
Accepted formats typically include JPEG, PNG, GIF. File size limits apply (see
server configuration).

**Behavior:** If the user already has an avatar, it is replaced. Sending a request
without the `avatar` file returns `400`.
"""

avatar_upload_schema = extend_schema(
    tags=["Authentication"],
    summary="Upload avatar",
    description=AVATAR_UPLOAD_DESCRIPTION,
    request={
        "multipart/form-data": {
            "type": "object",
            "required": ["avatar"],
            "properties": {
                "avatar": {
                    "type": "string",
                    "format": "binary",
                    "description": "Image file (e.g. JPEG, PNG). Form field name must be 'avatar'.",
                },
            },
        }
    },
    examples=[
        OpenApiExample(
            "multipart/form-data",
            value={"avatar": "(binary file)"},
            request_only=True,
            description="Send as multipart/form-data with a single field 'avatar' containing the image file.",
        ),
    ],
    responses={
        200: UserSerializer,
        400: OpenApiResponse(
            description="No avatar file provided or invalid file.",
            examples=[
                OpenApiExample(
                    "No file provided",
                    value={"avatar": ["No avatar file provided."]},
                    response_only=True,
                ),
            ],
        ),
        401: RESP_401_UNAUTHORIZED,
    },
)
