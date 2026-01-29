# apps/authentication/swagger.py
"""
OpenAPI / Swagger documentation for the authentication app.

All schema definitions, response descriptions, and request/response examples
live here. Views are kept thin and apply these via decorators imported from
this module.

Multi-tenant context:
- Login and registration are scoped by host: main domain (Owner) vs subdomain
  (Center). Same email in two centers cannot log into the wrong one.
- User management (UserViewSet): CENTER_ADMIN sees all center users and can
  create/update/delete; TEACHER sees only their students (list/retrieve only).
"""
from drf_spectacular.utils import (
    OpenApiExample,
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


# ---- Reusable response descriptions ----
RESP_400_INVALID = OpenApiResponse(
    description="Invalid input or validation error (e.g. duplicate email in center, invalid invitation code).",
)
RESP_401_UNAUTHORIZED = OpenApiResponse(
    description="Authentication required or invalid/expired JWT.",
)
RESP_403_FORBIDDEN = OpenApiResponse(
    description="Insufficient permissions (e.g. TEACHER attempting create/update/delete).",
)
RESP_429_THROTTLED = OpenApiResponse(
    description="Too many requests; throttling or Axes lockout applied. Retry later.",
)


# ---- Register ----
REGISTER_DESCRIPTION = """
Register a new user using an **invitation code** from a center.

**Multi-tenant:** Call this from the center's subdomain (e.g. `edu1.mikan.uz`) so the
invitation is resolved in context. Email must be unique **within that center**.
Registration is atomic; duplicate claim of the same invitation is prevented.
"""

register_schema = extend_schema(
    tags=["Authentication"],
    summary="Register with invitation code",
    description=REGISTER_DESCRIPTION,
    request=RegisterSerializer,
    examples=[
        OpenApiExample(
            "Valid request",
            value={
                "email": "student@example.com",
                "first_name": "Jane",
                "last_name": "Doe",
                "password": "securePass123",
                "invitation_code": "abc123xyz789",
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
            description="Validation error (e.g. duplicate email in center, invalid/claimed/expired invitation).",
            examples=[
                OpenApiExample(
                    "Duplicate email in center",
                    value={"email": ["A user with this email already exists in this center."]},
                    response_only=True,
                ),
                OpenApiExample(
                    "Invitation already claimed",
                    value={"invitation_code": ["Invitation already claimed."]},
                    response_only=True,
                ),
            ],
        ),
        429: RESP_429_THROTTLED,
    },
)


# ---- Login ----
LOGIN_DESCRIPTION = """
Obtain JWT **access** and **refresh** tokens.

**Multi-tenant:** Login is strictly scoped by host:
- **Main domain** (e.g. `api.mikan.uz`): Only users with no center (Owner).
- **Subdomain** (e.g. `edu1.mikan.uz`): Only users belonging to the center whose slug matches the subdomain.

Same email in two centers cannot log into the wrong center. Brute-force protection
(Axes + throttle) applies; use the same host the frontend will use.
"""

login_schema = extend_schema(
    tags=["Authentication"],
    summary="Login (JWT)",
    description=LOGIN_DESCRIPTION,
    request=LoginSerializer,
    examples=[
        OpenApiExample(
            "Center user (subdomain)",
            value={"email": "teacher@edu1.com", "password": "yourPassword"},
            request_only=True,
        ),
    ],
    responses={
        200: OpenApiResponse(
            description="Login successful; returns access, refresh, and user payload.",
            examples=[
                OpenApiExample(
                    "Success",
                    value={
                        "access": "eyJ0eXAiOiJKV1QiLCJhbGc...",
                        "refresh": "eyJ0eXAiOiJKV1QiLCJhbGc...",
                        "user": {
                            "id": 1,
                            "email": "teacher@edu1.com",
                            "first_name": "John",
                            "last_name": "Doe",
                            "role": "TEACHER",
                            "center": 1,
                            "is_approved": True,
                        },
                    },
                    response_only=True,
                ),
            ],
        ),
        400: OpenApiResponse(
            description="Validation error (e.g. missing email/password).",
            examples=[
                OpenApiExample(
                    "Missing fields",
                    value={"email": ["This field is required."]},
                    response_only=True,
                ),
            ],
        ),
        401: OpenApiResponse(
            description="Invalid credentials, account disabled, or pending approval.",
            examples=[
                OpenApiExample(
                    "Invalid credentials",
                    value={"detail": "Invalid credentials."},
                    response_only=True,
                ),
                OpenApiExample(
                    "Pending approval",
                    value={"detail": "Account pending approval."},
                    response_only=True,
                ),
            ],
        ),
        429: RESP_429_THROTTLED,
    },
)


# ---- Me (current user) ----
me_schema_view = extend_schema_view(
    get=extend_schema(
        tags=["Authentication"],
        summary="Get current user",
        description="Return the authenticated user (public schema).",
        responses={
            200: UserSerializer,
            401: RESP_401_UNAUTHORIZED,
        },
    ),
    put=extend_schema(
        tags=["Authentication"],
        summary="Update current user (full)",
        request=UserSerializer,
        responses={
            200: UserSerializer,
            400: RESP_400_INVALID,
            401: RESP_401_UNAUTHORIZED,
        },
    ),
    patch=extend_schema(
        tags=["Authentication"],
        summary="Update current user (partial)",
        request=UserSerializer,
        responses={
            200: UserSerializer,
            400: RESP_400_INVALID,
            401: RESP_401_UNAUTHORIZED,
        },
    ),
)


# ---- Logout ----
LOGOUT_DESCRIPTION = """
Blacklist the given **refresh** token so it can no longer be used to obtain new access tokens.

Requires a valid JWT in the `Authorization` header. The request body must contain
the refresh token to blacklist (same one returned by Login).
"""

logout_schema = extend_schema(
    tags=["Authentication"],
    summary="Logout (blacklist refresh token)",
    description=LOGOUT_DESCRIPTION,
    request=LogoutRequestSerializer,
    examples=[
        OpenApiExample(
            "Request body",
            value={"refresh": "eyJ0eXAiOiJKV1QiLCJhbGc..."},
            request_only=True,
        ),
    ],
    responses={
        205: OpenApiResponse(
            description="Successfully logged out; refresh token blacklisted.",
        ),
        400: OpenApiResponse(
            description="Missing or invalid refresh token.",
        ),
        401: RESP_401_UNAUTHORIZED,
    },
)


# ---- Update password (authenticated) ----
update_password_schema = extend_schema(
    tags=["Authentication"],
    summary="Change password",
    description="Change the authenticated user's password. Requires current password.",
    request=UpdatePasswordSerializer,
    responses={
        200: OpenApiResponse(description="Password updated successfully."),
        400: RESP_400_INVALID,
        401: RESP_401_UNAUTHORIZED,
    },
)


# ---- Password reset request ----
PASSWORD_RESET_REQUEST_DESCRIPTION = """
Request a password reset email for the given email address.

**Security:** The same success message is returned whether the email exists or not,
to avoid leaking account existence. Throttled (e.g. 5/hour per IP).
"""

password_reset_request_schema = extend_schema(
    tags=["Authentication"],
    summary="Request password reset email",
    description=PASSWORD_RESET_REQUEST_DESCRIPTION,
    request=PasswordResetRequestSerializer,
    responses={
        200: OpenApiResponse(
            description="If the email exists, a reset link was sent. Same message either way.",
        ),
        429: RESP_429_THROTTLED,
    },
)


# ---- Password reset confirm ----
PASSWORD_RESET_CONFIRM_DESCRIPTION = """
Set a new password using the token and uid from the reset email link.

**Security:** UID is a signed base64-encoded user id; token is time-limited. Invalid
or expired links return a generic error. Throttled.
"""

password_reset_confirm_schema = extend_schema(
    tags=["Authentication"],
    summary="Confirm password reset",
    description=PASSWORD_RESET_CONFIRM_DESCRIPTION,
    request=PasswordResetConfirmSerializer,
    responses={
        200: OpenApiResponse(description="Password reset successfully."),
        400: RESP_400_INVALID,
        429: RESP_429_THROTTLED,
    },
)


# ---- UserViewSet (center users) ----
USERS_LIST_DESCRIPTION = """
List users in the current center.

**Access:**
- **CENTER_ADMIN:** All users in the center (full CRUD).
- **TEACHER:** Only students in groups they teach (list/retrieve only; no create/update/delete).
"""
USERS_RETRIEVE_DESCRIPTION = "Retrieve a user in the current center (same access rules as list)."
USERS_CREATE_DESCRIPTION = "Create a new user in the center. **CENTER_ADMIN only.** Teachers cannot create users."
USERS_UPDATE_DESCRIPTION = "Update a user. **CENTER_ADMIN only.**"
USERS_DESTROY_DESCRIPTION = "Soft-delete a user. **CENTER_ADMIN only.**"

user_viewset_schema = extend_schema_view(
    list=extend_schema(
        tags=["Users"],
        summary="List center users",
        description=USERS_LIST_DESCRIPTION,
        responses={
            200: UserListSerializer(many=True),
            401: RESP_401_UNAUTHORIZED,
            403: RESP_403_FORBIDDEN,
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
        },
    ),
    create=extend_schema(
        tags=["Users"],
        summary="Create center user",
        description=USERS_CREATE_DESCRIPTION,
        request=UserCreateSerializer,
        responses={
            201: UserManagementSerializer,
            400: RESP_400_INVALID,
            401: RESP_401_UNAUTHORIZED,
            403: RESP_403_FORBIDDEN,
        },
    ),
    update=extend_schema(
        tags=["Users"],
        summary="Update center user",
        description=USERS_UPDATE_DESCRIPTION,
        request=UserManagementSerializer,
        responses={
            200: UserManagementSerializer,
            400: RESP_400_INVALID,
            401: RESP_401_UNAUTHORIZED,
            403: RESP_403_FORBIDDEN,
        },
    ),
    partial_update=extend_schema(
        tags=["Users"],
        summary="Partially update center user",
        request=UserManagementSerializer,
        responses={
            200: UserManagementSerializer,
            400: RESP_400_INVALID,
            401: RESP_401_UNAUTHORIZED,
            403: RESP_403_FORBIDDEN,
        },
    ),
    destroy=extend_schema(
        tags=["Users"],
        summary="Delete center user",
        description=USERS_DESTROY_DESCRIPTION,
        responses={
            204: OpenApiResponse(description="User deleted (soft delete)."),
            401: RESP_401_UNAUTHORIZED,
            403: RESP_403_FORBIDDEN,
        },
    ),
)


# ---- Avatar upload ----
avatar_upload_schema = extend_schema(
    tags=["Authentication"],
    summary="Upload avatar",
    description="Upload or replace the authenticated user's avatar. Multipart form; field name: `avatar`.",
    request={
        "multipart/form-data": {
            "type": "object",
            "properties": {
                "avatar": {"type": "string", "format": "binary", "description": "Image file"},
            },
            "required": ["avatar"],
        }
    },
    responses={
        200: UserSerializer,
        400: OpenApiResponse(description="No file provided or invalid file."),
        401: RESP_401_UNAUTHORIZED,
    },
)


