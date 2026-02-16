"""
OpenAPI / Swagger documentation for the Authentication app.

ENTERPRISE-GRADE API DOCUMENTATION for Frontend Integration.

Core Concepts:
- Centralized Architecture: All users log in through the main domain (mikan.uz).
  Email is globally unique across the platform. User's center is identified via center_id.
- Role-Based Access Control: CENTER_ADMIN (full CRUD), TEACHER (list/retrieve students only),
  STUDENT/GUEST (self-service only), OWNER (platform-wide).
- Security: Soft-deleted users blocked from login; rate-limited auth endpoints; 
  JWT tokens with refresh rotation.
- Data Optimization: Batch fetching of center avatars and group memberships to prevent N+1.

See README for integration guide: https://docs.mikan.uz/authentication
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


# =============================================================================
# REUSABLE RESPONSE DEFINITIONS
# =============================================================================

RESP_400_INVALID = OpenApiResponse(
    description="Bad Request: validation error or invalid payload.",
)

RESP_401_UNAUTHORIZED = OpenApiResponse(
    description="Unauthorized: missing, invalid, or expired JWT token.",
)

RESP_403_FORBIDDEN = OpenApiResponse(
    description="Forbidden: authenticated but insufficient permissions for this action.",
)

RESP_404_NOT_FOUND = OpenApiResponse(
    description="Not Found: resource does not exist or not visible to this user.",
)

RESP_429_THROTTLED = OpenApiResponse(
    description=(
        "Too Many Requests: rate limit exceeded (Axes lockout or throttle_scope limit). "
        "Include `Retry-After` header. Auth endpoints: 5 attempts/15min. "
        "Password reset: 5 attempts/hour per email."
    ),
)


# =============================================================================
# REGISTER ENDPOINT
# =============================================================================

REGISTER_DESCRIPTION = """
**Register a new user with an invitation code.**

Invitation codes are issued by a center's administrator for new students or teachers.
Only users with role STUDENT or TEACHER can self-register; OWNER and CENTER_ADMIN 
roles must be created by system administrators.

**Invitation Code:**
- The invitation code determines which center the new user joins.
- Same code cannot be reused once claimed.

**Email Uniqueness:**
Email must be unique **across the entire platform**. The same email cannot be used in different centers.

**After Registration:**
1. Account created with `is_approved=False`.
2. User receives email confirmation if enabled.
3. Center admin must approve account before user can log in.

**Errors:**
- `400`: Invalid code (not found, expired, already claimed, wrong role).
- `400`: Email already exists on the platform.
- `429`: Too many registration attempts (brute-force protection).
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
            "Minimal registration (required fields only)",
            value={
                "email": "newuser@center.edu",
                "password": "Passw0rd",
                "invitation_code": "INV-xyz",
            },
            request_only=True,
            description="First and last name are optional; email domain should match center.",
        ),
    ],
    responses={
        201: OpenApiResponse(
            description="Registration successful; user account pending center admin approval.",
            examples=[
                OpenApiExample(
                    "Success - Pending approval",
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
            description="Validation error. Check 'invitation_code', 'email', or 'password'.",
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
                    "Admin role cannot self-register",
                    value={
                        "invitation_code": [
                            "Administrators cannot register via public API. "
                            "Please contact system support."
                        ]
                    },
                    response_only=True,
                    description="OWNER and CENTER_ADMIN roles require admin provisioning.",
                ),
                OpenApiExample(
                    "Email already exists",
                    value={"email": ["A user with this email already exists."]},
                    response_only=True,
                ),
                OpenApiExample(
                    "Password too short",
                    value={"password": ["This password is too short. It must contain at least 6 characters."]},
                    response_only=True,
                ),
            ],
        ),
        429: RESP_429_THROTTLED,
    },
)


# =============================================================================
# LOGIN ENDPOINT
# =============================================================================

