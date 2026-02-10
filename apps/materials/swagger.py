"""
OpenAPI / Swagger documentation for the Materials app.

Enterprise-level API documentation for secure file uploads and access control.
Materials and files live in the **tenant schema**; files are stored in S3 (or
default storage) with tenant-isolated paths. All create/update operations use
**multipart/form-data** with strict MIME-type and extension validation.

Tags: **Materials** (list, retrieve, create, update, partial_update, destroy).

================================================================================
ROLE-BASED ACCESS CONTROL (RBAC)
================================================================================

**Visibility (get_queryset):**

| Role          | Can See                                                    |
|---------------|------------------------------------------------------------|
| CENTER_ADMIN  | ALL materials in the center                               |
| TEACHER       | ALL materials in the center                               |
| STUDENT       | Only: is_public=True OR assigned to student's groups      |
| GUEST         | NOTHING (empty queryset)                                   |

**Student Visibility Matrix:**

| Material State                              | Student Can See? |
|---------------------------------------------|------------------|
| is_public=True                              | ✅ Always         |
| is_public=False, student in assigned group  | ✅ Yes            |
| is_public=False, student NOT in any group   | ❌ Hidden         |

**Permission Logic:**

| Action         | CENTER_ADMIN | TEACHER              | STUDENT | GUEST |
|----------------|--------------|----------------------|---------|-------|
| List/Retrieve  | ✅ All        | ✅ All                | ✅ Filtered | ❌     |
| Create         | ✅            | ✅                    | ❌       | ❌     |
| Update         | ✅ Any        | ✅ Own materials only | ❌       | ❌     |
| Delete         | ✅ Any        | ✅ Own materials only | ❌       | ❌     |

**Ownership Check:** TEACHER can only update/delete materials where 
`created_by_id` matches their user ID. CENTER_ADMIN bypasses this check.

================================================================================
SECURITY: MIME SPOOFING PROTECTION
================================================================================

**Content-based MIME Detection (not header-based):**

The serializer's `validate()` method reads the **first 512 bytes of the uploaded
file** (magic bytes) to detect the true MIME type, preventing spoofing attacks.

**Attack Prevention Example:**
- Attacker renames `malware.exe` → `document.pdf`
- Sets HTTP header `Content-Type: application/pdf`
- **Validation Result:** ❌ REJECTED
  - Magic bytes detector reads `4D 5A` (PE executable signature)
  - Actual MIME: `application/x-dosexec`
  - Expected for PDF: `application/pdf`
  - Returns 400: "File MIME type 'application/x-dosexec' does not match..."

**Implementation:**
1. Primary: Uses `python-magic` library (libmagic wrapper) for content analysis
2. Fallback: Uses Python's `mimetypes.guess_type()` based on filename
3. Validation: Compares detected MIME against ALLOWED_MIME_TYPES dict

**Why This Matters:** Prevents execution of malicious files disguised as 
documents/media, protecting users from drive-by downloads and XSS attacks.

================================================================================
PERFORMANCE OPTIMIZATION
================================================================================

**created_by Batch Fetch (user_map):**

The `list()` view implements zero-N+1 optimization for cross-schema user lookups:

1. **Collect:** Gather all unique `created_by_id` values from paginated materials
2. **Batch Fetch:** Execute ONE query in public schema: `User.objects.filter(id__in=user_ids)`
3. **Cache:** Store as `user_map = {user_id: User}` in serializer context
4. **Serialize:** MaterialSerializer.get_created_by() uses cached user_map

**Impact:** 20 materials = 1 public schema query (not 20), avoiding expensive
per-row schema switching in multi-tenant PostgreSQL.

================================================================================
FIELD STRUCTURE REFERENCE
================================================================================

**Request Fields (multipart/form-data):**

- `name` (string, required): Display name of the material
- `file` (binary, required): File upload using field name 'file'
- `file_type` (enum, required): AUDIO | PDF | DOCX | IMAGE | OTHER
- `is_public` (boolean, optional): Default false. If true, all students see it.
- `group_ids` (array[uuid], write-only): Assign to specific groups (not needed if is_public=true)

**Response Fields (JSON):**

- `id` (uuid): Material unique identifier
- `name` (string): Display name
- `file` (string): Full S3/CloudFront URL (e.g., https://cdn.example.com/tenants/123/materials/vocab.pdf)
- `file_type` (enum): AUDIO | PDF | DOCX | IMAGE | OTHER
- `file_size` (integer): File size in bytes (added by storage backend)
- `created_by` (object): UserSummarySerializer with {id, email, full_name, role}
- `is_public` (boolean): Visibility flag
- `groups` (array, read-only): Array of {id, name} for assigned groups
- `created_at` (datetime): ISO 8601 timestamp
- `updated_at` (datetime): ISO 8601 timestamp

**Note:** `group_ids` (write) vs `groups` (read) - request sends UUIDs, response 
returns full Group objects with id+name.
"""
from drf_spectacular.utils import (
    OpenApiExample,
    OpenApiParameter,
    OpenApiResponse,
    extend_schema,
    extend_schema_view,
)

