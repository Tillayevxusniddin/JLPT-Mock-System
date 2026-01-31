"""
OpenAPI / Swagger documentation for the Materials app.

Enterprise-level API documentation for secure file uploads and access control.
Materials and files live in the **tenant schema**; files are stored in S3 (or
default storage) with tenant-isolated paths. All create/update operations use
**multipart/form-data** with strict MIME-type and extension validation.

Tags: **Materials** (list, retrieve, create, update, partial_update, destroy).

Role-based visibility (get_queryset):
- **CENTER_ADMIN** & **TEACHER:** See and manage all materials in the center.
- **STUDENT:** See only materials where `is_public=True` OR material is assigned
  to at least one group the student belongs to.
- **GUEST:** No access (empty list or 403).

Permission logic:
- **Create:** CENTER_ADMIN or TEACHER only.
- **Update / Delete:** CENTER_ADMIN can edit or delete any material; TEACHER can
  only edit or delete materials they uploaded (created_by_id = user.id).
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
**Strict MIME-type and extension rules (create and update):**

| file_type | Allowed extensions | Allowed MIME types |
|-----------|--------------------|--------------------|
| **PDF**   | `.pdf`             | `application/pdf` |
| **AUDIO** | `.mp3`, `.wav`, `.ogg` | `audio/mpeg`, `audio/mp3`, `audio/wav`, `audio/ogg`, `audio/x-wav` |
| **IMAGE** | `.jpg`, `.jpeg`, `.png` | `image/jpeg`, `image/jpg`, `image/png` |
| **DOCX**  | `.doc`, `.docx`    | `application/msword`, `application/vnd.openxmlformats-officedocument.wordprocessingml.document` |
| **OTHER** | (any)              | (no strict check) |

A **mismatch** between `file_type` and the actual file (extension or Content-Type)
results in **400 Bad Request** with a message indicating the allowed values.
"""


# =============================================================================
# Materials ViewSet
# =============================================================================

MATERIALS_LIST_DESCRIPTION = f"""
List materials. **Visibility (get_queryset):**
- **CENTER_ADMIN** & **TEACHER:** See **all** materials in the center.
- **STUDENT:** See only materials where `is_public=True` **or** the material is
  assigned to at least one group the student belongs to.
- **GUEST:** No access (empty list).

**Performance:** The `created_by` field is populated via **batch-fetching** from
the **public schema** in a single query for all materials on the page (zero N+1
schema switching).

**Filters:** `file_type`, `is_public`. **Search:** `name`. **Ordering:** `created_at`, `name` (default: -created_at).
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

**Resource cleanup:** Deleting a material record **also triggers physical deletion**
of the file from S3 (or default storage) via a post_delete signal. The file is
removed from storage; this action is irreversible.
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
    ),
    create=extend_schema(
        tags=["Materials"],
        summary="Create material",
        description=MATERIALS_CREATE_DESCRIPTION,
        request=MULTIPART_CREATE_SCHEMA,
        responses={
            201: MaterialSerializer,
            400: OpenApiResponse(
                description="Validation error: MIME/extension mismatch, group_ids not found, or invalid payload.",
                examples=[
                    OpenApiExample(
                        "Extension mismatch",
                        value={"file": "File extension '.txt' does not match file_type 'PDF'. Allowed: .pdf."},
                        response_only=True,
                    ),
                    OpenApiExample(
                        "MIME mismatch",
                        value={"file": "File MIME type 'text/plain' does not match file_type 'PDF'. Expected: application/pdf."},
                        response_only=True,
                    ),
                    OpenApiExample(
                        "Groups not found",
                        value={"group_ids": "One or more groups not found."},
                        response_only=True,
                    ),
                ],
            ),
            401: RESP_401,
            403: OpenApiResponse(description="Only CENTER_ADMIN or TEACHER can create materials."),
        },
        examples=[
            OpenApiExample(
                "Create (multipart/form-data)",
                value={
                    "name": "JLPT N5 Vocabulary List",
                    "file": "(binary file)",
                    "file_type": "PDF",
                    "is_public": True,
                    "group_ids": [],
                },
                request_only=True,
                description="POST as multipart/form-data; use the file upload button for 'file'.",
            ),
            OpenApiExample(
                "Create with group assignment",
                value={
                    "name": "Week 1 Audio",
                    "file": "(binary file)",
                    "file_type": "AUDIO",
                    "is_public": False,
                    "group_ids": ["550e8400-e29b-41d4-a716-446655440000"],
                },
                request_only=True,
                description="Assign material to specific groups; students in those groups can see it.",
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
                description="Forbidden: TEACHER can only update materials they uploaded.",
            ),
            404: RESP_404,
        },
        examples=[
            OpenApiExample(
                "PUT (multipart/form-data)",
                value={
                    "name": "Updated material name",
                    "file": "(binary file)",
                    "file_type": "PDF",
                    "is_public": False,
                    "group_ids": ["550e8400-e29b-41d4-a716-446655440000"],
                },
                request_only=True,
                description="Full update; file and file_type validated together if both sent.",
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
                description="Material deleted; physical file removed from S3/storage.",
            ),
            401: RESP_401,
            403: OpenApiResponse(
                description="Forbidden: TEACHER can only delete materials they uploaded.",
            ),
            404: RESP_404,
        },
    ),
)