LOGIN_DESCRIPTION = """
**Obtain JWT access and refresh tokens for authentication.**

Users log in through the main domain (mikan.uz). Email is globally unique,
so the user is identified directly by email. The user's center context is
carried in the JWT token after authentication.

**Login Flow:**
- User provides email + password on the main domain.
- Backend authenticates and returns JWT tokens with user info including center_id.
- Frontend uses center_id to determine routing/UI context.

**Account Eligibility Checks:**
1. User exists and has correct password.
2. User is active (`is_active=True`).
3. User is approved (`is_approved=True`).
4. User's center (if any) is active (`center.is_active=True`).

Any failure returns `401` with a descriptive message.

**Security:**
- Brute-force protection: Axes locks account after 5 failed attempts (15-min lockout).
- Rate limiting: 10 requests/minute per IP (throttle_scope='auth').
- Returns `429` if rate limit exceeded.

**Token Details:**
- `access`: Short-lived JWT (~5 min). Include in `Authorization: Bearer <access>` header.
- `refresh`: Long-lived JWT (~7 days). Used to obtain new access token; do NOT include in requests.
- `user`: Full user object with groups, center info, and approval status.

**After Login:**
- Store `refresh` token securely (httpOnly cookie preferred).
- Use `access` token for all subsequent API calls.
- When access expires, call `POST /api/v1/auth/token/refresh/` with the refresh token.
"""

login_schema = extend_schema(
    tags=["Authentication"],
    summary="Login (obtain JWT tokens)",
    description=LOGIN_DESCRIPTION,
    request=LoginSerializer,
    examples=[
        OpenApiExample(
            "Center user login",
            value={
                "email": "teacher@edu1.com",
                "password": "SecurePassword123",
            },
            request_only=True,
            description="Email must be registered on the platform.",
        ),
        OpenApiExample(
            "Owner login",
            value={
                "email": "admin@mikan.uz",
                "password": "AdminPassword456",
            },
            request_only=True,
            description="Owner has no center assigned.",
        ),
    ],
    responses={
        200: OpenApiResponse(
            description="Login successful; returns tokens and user object.",
            examples=[
                OpenApiExample(
                    "Successful login (center user)",
                    value={
                        "access": "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.eyJzdWIiOjEsImV4cCI6MTY0OTI4NDgwMH0.abcdef...",
                        "refresh": "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.eyJzdWIiOjEsImV4cCI6MTY0OTM3MTIwMH0.ghijkl...",
                        "user": {
                            "id": 1,
                            "email": "teacher@edu1.com",
                            "first_name": "John",
                            "last_name": "Doe",
                            "avatar": "https://cdn.mikan.uz/avatars/user_1.jpg",
                            "role": "TEACHER",
                            "center": 1,
                            "center_info": {
                                "id": 1,
                                "name": "Edu Center N5",
                                "is_active": True,
                            },
                            "my_groups": [
                                {
                                    "id": 5,
                                    "name": "N5 Beginner Class",
                                    "role": "TEACHER",
                                },
                                {
                                    "id": 8,
                                    "name": "Advanced Prep",
                                    "role": "TEACHER",
                                },
                            ],
                            "is_approved": True,
                            "created_at": "2024-01-15T10:00:00Z",
                            "updated_at": "2024-01-20T12:00:00Z",
                        },
                    },
                    response_only=True,
                ),
                OpenApiExample(
                    "Successful login (owner)",
                    value={
                        "access": "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9...",
                        "refresh": "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9...",
                        "user": {
                            "id": 100,
                            "email": "admin@mikan.uz",
                            "first_name": "Admin",
                            "last_name": "User",
                            "role": "OWNER",
                            "center": None,
                            "center_info": None,
                            "my_groups": [],
                            "is_approved": True,
                            "created_at": "2023-01-01T00:00:00Z",
                            "updated_at": "2024-01-20T12:00:00Z",
                        },
                    },
                    response_only=True,
                    description="Owner users have center=null and no group memberships.",
                ),
            ],
        ),
        400: OpenApiResponse(
            description="Bad Request: missing or malformed fields.",
            examples=[
                OpenApiExample(
                    "Missing email field",
                    value={"email": ["This field is required."]},
                    response_only=True,
                ),
                OpenApiExample(
                    "Invalid email format",
                    value={"email": ["Enter a valid email address."]},
                    response_only=True,
                ),
                OpenApiExample(
                    "Missing password field",
                    value={"password": ["This field is required."]},
                    response_only=True,
                ),
            ],
        ),
        401: OpenApiResponse(
            description="Unauthorized: credentials invalid or account ineligible.",
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
                    description="Center admin must approve account before user can log in.",
                ),
                OpenApiExample(
                    "Account disabled",
                    value={"detail": "User account is disabled."},
                    response_only=True,
                    description="User's is_active flag is False; contact admin to reactivate.",
                ),
                OpenApiExample(
                    "Center suspended",
                    value={"detail": "This center is currently suspended. Please contact support."},
                    response_only=True,
                    description="User's center has is_active=False; center must be reactivated by owner.",
                ),
            ],
        ),
        429: RESP_429_THROTTLED,
    },
)