from .serializers import MaterialSerializer

# -----------------------------------------------------------------------------
# Reusable responses
# -----------------------------------------------------------------------------

RESP_400 = OpenApiResponse(
    description="Bad Request: validation error (MIME/extension mismatch, group_ids not found, etc.).",
)
RESP_401 = OpenApiResponse(description="Unauthorized: authentication required.")
RESP_403 = OpenApiResponse(
    description="Forbidden: not CENTER_ADMIN/TEACHER for create; or not owner/admin for update/delete.",
)
RESP_404 = OpenApiResponse(description="Not Found: material not found or not visible to this user.")


# -----------------------------------------------------------------------------
# Multipart request schema (file = binary for Swagger UI file upload)
# -----------------------------------------------------------------------------

MULTIPART_CREATE_SCHEMA = {
    "multipart/form-data": {
        "type": "object",
        "required": ["name", "file", "file_type"],
        "properties": {
            "name": {"type": "string", "description": "Display name of the material."},
            "file": {"type": "string", "format": "binary", "description": "The file to upload (must match file_type)."},
            "file_type": {
                "type": "string",
                "enum": ["AUDIO", "PDF", "DOCX", "IMAGE", "OTHER"],
                "description": "Type of file; extension and MIME must match (see description).",
            },
            "is_public": {"type": "boolean", "description": "If true, visible to all students in the center."},
            "group_ids": {
                "type": "array",
                "items": {"type": "string", "format": "uuid"},
                "description": "List of group UUIDs to assign this material to (if not public).",
            },
        },
    }
}

MULTIPART_UPDATE_SCHEMA = {
    "multipart/form-data": {
        "type": "object",
        "properties": {
            "name": {"type": "string"},
            "file": {"type": "string", "format": "binary"},
            "file_type": {"type": "string", "enum": ["AUDIO", "PDF", "DOCX", "IMAGE", "OTHER"]},
            "is_public": {"type": "boolean"},
            "group_ids": {"type": "array", "items": {"type": "string", "format": "uuid"}},
        },
    }
}


# -----------------------------------------------------------------------------
# MIME & extension rules (for descriptions)
# -----------------------------------------------------------------------------