# =============================================================================
# ME ENDPOINT (CURRENT USER)
# =============================================================================

ME_GET_DESCRIPTION = """
**Retrieve the full profile of the authenticated user.**

Returns complete user data including center info, group memberships, and status flags.
Any authenticated user (OWNER, CENTER_ADMIN, TEACHER, STUDENT, GUEST) can call this.

**Group Membership (`my_groups`):**
Structure: `[{"id": int, "name": str, "role": str}, ...]`

Possible roles within a group:
- `"TEACHER"`: Teaching one or more classes.
- `"STUDENT"`: Enrolled in one or more classes.
- `"ADMIN"`: Group administrator (if applicable).

If user has no center, `my_groups` is empty. If user is not in any group, `my_groups` is empty.

**Center Info:**
Only present if user belongs to a center. Includes center name and active status.
If center is suspended (`is_active=False`), user cannot log in but existing session remains valid.
"""

ME_UPDATE_DESCRIPTION = """
**Update the authenticated user's profile (full update).**

Writable fields: `first_name`, `last_name`, `avatar` (URL or null), `bio`, `address`, 
`city`, `emergency_contact_phone`.

Read-only fields: `id`, `email`, `role`, `center`, `is_approved`, `created_at`, `updated_at`.

**GUEST Users:**
- Can update own profile (name, bio, contact info).
- Cannot create/manage other users (no UserViewSet access).
- Avatar upload available.

**Role Hierarchy:**
- OWNER: Can update self only.
- CENTER_ADMIN: Can update self only (use UserViewSet for other users).
- TEACHER: Can update self only (use UserViewSet for students).
- STUDENT/GUEST: Can update self only.

All roles use this endpoint for self-service updates. Management of other users is via UserViewSet.
"""

ME_PARTIAL_UPDATE_DESCRIPTION = """
**Update the authenticated user's profile (partial update).**

Send only the fields you want to change. Other fields remain unchanged.

Example: Update only first name and city.
"""

me_schema_view = extend_schema_view(
    get=extend_schema(
        tags=["Authentication"],
        summary="Get current user profile",
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
                    "bio": "JLPT N5 student preparing for exam.",
                    "address": "123 Main St, Apt 4B",
                    "city": "Tashkent",
                    "emergency_contact_phone": "+998901234567",
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
        description=ME_PARTIAL_UPDATE_DESCRIPTION,
        request=UserSerializer,
        examples=[
            OpenApiExample(
                "Partial update (name only)",
                value={"first_name": "Jane", "last_name": "Smith"},
                request_only=True,
            ),
            OpenApiExample(
                "Partial update (bio only)",
                value={"bio": "Updated bio text here."},
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
# LOGOUT ENDPOINT
# =============================================================================

LOGOUT_DESCRIPTION = """
**Blacklist a refresh token to prevent reuse.**

Call this endpoint when the user logs out. The refresh token is invalidated and 
can no longer be used to obtain new access tokens.

**Request Body:**
The `refresh` token (as a string) must be included in the JSON request body, NOT 
in the Authorization header. This is the same token returned by the Login endpoint.

**Access Token:**
The access token does NOT need to be sent and will expire naturally. Blacklisting 
the refresh token prevents silent re-authentication.

**After Logout:**
- Access token remains valid until expiration (typically 5 minutes).
- Refresh token is invalidated immediately.
- Client should discard both tokens (clear localStorage/sessionStorage).
- Next API call with expired access will fail unless client obtains new tokens 
  (which requires the now-blacklisted refresh token).

**Security:**
Logout cannot fail (always returns 205). If the token is already invalid, 
the operation completes successfully. Prevents information disclosure.
"""

logout_schema = extend_schema(
    tags=["Authentication"],
    summary="Logout (blacklist refresh token)",
    description=LOGOUT_DESCRIPTION,
    request=LogoutRequestSerializer,
    examples=[
        OpenApiExample(
            "Logout request",
            value={"refresh": "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.eyJzdWIiOjEsImV4cCI6MTY0OTM3MTIwMH0.ghijkl..."},
            request_only=True,
            description="Include the refresh token from Login response. NOT in Authorization header.",
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
            description="Missing or invalid refresh token in request body.",
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
# UPDATE PASSWORD ENDPOINT
# =============================================================================

UPDATE_PASSWORD_DESCRIPTION = """
**Change the authenticated user's password.**

Requires the current password for verification. New password must pass Django's 
password validation:
- Minimum 8 characters (recommended).
- Cannot be entirely numeric.
- Cannot be a common password (e.g., 'password123').
- Cannot match user's email or name.

**Security:**
- Authenticated user only (requires valid JWT access token).
- Old password checked against stored hash.
- New password validated before update.
- Session remains valid after change; no re-login required.

**After Password Change:**
All active refresh tokens remain valid. Users can refresh if needed, but 
in production consider blacklisting old tokens for maximum security.
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
                "old_password": "CurrentPassword123",
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
            description="Validation error: wrong old password or new password fails validation.",
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
                OpenApiExample(
                    "New password too similar to email",
                    value={"new_password": ["The password is too similar to the email address."]},
                    response_only=True,
                ),
                OpenApiExample(
                    "New password too short",
                    value={"new_password": ["This password is too short. It must contain at least 8 characters."]},
                    response_only=True,
                ),
            ],
        ),
        401: RESP_401_UNAUTHORIZED,
    },
)


# =============================================================================
# PASSWORD RESET REQUEST ENDPOINT
# =============================================================================

PASSWORD_RESET_REQUEST_DESCRIPTION = """
**Request a password reset email.**

If the email exists in the system and belongs to an active user, a time-limited 
reset link is sent to that email address. Throttled per IP to prevent abuse.

**Security:**
The API always returns the same success message (200) whether the email exists or not.
This prevents attackers from enumerating valid email addresses in the system.

**Email Content:**
Reset email includes:
- Personalized greeting with user's first name.
- Reset link: `{FRONTEND_URL}/auth/forgot-password/password/?uid=<uid>&token=<token>`
- Token validity: 24 hours.
- Instructions to ignore if they didn't request the reset.

**Rate Limiting:**
- 5 requests per hour per email address.
- 429 Too Many Requests if exceeded.

**Frontend Implementation:**
1. User enters email on forgot-password page.
2. Frontend calls this endpoint.
3. Frontend shows: "If that email is registered, you will receive a reset link."
4. Frontend navigates to password reset form (same regardless of success/failure).
5. User extracts `uid` and `token` from email link.
6. Frontend calls POST /api/v1/auth/password-reset-confirm/ with new password.
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
            description="Password reset request processed. Same message regardless of email existence.",
            examples=[
                OpenApiExample(
                    "Success (or email not found)",
                    value={"detail": "Password reset email sent."},
                    response_only=True,
                    description="Always returns this message for security (prevents email enumeration).",
                ),
            ],
        ),
        400: OpenApiResponse(
            description="Invalid email format.",
            examples=[
                OpenApiExample(
                    "Invalid email format",
                    value={"email": ["Enter a valid email address."]},
                    response_only=True,
                ),
            ],
        ),
        429: RESP_429_THROTTLED,
    },
)


# =============================================================================
# PASSWORD RESET CONFIRM ENDPOINT
# =============================================================================

PASSWORD_RESET_CONFIRM_DESCRIPTION = """
**Set a new password using the reset link from email.**

The email contains a reset link: `...?uid=<uid>&token=<token>`

Extract `uid` and `token` from the URL and send them here along with the new password.

**URL Parameters from Email Link:**

- **uid**: Base64-encoded user ID (example: "Mw==" for user ID 3).
- **token**: Time-limited token generated by Django's PasswordResetTokenGenerator.
  - Valid for 24 hours from reset request.
  - Contains hash of user ID and password, so token becomes invalid if password changed.

**Validation:**
Both uid and token must be valid and correspond to an existing active user. 
Invalid or expired links return a generic error (doesn't reveal whether uid is valid).

**New Password Requirements:**
Must pass Django password validation (same rules as Update Password endpoint).

**Security:**
- Links expire after 24 hours.
- Token is one-time use (becomes invalid after password change).
- Password must be different from current password.
- Account must be active (is_active=True).
- Throttled (5 attempts per hour per IP).

**After Reset:**
User can immediately log in with new password. 
All existing refresh tokens remain valid (refresh new access as needed).
"""

password_reset_confirm_schema = extend_schema(
    tags=["Authentication"],
    summary="Confirm password reset with token",
    description=PASSWORD_RESET_CONFIRM_DESCRIPTION,
    request=PasswordResetConfirmSerializer,
    examples=[
        OpenApiExample(
            "Confirm reset (from email link)",
            value={
                "uid": "Mw==",
                "token": "abc123-def456-ghi789-jkl012",
                "new_password": "NewSecurePassword789!",
            },
            request_only=True,
            description="uid is base64-encoded user ID from email link. Token is time-limited.",
        ),
    ],
    responses={
        201: OpenApiResponse(
            description="Password reset successfully; user can log in with new password.",
        ),
        400: OpenApiResponse(
            description="Invalid or expired link, malformed uid/token, or password validation failed.",
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
                OpenApiExample(
                    "Password validation failed",
                    value={"new_password": ["This password is too common."]},
                    response_only=True,
                ),
            ],
        ),
        429: RESP_429_THROTTLED,
    },
)


# =============================================================================
# USER MANAGEMENT VIEWSET
# =============================================================================

USERS_LIST_DESCRIPTION = """
**List users in the current center (tenant).**

The center is determined by the authenticated user's JWT (`center_id` in token).

**Role-Based Visibility & Permissions:**

1. **CENTER_ADMIN:**
   - Sees ALL users in the center (all roles).
   - Full CRUD: create, retrieve, update, delete users.
   - Can filter by role, is_active, is_approved.
   - Can search by first_name, last_name, email.
   - Can order by created_at, last_login, first_name, last_name, email.

2. **TEACHER:**
   - Sees ONLY students (role=STUDENT or GUEST) who are in groups they teach.
   - Can only retrieve (list/get) students; cannot create/update/delete (403).
   - Same filters/search/ordering apply to this subset of students.
   - To see all students in center, ask CENTER_ADMIN.

3. **STUDENT / GUEST:**
   - Cannot access this endpoint at all (403 Forbidden).
   - Use GET /api/v1/auth/me/ to retrieve own profile.

**Batch Optimization:**
The `center_avatar` field is pre-fetched in batches to prevent N+1 queries.
Each user may have a center with an avatar URL.

**Response Fields:**

All users return UserListSerializer:
- `id`, `email`, `first_name`, `last_name`, `avatar`
- `role`, `center` (ID), `center_avatar` (URL or null)
- `is_approved`, `created_at`

Note: `my_groups` is NOT included in list (performance). 
Use retrieve endpoint for detailed user info with groups.

**Pagination:**
Results are paginated. Use `page` and `page_size` query parameters.
"""

USERS_RETRIEVE_DESCRIPTION = """
**Retrieve a single user in the current center.**

Same visibility rules as list:
- CENTER_ADMIN sees any user in the center.
- TEACHER sees only students in their teaching groups.

Returns UserManagementSerializer with full detail including `my_groups`.
"""

USERS_CREATE_DESCRIPTION = """
**Create a new user in the center.**

**Permission:** CENTER_ADMIN only. Teachers receive 403.

**Required Fields:**
- `email` (must be unique across the entire platform)
- `first_name`, `last_name`
- `role` (one of: "TEACHER", "STUDENT"; GUEST is auto-assigned, OWNER/CENTER_ADMIN via admin)
- `password` (minimum 6 characters; longer recommended)

**Optional Fields:**
- `avatar` (image URL or null)
- `is_active` (default: True)

**After Creation:**
- User created with `is_approved=False` by default (CENTER_ADMIN can set True).
- User is immediately active (`is_active=True`) unless set otherwise.
- User can log in after approval.

**Email Uniqueness:**
Email must be unique across the entire platform. The same email cannot exist in any other center.
"""

USERS_UPDATE_DESCRIPTION = """
**Update a user in the center (full update).**

**Permission:** CENTER_ADMIN only. Teachers receive 403.

**Writable Fields:**
- `first_name`, `last_name`
- `avatar`
- `is_active` (True/False; disabling prevents login)
- `is_approved` (True/False; required before user can log in)

**Read-Only Fields:**
- `id`, `email`, `role`, `created_at`

Cannot change email or role after creation (use delete + recreate if needed).
"""

USERS_PARTIAL_UPDATE_DESCRIPTION = """
**Partially update a user in the center.**

**Permission:** CENTER_ADMIN only. Teachers receive 403.

Send only the fields you want to change. Other fields remain unchanged.

Common use cases:
- Approve user: `{"is_approved": true}`
- Disable user: `{"is_active": false}`
- Update name: `{"first_name": "Jane", "last_name": "Doe"}`
"""

USERS_DESTROY_DESCRIPTION = """
**Soft-delete a user in the center.**

**Permission:** CENTER_ADMIN only. Teachers receive 403.

**Soft Delete Behavior:**
- User is marked as deleted in database (soft delete).
- User is IMMEDIATELY barred from logging in.
- User is excluded from all default querysets (lists, searches).
- User's data is preserved (can be restored by database admin if needed).
- Hard delete is not available via API (requires database access).

**After Deletion:**
- User cannot log in (authentication fails).
- User does not appear in list endpoints.
- User's ID cannot be reused (soft-deleted record preserved).
- Assignments/submissions remain (orphaned but preserved).

**Cannot Undo via API:**
No "restore" endpoint. Contact system administrator for recovery.
"""

user_viewset_schema = extend_schema_view(
    list=extend_schema(
        tags=["Users"],
        summary="List center users",
        description=USERS_LIST_DESCRIPTION,
        parameters=[
            OpenApiParameter(
                name="role",
                type=str,
                enum=["TEACHER", "STUDENT", "GUEST", "CENTER_ADMIN"],
                description="Filter by role.",
            ),
            OpenApiParameter(
                name="is_active",
                type=bool,
                description="Filter by active status.",
            ),
            OpenApiParameter(
                name="is_approved",
                type=bool,
                description="Filter by approval status.",
            ),
            OpenApiParameter(
                name="search",
                type=str,
                description="Search across first_name, last_name, email.",
            ),
            OpenApiParameter(
                name="ordering",
                type=str,
                description="Order by field: created_at, last_login, first_name, last_name, email. Prefix with '-' for descending.",
            ),
            OpenApiParameter(
                name="page",
                type=int,
                description="Page number (pagination).",
            ),
            OpenApiParameter(
                name="page_size",
                type=int,
                description="Items per page (default: 20).",
            ),
        ],
        responses={
            200: UserListSerializer(many=True),
            401: RESP_401_UNAUTHORIZED,
            403: OpenApiResponse(
                description="Forbidden: only CENTER_ADMIN and TEACHER can list users.",
            ),
        },
    ),
    retrieve=extend_schema(
        tags=["Users"],
        summary="Get center user details",
        description=USERS_RETRIEVE_DESCRIPTION,
        responses={
            200: UserManagementSerializer,
            401: RESP_401_UNAUTHORIZED,
            403: RESP_403_FORBIDDEN,
            404: RESP_404_NOT_FOUND,
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
                    "email": "newteacher@edu.center",
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
                    "email": "student@edu.center",
                    "first_name": "Bob",
                    "last_name": "Student",
                    "role": "STUDENT",
                    "password": "StudentPass1",
                    "is_active": True,
                },
                request_only=True,
            ),
        ],
        responses={
            201: UserManagementSerializer,
            400: OpenApiResponse(
                description="Validation error.",
                examples=[
                    OpenApiExample(
                        "Duplicate email",
                        value={"email": ["A user with this email already exists."]},
                        response_only=True,
                    ),
                    OpenApiExample(
                        "Invalid role",
                        value={"role": ["Not a valid choice. Choose from: TEACHER, STUDENT."]},
                        response_only=True,
                    ),
                ],
            ),
            401: RESP_401_UNAUTHORIZED,
            403: OpenApiResponse(
                description="Forbidden: only CENTER_ADMIN can create users.",
            ),
        },
    ),
    update=extend_schema(
        tags=["Users"],
        summary="Update center user (full)",
        description=USERS_UPDATE_DESCRIPTION,
        request=UserManagementSerializer,
        examples=[
            OpenApiExample(
                "Update and approve user",
                value={
                    "first_name": "Alice",
                    "last_name": "Updated",
                    "is_active": True,
                    "is_approved": True,
                },
                request_only=True,
            ),
            OpenApiExample(
                "Disable user",
                value={
                    "is_active": False,
                },
                request_only=True,
            ),
        ],
        responses={
            200: UserManagementSerializer,
            400: RESP_400_INVALID,
            401: RESP_401_UNAUTHORIZED,
            403: OpenApiResponse(
                description="Forbidden: only CENTER_ADMIN can update users.",
            ),
            404: RESP_404_NOT_FOUND,
        },
    ),
    partial_update=extend_schema(
        tags=["Users"],
        summary="Update center user (partial)",
        description=USERS_PARTIAL_UPDATE_DESCRIPTION,
        request=UserManagementSerializer,
        examples=[
            OpenApiExample(
                "Approve user",
                value={"is_approved": True},
                request_only=True,
            ),
            OpenApiExample(
                "Update name only",
                value={"first_name": "Jane", "last_name": "Doe"},
                request_only=True,
            ),
        ],
        responses={
            200: UserManagementSerializer,
            400: RESP_400_INVALID,
            401: RESP_401_UNAUTHORIZED,
            403: OpenApiResponse(
                description="Forbidden: only CENTER_ADMIN can update users.",
            ),
            404: RESP_404_NOT_FOUND,
        },
    ),
    destroy=extend_schema(
        tags=["Users"],
        summary="Delete center user (soft delete)",
        description=USERS_DESTROY_DESCRIPTION,
        responses={
            204: OpenApiResponse(
                description="User soft-deleted successfully. User is immediately barred from login.",
            ),
            401: RESP_401_UNAUTHORIZED,
            403: OpenApiResponse(
                description="Forbidden: only CENTER_ADMIN can delete users.",
            ),
            404: RESP_404_NOT_FOUND,
        },
    ),
)


# =============================================================================
# AVATAR UPLOAD ENDPOINT
# =============================================================================

AVATAR_UPLOAD_DESCRIPTION = """
**Upload or replace the authenticated user's avatar image.**

**Content-Type:** Must be `multipart/form-data` (NOT JSON).

**Form Field:** 
Name the file input `avatar`. Send the image file as binary data.

**Accepted Image Formats:**
- JPEG / JPG (`image/jpeg`)
- PNG (`image/png`)
- GIF (`image/gif`)
- WebP (`image/webp`)

**File Size Limits:**
- Maximum file size: 10 MB (server configuration may vary).
- Recommended: Images < 5 MB for optimal performance.

**Image Validation:**
- Uploaded file must be a valid image (PIL/Pillow verified).
- Corrupted or invalid files are rejected with 400.
- Archive files, executables, or non-image files are rejected.

**Behavior:**
- If user already has an avatar, it is **replaced** (old file deleted).
- If no avatar file provided, returns 400.
- Successful upload returns updated user object with new avatar URL.

**URL Storage:**
Avatar URLs are stored as relative paths in database. 
Frontend receives full URL (e.g., `https://cdn.mikan.uz/avatars/user_123.jpg`).

**Implementation Note (Frontend):**
Use `FormData` in JavaScript:

```javascript
const formData = new FormData();
formData.append('avatar', fileInputElement.files[0]);

fetch('/api/v1/auth/avatar-upload/', {
    method: 'POST',
    headers: {'Authorization': `Bearer ${accessToken}`},
    body: formData,  // NOT stringified; sent as multipart
});
```

Do NOT set Content-Type header; browser will set it automatically with boundary.
"""

avatar_upload_schema = extend_schema(
    tags=["Authentication"],
    summary="Upload user avatar",
    description=AVATAR_UPLOAD_DESCRIPTION,
    request={
        "multipart/form-data": {
            "type": "object",
            "required": ["avatar"],
            "properties": {
                "avatar": {
                    "type": "string",
                    "format": "binary",
                    "description": "Image file (JPEG, PNG, GIF, WebP). Form field name MUST be 'avatar'.",
                },
            },
        }
    },
    examples=[
        OpenApiExample(
            "Upload avatar (multipart/form-data)",
            value={"avatar": "(binary image file)"},
            request_only=True,
            description=(
                "Send as multipart/form-data. Form field name: 'avatar'. "
                "Accepted MIME types: image/jpeg, image/png, image/gif, image/webp."
            ),
        ),
    ],
    responses={
        200: OpenApiResponse(
            description="Avatar uploaded successfully; returns updated user object.",
            examples=[
                OpenApiExample(
                    "Success",
                    value={
                        "id": 1,
                        "email": "user@example.com",
                        "first_name": "John",
                        "avatar": "https://cdn.mikan.uz/avatars/user_1.jpg",
                        "role": "STUDENT",
                        "is_approved": True,
                    },
                    response_only=True,
                ),
            ],
        ),
        400: OpenApiResponse(
            description="No avatar file provided or invalid image.",
            examples=[
                OpenApiExample(
                    "No file provided",
                    value={"avatar": ["No avatar file provided."]},
                    response_only=True,
                ),
                OpenApiExample(
                    "Invalid image file",
                    value={"avatar": ["Invalid image file."]},
                    response_only=True,
                    description="File is not a valid image or is corrupted.",
                ),
            ],
        ),
        401: RESP_401_UNAUTHORIZED,
    },
)