MIME_EXTENSION_RULES = """
**Strict MIME-type and extension rules (enforced via content analysis, not headers):**

| file_type | Allowed extensions | Allowed MIME types (detected from file content) |
|-----------|--------------------|-------------------------------------------------|
| **PDF**   | `.pdf`             | `application/pdf` |
| **AUDIO** | `.mp3`, `.wav`, `.ogg` | `audio/mpeg`, `audio/mp3`, `audio/wav`, `audio/ogg`, `audio/x-wav`, `audio/wave`, `audio/vorbis` |
| **IMAGE** | `.jpg`, `.jpeg`, `.png` | `image/jpeg`, `image/jpg`, `image/png` |
| **DOCX**  | `.doc`, `.docx`    | `application/msword`, `application/vnd.openxmlformats-officedocument.wordprocessingml.document` |
| **OTHER** | (any)              | (no strict MIME validation) |

**Validation Process:**
1. **Extension Check:** File name must end with allowed extension for file_type
2. **Content Analysis:** First 512 bytes read to detect true MIME type (magic bytes)
3. **MIME Verification:** Detected MIME must match expected types for file_type

**Security:** Renaming `malware.exe` to `document.pdf` will **fail validation** 
because content-based detection identifies the true file type, not the filename 
or HTTP headers.

**Failure Result:** 400 Bad Request with specific error message indicating the 
mismatch (extension or MIME) and listing allowed values.
"""


# =============================================================================
# Materials ViewSet
# =============================================================================

MATERIALS_LIST_DESCRIPTION = f"""
List materials with **role-based filtering** (see RBAC matrix in module docstring).

**Visibility Rules:**

- **CENTER_ADMIN & TEACHER:** See **all** materials in the center (no filtering).
- **STUDENT:** See only materials where:
  - `is_public=True` (public to all students), **OR**
  - Material is assigned to at least one group the student belongs to via GroupMembership
- **GUEST:** Empty list (no access).

**Student Examples:**
- Student in Group A: Sees public materials + materials assigned to Group A
- Student not in any group: Sees only public materials
- Private material assigned to Group B: Hidden from students not in Group B

**Performance Optimization (user_map):**

The `created_by` field requires cross-schema lookup (User in public, Material in tenant).
To avoid N+1 queries (20 materials = 20 schema switches), the view implements:

1. Collect all `created_by_id` from paginated materials (e.g., 20 IDs)
2. Execute **one batch query** in public schema: `User.objects.filter(id__in=user_ids)`
3. Build `user_map = {{user_id: User}}` and pass to serializer context
4. Serializer uses cached map: zero additional queries

**Result:** 20 materials = 1 public schema query (was 20 without optimization).

**Filters:** `file_type` (AUDIO|PDF|DOCX|IMAGE|OTHER), `is_public` (true|false).  
**Search:** `name` (case-insensitive partial match).  
**Ordering:** `created_at`, `name` (default: `-created_at`).
"""

MATERIALS_RETRIEVE_DESCRIPTION = """
Retrieve a single material. Same visibility rules as list: CENTER_ADMIN/TEACHER
see any; STUDENT only if is_public or assigned to their group; GUEST gets 404.
"""

MATERIALS_CREATE_DESCRIPTION = f"""
Create a material. **CENTER_ADMIN** or **TEACHER** only. Students and guests receive **403 Forbidden**.

**Request:** Must be **multipart/form-data**. Required: `name`, `file` (binary), `file_type`.
Optional: `is_public`, `group_ids` (list of group UUIDs).

{MIME_EXTENSION_RULES}
"""

MATERIALS_UPDATE_DESCRIPTION = f"""
Full update of a material. **CENTER_ADMIN** can update any material; **TEACHER**
can update **only** materials they uploaded (`created_by_id` = their user id).
Students and guests receive **403**.

**Request:** **multipart/form-data**. Include only fields to change. If both `file`
and `file_type` are sent, they are validated together (extension and MIME must match file_type).

{MIME_EXTENSION_RULES}
"""

MATERIALS_PARTIAL_UPDATE_DESCRIPTION = f"""
Partial update. Same permissions as full update (CENTER_ADMIN any; TEACHER only own).
Send as **multipart/form-data** with only the fields you want to change. If you
send a new `file`, you may send `file_type` as well; both are validated together.
"""

MATERIALS_DESTROY_DESCRIPTION = """
Delete a material. **CENTER_ADMIN** can delete any; **TEACHER** only materials they uploaded.

**⚠️ IRREVERSIBLE OPERATION:**

Deleting a material triggers **permanent physical file deletion** from S3/storage:

1. Material record soft-deleted in database (is_deleted=True)
2. **post_delete signal** fires and removes file from S3 bucket
3. File URL becomes inaccessible (404 Not Found)
4. **No recovery possible** - file is permanently gone from storage

**Use Case Warning:** Ensure users are not actively downloading/viewing the material
before deletion. Consider implementing a "deactivate" feature instead of hard delete
for production environments.

**Permissions:** CENTER_ADMIN can delete any material; TEACHER can only delete 
materials where `created_by_id` matches their user ID.
"""

material_viewset_schema = extend_schema_view(
    list=extend_schema(
        tags=["Materials"],
        summary="List materials",
        description=MATERIALS_LIST_DESCRIPTION,
        parameters=[
            OpenApiParameter(name="search", type=str, description="Search by name"),
            OpenApiParameter(name="file_type", type=str, enum=["AUDIO", "PDF", "DOCX", "IMAGE", "OTHER"]),
            OpenApiParameter(name="is_public", type=bool),
            OpenApiParameter(name="ordering", type=str, description="e.g. -created_at, name"),
        ],
        responses={
            200: MaterialSerializer(many=True),
            401: RESP_401,
            403: RESP_403,
        },
        examples=[
            OpenApiExample(
                "List response (paginated)",
                value={
                    "count": 2,
                    "next": None,
                    "previous": None,
                    "results": [
                        {
                            "id": "550e8400-e29b-41d4-a716-446655440000",
                            "name": "JLPT N5 Vocabulary List",
                            "file": "https://cdn.example.com/tenants/123/materials/n5_vocab.pdf",
                            "file_type": "PDF",
                            "created_by": {
                                "id": 42,
                                "email": "teacher@example.com",
                                "full_name": "John Smith",
                                "role": "TEACHER"
                            },
                            "is_public": True,
                            "groups": [],
                            "created_at": "2026-02-10T10:30:00Z",
                            "updated_at": "2026-02-10T10:30:00Z"
                        },
                        {
                            "id": "660e8400-e29b-41d4-a716-446655440001",
                            "name": "Week 1 Listening Practice",
                            "file": "https://s3.amazonaws.com/jlpt-materials/tenants/123/materials/week1_audio.mp3",
                            "file_type": "AUDIO",
                            "created_by": {
                                "id": 42,
                                "email": "teacher@example.com",
                                "full_name": "John Smith",
                                "role": "TEACHER"
                            },
                            "is_public": False,
                            "groups": [
                                {"id": "770e8400-e29b-41d4-a716-446655440002", "name": "Beginner Group A"}
                            ],
                            "created_at": "2026-02-09T14:20:00Z",
                            "updated_at": "2026-02-09T14:20:00Z"
                        }
                    ]
                },
                response_only=True,
                description="Typical paginated response showing public and group-assigned materials with full S3 URLs."
            ),
        ],
    ),
    retrieve=extend_schema(
        tags=["Materials"],
        summary="Get material",
        description=MATERIALS_RETRIEVE_DESCRIPTION,
        responses={
            200: MaterialSerializer,
            401: RESP_401,
            403: RESP_403,
            404: OpenApiResponse(
                description="Material not found or not visible (e.g. student and material not public/assigned).",
            ),
        },
        examples=[
            OpenApiExample(
                "Single material response",
                value={
                    "id": "550e8400-e29b-41d4-a716-446655440000",
                    "name": "Grammar Exercise Sheet",
                    "file": "https://cdn.cloudfront.net/tenants/123/materials/grammar_n5.pdf",
                    "file_type": "PDF",
                    "created_by": {
                        "id": 15,
                        "email": "admin@center.jp",
                        "full_name": "Tanaka Yuki",
                        "role": "CENTER_ADMIN"
                    },
                    "is_public": False,
                    "groups": [
                        {"id": "aa0e8400-e29b-41d4-a716-446655440010", "name": "Morning Class"},
                        {"id": "bb0e8400-e29b-41d4-a716-446655440011", "name": "Evening Class"}
                    ],
                    "created_at": "2026-02-08T09:15:00Z",
                    "updated_at": "2026-02-10T11:22:00Z"
                },
                response_only=True,
                description="Private material assigned to two groups. Students must be in Morning Class OR Evening Class to access."
            ),
        ],
    ),
    create=extend_schema(
        tags=["Materials"],
        summary="Create material",
        description=MATERIALS_CREATE_DESCRIPTION,
        request=MULTIPART_CREATE_SCHEMA,
        responses={
            201: MaterialSerializer,
            400: OpenApiResponse(
                description="Validation error: MIME/extension mismatch, group_ids not found, corrupted file, or invalid payload.",
                examples=[
                    OpenApiExample(
                        "Extension mismatch",
                        value={"file": "File extension '.txt' does not match file_type 'PDF'. Allowed: .pdf."},
                        response_only=True,
                    ),
                    OpenApiExample(
                        "MIME mismatch (spoofing detected)",
                        value={"file": "File MIME type 'application/x-dosexec' does not match file_type 'PDF'. Expected: application/pdf."},
                        response_only=True,
                        description="Detected when .exe file is renamed to .pdf - content analysis reveals true type."
                    ),
                    OpenApiExample(
                        "MIME mismatch (wrong audio format)",
                        value={"file": "File MIME type 'video/mp4' does not match file_type 'AUDIO'. Expected: audio/mpeg, audio/wav, audio/ogg."},
                        response_only=True,
                    ),
                    OpenApiExample(
                        "Groups not found",
                        value={"group_ids": "One or more groups not found."},
                        response_only=True,
                    ),
                    OpenApiExample(
                        "Corrupted file (MIME detection failed)",
                        value={"file": "Could not detect file type. File may be corrupted or empty."},
                        response_only=True,
                        description="Occurs when magic bytes detection fails and no fallback MIME can be determined."
                    ),
                ],
            ),
            401: RESP_401,
            403: OpenApiResponse(description="Only CENTER_ADMIN or TEACHER can create materials. Students receive 403."),
        },
        examples=[
            OpenApiExample(
                "Create public PDF (multipart/form-data)",
                value={
                    "name": "JLPT N5 Vocabulary List",
                    "file": "(binary file)",
                    "file_type": "PDF",
                    "is_public": True,
                    "group_ids": [],
                },
                request_only=True,
                description="POST as multipart/form-data. Use 'file' as the field name for file upload. Public materials visible to all students.",
            ),
            OpenApiExample(
                "Create private audio with group assignment",
                value={
                    "name": "Week 1 Listening Practice",
                    "file": "(binary file)",
                    "file_type": "AUDIO",
                    "is_public": False,
                    "group_ids": ["550e8400-e29b-41d4-a716-446655440000", "660e8400-e29b-41d4-a716-446655440001"],
                },
                request_only=True,
                description="Private material assigned to two groups. Only students in those groups can access.",
            ),
            OpenApiExample(
                "Successful creation response",
                value={
                    "id": "770e8400-e29b-41d4-a716-446655440002",
                    "name": "JLPT N5 Vocabulary List",
                    "file": "https://s3.amazonaws.com/jlpt-materials/tenants/123/materials/n5_vocab.pdf",
                    "file_type": "PDF",
                    "created_by": {
                        "id": 42,
                        "email": "teacher@example.com",
                        "full_name": "John Smith",
                        "role": "TEACHER"
                    },
                    "is_public": True,
                    "groups": [],
                    "created_at": "2026-02-10T12:45:30Z",
                    "updated_at": "2026-02-10T12:45:30Z"
                },
                response_only=True,
                description="201 Created response with full S3 URL. File is now accessible via the 'file' URL."
            ),
        ],
    ),
    update=extend_schema(
        tags=["Materials"],
        summary="Full update material",
        description=MATERIALS_UPDATE_DESCRIPTION,
        request=MULTIPART_UPDATE_SCHEMA,
        responses={
            200: MaterialSerializer,
            400: RESP_400,
            401: RESP_401,
            403: OpenApiResponse(
                description="Forbidden: TEACHER can only update materials they uploaded (created_by_id must match). CENTER_ADMIN can update any.",
                examples=[
                    OpenApiExample(
                        "Teacher updating another's material",
                        value={"detail": "You do not have permission to perform this action."},
                        response_only=True,
                        description="Teacher attempts to update material uploaded by another teacher."
                    ),
                ],
            ),
            404: RESP_404,
        },
        examples=[
            OpenApiExample(
                "PUT - Full update (multipart/form-data)",
                value={
                    "name": "Updated Vocabulary List",
                    "file": "(binary file)",
                    "file_type": "PDF",
                    "is_public": False,
                    "group_ids": ["550e8400-e29b-41d4-a716-446655440000"],
                },
                request_only=True,
                description="Full update; all fields required. File and file_type validated together if both sent.",
            ),
            OpenApiExample(
                "Update response",
                value={
                    "id": "770e8400-e29b-41d4-a716-446655440002",
                    "name": "Updated Vocabulary List",
                    "file": "https://s3.amazonaws.com/jlpt-materials/tenants/123/materials/n5_vocab_v2.pdf",
                    "file_type": "PDF",
                    "created_by": {
                        "id": 42,
                        "email": "teacher@example.com",
                        "full_name": "John Smith",
                        "role": "TEACHER"
                    },
                    "is_public": False,
                    "groups": [{"id": "550e8400-e29b-41d4-a716-446655440000", "name": "Morning Class"}],
                    "created_at": "2026-02-10T12:45:30Z",
                    "updated_at": "2026-02-10T15:20:10Z"
                },
                response_only=True,
                description="200 OK with updated material. Note: updated_at changed, created_by remains unchanged."
            ),
        ],
    ),
    partial_update=extend_schema(
        tags=["Materials"],
        summary="Partial update material",
        description=MATERIALS_PARTIAL_UPDATE_DESCRIPTION,
        request=MULTIPART_UPDATE_SCHEMA,
        responses={
            200: MaterialSerializer,
            400: RESP_400,
            401: RESP_401,
            403: OpenApiResponse(
                description="Forbidden: TEACHER can only update their own materials.",
            ),
            404: RESP_404,
        },
        examples=[
            OpenApiExample(
                "PATCH (multipart/form-data)",
                value={
                    "name": "New name only",
                },
                request_only=True,
                description="Partial update; send only fields to change.",
            ),
            OpenApiExample(
                "PATCH (replace file)",
                value={
                    "file": "(binary file)",
                    "file_type": "PDF",
                },
                request_only=True,
                description="Replace file; file_type must match the new file.",
            ),
        ],
    ),
    destroy=extend_schema(
        tags=["Materials"],
        summary="Delete material",
        description=MATERIALS_DESTROY_DESCRIPTION,
        responses={
            204: OpenApiResponse(
                description="Material deleted; physical file permanently removed from S3/storage (irreversible).",
            ),
            401: RESP_401,
            403: OpenApiResponse(
                description="Forbidden: TEACHER can only delete materials they uploaded (created_by_id must match).",
                examples=[
                    OpenApiExample(
                        "Teacher deleting another's material",
                        value={"detail": "You do not have permission to perform this action."},
                        response_only=True,
                        description="Teacher attempts to delete material uploaded by CENTER_ADMIN or another teacher."
                    ),
                ],
            ),
            404: RESP_404,
        },
    ),
)
