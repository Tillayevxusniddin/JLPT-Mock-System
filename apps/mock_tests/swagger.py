"""
OpenAPI / Swagger documentation for the mock_tests app.

Enterprise-level API documentation for the 4-level hierarchy: **MockTest** →
**TestSection** → **QuestionGroup (Mondai)** → **Question**. Quizzes are separate:
**Quiz** → **QuizQuestion**.

================================================================================
HIERARCHY STRUCTURE
================================================================================

**MockTest System (Full Exams):**
MockTest (N5/N4/N3/N2/N1, DRAFT/PUBLISHED)
  └─ TestSection (Vocabulary, Grammar, Listening, duration, score)
      └─ QuestionGroup/Mondai (reading_text, audio_file, instruction)
          └─ Question (text, options JSONField, score)

**Quiz System (Standalone Practice):**
Quiz (is_active, default_duration)
  └─ QuizQuestion (text, QUIZ/TRUE_FALSE, options JSONField, points)

**Key Difference:** MockTest hierarchy is for structured exams with sections and time
limits; Quiz is for quick practice questions without sectioning.

================================================================================
ROLE-BASED ACCESS CONTROL (RBAC)
================================================================================

**Visibility (get_queryset):**

| Resource         | CENTER_ADMIN | TEACHER      | STUDENT         | GUEST           |
|------------------|--------------|--------------|-----------------|-----------------|
| MockTest         | All          | All          | PUBLISHED only  | PUBLISHED only  |
| TestSection      | All          | All          | PUBLISHED only  | PUBLISHED only  |
| QuestionGroup    | All          | All          | PUBLISHED only  | PUBLISHED only  |
| Question         | All          | All          | PUBLISHED only  | PUBLISHED only  |
| Quiz             | All          | All          | is_active only  | is_active only  |
| QuizQuestion     | All          | All          | active quiz only| active quiz only|

**Permissions (Create/Update/Delete):**

| Action           | CENTER_ADMIN | TEACHER      | STUDENT | GUEST |
|------------------|--------------|--------------|---------|-------|
| Create MockTest  | ✅           | ✅           | ❌      | ❌    |
| Update MockTest  | ✅ Any       | ✅ Own only  | ❌      | ❌    |
| Delete MockTest  | ✅ Any       | ✅ Own only  | ❌      | ❌    |
| Publish/Unpublish| ✅ Any       | ✅ Own only  | ❌      | ❌    |
| Clone MockTest   | ✅           | ✅           | ❌      | ❌    |

**Ownership Check:** TEACHER can only update/delete/publish MockTests where 
`created_by_id` matches their user ID. CENTER_ADMIN bypasses this check.

================================================================================
PUBLISHED-LOCK SECURITY MECHANISM
================================================================================

**Immutability Rule:** Once a MockTest status is **PUBLISHED**, the test and ALL
its children (TestSection, QuestionGroup, Question) become **read-only**.

**Blocked Operations on PUBLISHED tests:**
- PUT/PATCH on MockTest or any child → 400 "Cannot modify a published test."
- DELETE on MockTest or any child → 400 "Cannot modify a published test."
- POST new TestSection/QuestionGroup/Question → 400 "Cannot modify a published test."

**Rationale:** Prevents mid-exam changes that could invalidate student attempts.
If a student starts a PUBLISHED exam, the questions/structure must remain stable.

**Workaround:** Change MockTest status to DRAFT via `POST /mock-tests/{id}/publish/`
(toggles PUBLISHED ↔ DRAFT), then edit, then republish.

**Enforcement:** Serializers call `validate_mock_test_editable()` and 
`validate_child_object_editable()` in `validate()` method, raising ValidationError
if status is PUBLISHED.

================================================================================
ANSWER PROTECTION (SECURITY)
================================================================================

**Serializer Logic:** QuestionSerializer and QuizQuestionSerializer implement
`to_representation()` to conditionally strip answer fields based on user role.

**Teacher/Admin View (Full Answers):**
```json
{
  "id": "...",
  "text": "彼は毎日学校へ___。",
  "correct_option_index": 1,
  "options": [
    {"text": "いきます", "is_correct": false},
    {"text": "いきました", "is_correct": true},
    {"text": "いって", "is_correct": false}
  ]
}
```

**Student/Guest View (Answers Hidden):**
```json
{
  "id": "...",
  "text": "彼は毎日学校へ___。",
  "options": [
    {"text": "いきます"},
    {"text": "いきました"},
    {"text": "いって"}
  ]
}
```

**Stripped Fields:**
- `correct_option_index` (root level) → Removed entirely
- `is_correct` (inside each option) → Removed from all options

**Purpose:** Prevents students from inspecting API responses to find correct answers
before submitting exam attempts.

================================================================================
PERFORMANCE OPTIMIZATION
================================================================================

**MockTest Retrieve (prefetch_related):**

The `retrieve()` view uses 4-level nested prefetching to load the entire exam
hierarchy in **1 database query** instead of N+1:

```python
prefetch_related(
    Prefetch("sections",
        queryset=TestSection.objects.order_by("order").prefetch_related(
            Prefetch("question_groups",
                queryset=QuestionGroup.objects.order_by("order").prefetch_related(
                    Prefetch("questions",
                        queryset=Question.objects.order_by("order")
                    )
                )
            )
        )
    )
)
```

**Result:** Retrieving a MockTest with 3 sections, 10 groups, 50 questions executes
1 query for MockTest + 1 for sections + 1 for groups + 1 for questions = **4 queries total**
(not 1 + 3 + 10 + 50 = 64 queries without optimization).

**created_by Batch Fetch (user_map):**

**NOTE:** Currently NOT implemented in list() views. Future enhancement would follow
the Materials app pattern: collect all created_by_id values, execute one public
schema query `User.objects.filter(id__in=user_ids)`, pass as context to serializer.

================================================================================
MEDIA FILES & STORAGE
================================================================================

**Upload Fields (Multipart/Form-Data):**
- QuestionGroup: `audio_file`, `image`
- Question: `audio_file`, `image`
- QuizQuestion: `image`

**Request Format:** Send as multipart/form-data with file upload (not JSON).

**Response Format:** Returns full S3/CloudFront URL:
```json
{
  "audio_file": "https://s3.amazonaws.com/tenants/123/mock_tests/listening_audios/track1.mp3",
  "image": "https://cdn.example.com/tenants/123/mock_tests/question_images/diagram.png"
}
```

**Tenant Isolation:** Files stored at `tenants/{center_id}/mock_tests/{subpath}/`
preventing cross-center access (same pattern as Materials app).

**Cleanup:** post_delete signals remove physical files from S3 when records are deleted.
"""
from drf_spectacular.utils import (
    OpenApiExample,
    OpenApiParameter,
    OpenApiResponse,
    extend_schema,
    extend_schema_view,
)

from .serializers import (
    MockTestSerializer,
    TestSectionSerializer,
    QuestionGroupSerializer,
    QuestionSerializer,
    QuizSerializer,
    QuizQuestionSerializer,
)
from .services import PUBLISHED_TEST_EDIT_MESSAGE

# -----------------------------------------------------------------------------
# Reusable responses
# -----------------------------------------------------------------------------

RESP_400_PUBLISHED = OpenApiResponse(
    description="Cannot modify a published test. Change status to DRAFT first.",
    examples=[
        OpenApiExample(
            "Edit published test",
            value={"detail": PUBLISHED_TEST_EDIT_MESSAGE},
            response_only=True,
        ),
    ],
)
RESP_400_VALIDATION = OpenApiResponse(
    description="Validation error (e.g. options must have exactly one correct answer).",
)
RESP_401 = OpenApiResponse(description="Unauthorized: authentication required.")
RESP_403 = OpenApiResponse(
    description="Permission denied: not CENTER_ADMIN/TEACHER for write, or not owner for update/delete.",
)
RESP_404 = OpenApiResponse(description="Resource not found.")

# -----------------------------------------------------------------------------
# Option format for Question / QuizQuestion (used in examples)
# -----------------------------------------------------------------------------

QUESTION_OPTIONS_EXAMPLE = [
    {"text": "いきます", "is_correct": False},
    {"text": "いきました", "is_correct": True},
    {"text": "いって", "is_correct": False},
    {"text": "いきません", "is_correct": False},
]

QUIZ_QUESTION_OPTIONS_EXAMPLE = [
    {"text": "True", "is_correct": False},
    {"text": "False", "is_correct": True},
]


# =============================================================================
# Mock Tests
# =============================================================================

MOCK_TEST_LIST_DESC = """
List mock tests. **Role-based visibility (get_queryset):**
- **CENTER_ADMIN** & **TEACHER:** See **all** tests (Draft + Published).
- **STUDENT** & **GUEST:** See **only** PUBLISHED tests.

**Filters:** `level` (N5–N1), `status` (DRAFT | PUBLISHED). **Search:** title, description. **Ordering:** created_at, title.

**Note:** `created_by` field is fetched per-record from public schema (not optimized 
with user_map batch fetch). For large lists, this may result in multiple schema 
switches. Future optimization planned.
"""

MOCK_TEST_RETRIEVE_DESC = """
Retrieve a single mock test with **complete nested hierarchy** (sections → groups → questions).

**Performance Optimization:** Uses 4-level `prefetch_related` to load the entire exam 
structure in **4 database queries** (1 for MockTest, 1 for sections, 1 for groups, 
1 for questions) instead of N+1 queries. For a test with 3 sections, 10 groups, 
50 questions: 4 queries (not 64).

**Answer Protection:** If user is STUDENT/GUEST, all Question objects have 
`correct_option_index` removed and `is_correct` stripped from options (see module 
docstring for examples).

Same role-based visibility as list: STUDENT/GUEST only see PUBLISHED tests.
"""
MOCK_TEST_CREATE_DESC = "Create a mock test. **CENTER_ADMIN** or **TEACHER** only. Students and guests receive **403**."
MOCK_TEST_UPDATE_DESC = f"""
Update a mock test. **CENTER_ADMIN** (any) or **TEACHER** (only own). If the test
status is **PUBLISHED**, returns **400** with \"{PUBLISHED_TEST_EDIT_MESSAGE}\"
"""
MOCK_TEST_DESTROY_DESC = f"""
Delete a mock test. **CENTER_ADMIN** (any) or **TEACHER** (only own). If the test
is **PUBLISHED**, returns **400** with \"{PUBLISHED_TEST_EDIT_MESSAGE}\"

**⚠️ IRREVERSIBLE CASCADE DELETION:**

1. **Soft-delete cascade:** MockTest and ALL children (sections, groups, questions) 
   marked as deleted (deleted_at timestamp) via `soft_delete_mock_test_tree()`
2. **Physical file deletion:** All `audio_file` and `image` fields on QuestionGroups 
   and Questions trigger post_delete signals → **permanent S3 removal**
3. **No recovery:** Files are gone from storage; database records are soft-deleted 
   but media is irreversible

**Impact:** Deleting a test with 50 questions removes up to 50+ media files from S3.

**Best Practice:** For production, consider implementing a "deactivate" status instead 
of hard delete, or require two-step confirmation (change to DRAFT first, then delete).
"""
MOCK_TEST_PUBLISH_DESC = """
Toggle MockTest status between DRAFT and PUBLISHED. **CENTER_ADMIN** can publish/unpublish any test; **TEACHER** only tests they created (`created_by_id` = user id). Students and guests receive **403**.
"""
MOCK_TEST_CLONE_DESC = """
Clone a mock test (**deep copy** of entire hierarchy). Creates a complete copy of:
- MockTest (title + " (Copy)", status → DRAFT, created_by_id → current user)
- All TestSections (names, types, durations, scores preserved)
- All QuestionGroups (mondai numbers, instructions, reading_text, order preserved)
- All Questions (text, options, scores, order preserved)

**Media Files:** `audio_file` and `image` references are copied (point to same S3 files).
Physical files are NOT duplicated in storage.

**Use Cases:**
- Teacher wants to create a new exam based on existing structure
- Center admin needs to modify a PUBLISHED test (clone → edit clone → publish clone)

**Permissions:** CENTER_ADMIN or TEACHER only. Cloned test belongs to the requesting user.

**Response:** Returns the newly created MockTest with status=DRAFT, full nested hierarchy.
"""

mock_test_viewset_schema = extend_schema_view(
    list=extend_schema(
        tags=["Mock Tests"],
        summary="List mock tests",
        description=MOCK_TEST_LIST_DESC,
        parameters=[
            OpenApiParameter(name="search", type=str, description="Search title, description"),
            OpenApiParameter(name="level", type=str, enum=["N5", "N4", "N3", "N2", "N1"]),
            OpenApiParameter(name="status", type=str, enum=["DRAFT", "PUBLISHED"]),
            OpenApiParameter(name="ordering", type=str, description="e.g. -created_at, title"),
        ],
        responses={200: MockTestSerializer(many=True), 401: RESP_401, 403: RESP_403},
    ),
    retrieve=extend_schema(
        tags=["Mock Tests"],
        summary="Get mock test",
        description=MOCK_TEST_RETRIEVE_DESC,
        responses={200: MockTestSerializer, 401: RESP_401, 403: RESP_403, 404: RESP_404},
        examples=[
            OpenApiExample(
                "Full exam hierarchy (Teacher/Admin view with answers)",
                value={
                    "id": "550e8400-e29b-41d4-a716-446655440000",
                    "title": "JLPT N5 Mock Exam 2025",
                    "level": "N5",
                    "description": "Full practice test covering all sections.",
                    "status": "PUBLISHED",
                    "created_by_id": 42,
                    "created_by": {
                        "id": 42,
                        "email": "teacher@example.com",
                        "full_name": "John Smith",
                        "role": "TEACHER"
                    },
                    "pass_score": 90,
                    "total_score": 180,
                    "sections": [
                        {
                            "id": "660e8400-e29b-41d4-a716-446655440001",
                            "name": "Vocabulary (Moji-Goi)",
                            "section_type": "VOCAB",
                            "duration": 20,
                            "order": 1,
                            "total_score": 60,
                            "question_groups": [
                                {
                                    "id": "770e8400-e29b-41d4-a716-446655440002",
                                    "mondai_number": 1,
                                    "title": "Kanji Reading",
                                    "instruction": "Choose the correct reading for the underlined kanji.",
                                    "reading_text": "彼は毎日学校へ行きます。",
                                    "audio_file": None,
                                    "image": None,
                                    "order": 1,
                                    "questions": [
                                        {
                                            "id": "880e8400-e29b-41d4-a716-446655440003",
                                            "text": "正しい読み方を選びなさい。",
                                            "question_number": 1,
                                            "image": None,
                                            "audio_file": None,
                                            "score": 1,
                                            "order": 1,
                                            "correct_option_index": 1,
                                            "options": [
                                                {"text": "いきます", "is_correct": False},
                                                {"text": "いきました", "is_correct": True},
                                                {"text": "いって", "is_correct": False},
                                                {"text": "いきません", "is_correct": False}
                                            ],
                                            "created_at": "2026-02-01T10:00:00Z",
                                            "updated_at": "2026-02-01T10:00:00Z"
                                        }
                                    ],
                                    "created_at": "2026-02-01T09:55:00Z",
                                    "updated_at": "2026-02-01T09:55:00Z"
                                }
                            ],
                            "created_at": "2026-02-01T09:50:00Z",
                            "updated_at": "2026-02-01T09:50:00Z"
                        },
                        {
                            "id": "990e8400-e29b-41d4-a716-446655440004",
                            "name": "Listening (Choukai)",
                            "section_type": "LISTENING",
                            "duration": 30,
                            "order": 2,
                            "total_score": 60,
                            "question_groups": [
                                {
                                    "id": "aa0e8400-e29b-41d4-a716-446655440005",
                                    "mondai_number": 1,
                                    "title": "Task-based Listening",
                                    "instruction": "Listen to the audio and choose the correct answer.",
                                    "reading_text": None,
                                    "audio_file": "https://s3.amazonaws.com/tenants/123/mock_tests/listening_audios/n5_track1.mp3",
                                    "image": None,
                                    "order": 1,
                                    "questions": [
                                        {
                                            "id": "bb0e8400-e29b-41d4-a716-446655440006",
                                            "text": "Where will they meet?",
                                            "question_number": 1,
                                            "image": None,
                                            "audio_file": None,
                                            "score": 2,
                                            "order": 1,
                                            "correct_option_index": 2,
                                            "options": [
                                                {"text": "Station", "is_correct": False},
                                                {"text": "School", "is_correct": False},
                                                {"text": "Park", "is_correct": True},
                                                {"text": "Library", "is_correct": False}
                                            ],
                                            "created_at": "2026-02-01T10:10:00Z",
                                            "updated_at": "2026-02-01T10:10:00Z"
                                        }
                                    ],
                                    "created_at": "2026-02-01T10:05:00Z",
                                    "updated_at": "2026-02-01T10:05:00Z"
                                }
                            ],
                            "created_at": "2026-02-01T10:00:00Z",
                            "updated_at": "2026-02-01T10:00:00Z"
                        }
                    ],
                    "created_at": "2026-02-01T09:45:00Z",
                    "updated_at": "2026-02-01T09:45:00Z"
                },
                response_only=True,
                description="Complete 4-level nested structure. For STUDENT/GUEST, correct_option_index and is_correct are stripped (see Student view example)."
            ),
            OpenApiExample(
                "Student view (answers hidden)",
                value={
                    "id": "550e8400-e29b-41d4-a716-446655440000",
                    "title": "JLPT N5 Mock Exam 2025",
                    "level": "N5",
                    "status": "PUBLISHED",
                    "sections": [
                        {
                            "id": "660e8400-e29b-41d4-a716-446655440001",
                            "name": "Vocabulary (Moji-Goi)",
                            "question_groups": [
                                {
                                    "id": "770e8400-e29b-41d4-a716-446655440002",
                                    "mondai_number": 1,
                                    "title": "Kanji Reading",
                                    "questions": [
                                        {
                                            "id": "880e8400-e29b-41d4-a716-446655440003",
                                            "text": "正しい読み方を選びなさい。",
                                            "options": [
                                                {"text": "いきます"},
                                                {"text": "いきました"},
                                                {"text": "いって"},
                                                {"text": "いきません"}
                                            ]
                                        }
                                    ]
                                }
                            ]
                        }
                    ]
                },
                response_only=True,
                description="Same test for STUDENT/GUEST: correct_option_index removed, is_correct stripped from all options. Students cannot see correct answers."
            ),
        ],
    ),
    create=extend_schema(
        tags=["Mock Tests"],
        summary="Create mock test",
        description=MOCK_TEST_CREATE_DESC,
        request=MockTestSerializer,
        responses={201: MockTestSerializer, 400: RESP_400_VALIDATION, 401: RESP_401, 403: RESP_403},
        examples=[
            OpenApiExample(
                "Create mock test",
                value={
                    "title": "JLPT N5 Mock Exam 2025",
                    "level": "N5",
                    "description": "Full practice test.",
                    "status": "DRAFT",
                    "pass_score": 90,
                    "total_score": 180,
                },
                request_only=True,
            ),
        ],
    ),
    update=extend_schema(
        tags=["Mock Tests"],
        summary="Full update mock test",
        description=MOCK_TEST_UPDATE_DESC,
        request=MockTestSerializer,
        responses={200: MockTestSerializer, 400: RESP_400_PUBLISHED, 401: RESP_401, 403: RESP_403, 404: RESP_404},
        examples=[
            OpenApiExample(
                "Full update mock test",
                value={
                    "title": "JLPT N5 Mock Exam 2025 (Revised)",
                    "level": "N5",
                    "description": "Full practice test with updated content.",
                    "status": "DRAFT",
                    "pass_score": 95,
                    "total_score": 180,
                },
                request_only=True,
            ),
        ],
    ),
    partial_update=extend_schema(
        tags=["Mock Tests"],
        summary="Partial update mock test",
        description=MOCK_TEST_UPDATE_DESC,
        request=MockTestSerializer,
        responses={200: MockTestSerializer, 400: RESP_400_PUBLISHED, 401: RESP_401, 403: RESP_403, 404: RESP_404},
        examples=[
            OpenApiExample(
                "Partial update mock test",
                value={
                    "title": "JLPT N5 Mock Exam 2025 (Revised)",
                    "level": "N5",
                    "description": "Full practice test with updated content.",
                    "status": "DRAFT",
                    "pass_score": 95,
                    "total_score": 180,
                },
                request_only=True,
            ),
        ],
    ),
    destroy=extend_schema(
        tags=["Mock Tests"],
        summary="Delete mock test",
        description=MOCK_TEST_DESTROY_DESC,
        responses={
            204: OpenApiResponse(description="Mock test and all children deleted; media files removed from storage."),
            400: RESP_400_PUBLISHED,
            401: RESP_401,
            403: RESP_403,
            404: RESP_404,
        },
    ),
    publish=extend_schema(
        tags=["Mock Tests"],
        summary="Publish / Unpublish",
        description=MOCK_TEST_PUBLISH_DESC,
        responses={
            200: OpenApiResponse(
                description="Status toggled; returns detail and mock test data.",
                examples=[
                    OpenApiExample(
                        "Success",
                        value={"detail": "MockTest published successfully.", "data": {}},
                        response_only=True,
                    ),
                ],
            ),
            401: RESP_401,
            403: OpenApiResponse(
                description="Only CENTER_ADMIN or creator TEACHER can publish/unpublish.",
                examples=[
                    OpenApiExample(
                        "Not owner",
                        value={"detail": "Only the creator or center admin can publish/unpublish this test."},
                        response_only=True,
                    ),
                ],
            ),
            404: RESP_404,
        },
    ),
    clone=extend_schema(
        tags=["Mock Tests"],
        summary="Clone mock test",
        description=MOCK_TEST_CLONE_DESC,
        responses={
            201: MockTestSerializer,
            401: RESP_401,
            403: OpenApiResponse(
                description="Only CENTER_ADMIN or TEACHER can clone tests.",
                examples=[
                    OpenApiExample(
                        "Student attempting clone",
                        value={"detail": "Only center admins or teachers can clone tests."},
                        response_only=True,
                    ),
                ],
            ),
            404: RESP_404,
        },
        examples=[
            OpenApiExample(
                "Clone request (POST with empty body)",
                value={},
                request_only=True,
                description="POST to /mock-tests/{id}/clone/ with no request body. All cloning logic is automatic."
            ),
            OpenApiExample(
                "Cloned test response",
                value={
                    "id": "cc0e8400-e29b-41d4-a716-446655440007",
                    "title": "JLPT N5 Mock Exam 2025 (Copy)",
                    "level": "N5",
                    "description": "Full practice test covering all sections.",
                    "status": "DRAFT",
                    "created_by_id": 15,
                    "created_by": {
                        "id": 15,
                        "email": "newteacher@example.com",
                        "full_name": "Jane Doe",
                        "role": "TEACHER"
                    },
                    "pass_score": 90,
                    "total_score": 180,
                    "sections": [
                        {"id": "dd0e8400-...", "name": "Vocabulary (Moji-Goi)", "question_groups": [...]}
                    ],
                    "created_at": "2026-02-10T14:30:00Z",
                    "updated_at": "2026-02-10T14:30:00Z"
                },
                response_only=True,
                description="New test with: title + ' (Copy)', status=DRAFT, created_by_id=current_user, new IDs for all objects. Source test remains unchanged."
            ),
        ],
    ),
)


# =============================================================================
# Test Sections
# =============================================================================

SECTION_LIST_DESC = """
List test sections. **Visibility:** CENTER_ADMIN & TEACHER see all sections;
STUDENT & GUEST see only sections belonging to **PUBLISHED** MockTests.

**Filter:** `mock_test` (UUID). **Ordering:** order.
"""
SECTION_CREATE_DESC = f"Create section. Returns **400** with \"{PUBLISHED_TEST_EDIT_MESSAGE}\" if parent MockTest is PUBLISHED."
SECTION_UPDATE_DESC = f"Update section. Returns **400** if parent MockTest is PUBLISHED."
SECTION_DESTROY_DESC = f"Delete section. Returns **400** if parent MockTest is PUBLISHED."

test_section_viewset_schema = extend_schema_view(
    list=extend_schema(
        tags=["Test Sections"],
        summary="List sections",
        description=SECTION_LIST_DESC,
        parameters=[
            OpenApiParameter(name="mock_test", type=str, description="Filter by mock test ID"),
            OpenApiParameter(name="ordering", type=str),
        ],
        responses={200: TestSectionSerializer(many=True), 401: RESP_401, 403: RESP_403},
    ),
    retrieve=extend_schema(
        tags=["Test Sections"],
        summary="Get section",
        responses={200: TestSectionSerializer, 401: RESP_401, 403: RESP_403, 404: RESP_404},
    ),
    create=extend_schema(
        tags=["Test Sections"],
        summary="Create section",
        description=SECTION_CREATE_DESC,
        request=TestSectionSerializer,
        responses={201: TestSectionSerializer, 400: RESP_400_PUBLISHED, 401: RESP_401, 403: RESP_403},
        examples=[
            OpenApiExample(
                "Create section",
                value={
                    "mock_test": "550e8400-e29b-41d4-a716-446655440000",
                    "name": "Vocabulary (Moji-Goi)",
                    "section_type": "VOCAB",
                    "duration": 20,
                    "order": 1,
                    "total_score": 60,
                },
                request_only=True,
            ),
        ],
    ),
    update=extend_schema(
        tags=["Test Sections"],
        summary="Full update section",
        description=SECTION_UPDATE_DESC,
        request=TestSectionSerializer,
        responses={200: TestSectionSerializer, 400: RESP_400_PUBLISHED, 401: RESP_401, 403: RESP_403, 404: RESP_404},
        examples=[
            OpenApiExample(
                "Full update section",
                value={
                    "mock_test": "550e8400-e29b-41d4-a716-446655440000",
                    "name": "Vocabulary (Moji-Goi) - Updated",
                    "section_type": "VOCAB",
                    "duration": 25,
                    "order": 1,
                    "total_score": 60,
                },
                request_only=True,
            ),
        ],
    ),
    partial_update=extend_schema(
        tags=["Test Sections"],
        summary="Partial update section",
        description=SECTION_UPDATE_DESC,
        request=TestSectionSerializer,
        responses={200: TestSectionSerializer, 400: RESP_400_PUBLISHED, 401: RESP_401, 403: RESP_403, 404: RESP_404},
        examples=[
            OpenApiExample(
                "Partial update section",
                value={
                    "mock_test": "550e8400-e29b-41d4-a716-446655440000",
                    "name": "Vocabulary (Moji-Goi) - Updated",
                    "section_type": "VOCAB",
                    "duration": 25,
                    "order": 1,
                    "total_score": 60,
                },
                request_only=True,
            ),
        ],
    ),
    destroy=extend_schema(
        tags=["Test Sections"],
        summary="Delete section",
        description=SECTION_DESTROY_DESC,
        responses={204: OpenApiResponse(description="Deleted."), 400: RESP_400_PUBLISHED, 401: RESP_401, 403: RESP_403, 404: RESP_404},
    ),
)


# =============================================================================
# Question Groups (Mondai)
# =============================================================================

MONDAI_LIST_DESC = """
List question groups (Mondai). **Visibility:** CENTER_ADMIN & TEACHER see all;
STUDENT & GUEST see only groups belonging to **PUBLISHED** MockTests.

**Filters:** `section`, `mock_test`. **Ordering:** section, order.
"""
MONDAI_CREATE_DESC = f"Create Mondai. Returns **400** if parent MockTest is PUBLISHED."
MONDAI_UPDATE_DESC = f"Update Mondai. Returns **400** if parent MockTest is PUBLISHED."
MONDAI_DESTROY_DESC = f"Delete Mondai. Returns **400** if parent MockTest is PUBLISHED."

question_group_viewset_schema = extend_schema_view(
    list=extend_schema(
        tags=["Question Groups (Mondai)"],
        summary="List question groups",
        description=MONDAI_LIST_DESC,
        parameters=[
            OpenApiParameter(name="section", type=str, ),
            OpenApiParameter(name="mock_test", type=str, ),
            OpenApiParameter(name="ordering", type=str),
        ],
        responses={200: QuestionGroupSerializer(many=True), 401: RESP_401, 403: RESP_403},
    ),
    retrieve=extend_schema(
        tags=["Question Groups (Mondai)"],
        summary="Get question group",
        responses={200: QuestionGroupSerializer, 401: RESP_401, 403: RESP_403, 404: RESP_404},
    ),
    create=extend_schema(
        tags=["Question Groups (Mondai)"],
        summary="Create Mondai",
        description=MONDAI_CREATE_DESC,
        request=QuestionGroupSerializer,
        responses={201: QuestionGroupSerializer, 400: RESP_400_PUBLISHED, 401: RESP_401, 403: RESP_403},
        examples=[
            OpenApiExample(
                "Create Mondai",
                value={
                    "section": "660e8400-e29b-41d4-a716-446655440001",
                    "mondai_number": 1,
                    "title": "Kanji Reading",
                    "instruction": "Choose the correct reading for the underlined kanji.",
                    "reading_text": "彼は毎日学校へ行きます。",
                    "audio_file": None,
                    "image": None,
                    "order": 1,
                },
                request_only=True,
            ),
        ],
    ),
    update=extend_schema(
        tags=["Question Groups (Mondai)"],
        summary="Full update Mondai",
        description=MONDAI_UPDATE_DESC,
        request=QuestionGroupSerializer,
        responses={200: QuestionGroupSerializer, 400: RESP_400_PUBLISHED, 401: RESP_401, 403: RESP_403, 404: RESP_404},
        examples=[
            OpenApiExample(
                "Full update Mondai",
                value={
                    "section": "660e8400-e29b-41d4-a716-446655440001",
                    "mondai_number": 1,
                    "title": "Kanji Reading - Updated",
                    "instruction": "Choose the correct reading for the underlined kanji.",
                    "reading_text": "彼は毎日学校へ行きます。",
                    "audio_file": None,
                    "image": None,
                    "order": 1,
                },
                request_only=True,
            ),
        ],
    ),
    partial_update=extend_schema(
        tags=["Question Groups (Mondai)"],
        summary="Partial update Mondai",
        description=MONDAI_UPDATE_DESC,
        request=QuestionGroupSerializer,
        responses={200: QuestionGroupSerializer, 400: RESP_400_PUBLISHED, 401: RESP_401, 403: RESP_403, 404: RESP_404},
        examples=[
            OpenApiExample(
                "Partial update Mondai",
                value={
                    "section": "660e8400-e29b-41d4-a716-446655440001",
                    "mondai_number": 1,
                    "title": "Kanji Reading - Updated",
                    "instruction": "Choose the correct reading for the underlined kanji.",
                    "reading_text": "彼は毎日学校へ行きます。",
                    "audio_file": None,
                    "image": None,
                    "order": 1,
                },
                request_only=True,
            ),
        ],
    ),
    destroy=extend_schema(
        tags=["Question Groups (Mondai)"],
        summary="Delete Mondai",
        description=MONDAI_DESTROY_DESC,
        responses={204: OpenApiResponse(description="Deleted."), 400: RESP_400_PUBLISHED, 401: RESP_401, 403: RESP_403, 404: RESP_404},
    ),
)


# =============================================================================
# Questions (with options JSON)
# =============================================================================

QUESTION_LIST_DESC = """
List questions. **Visibility:** CENTER_ADMIN & TEACHER see all; STUDENT & GUEST
see only questions belonging to **PUBLISHED** MockTests.

**Filters:** `group`, `section`, `mock_test`. **Ordering:** group, order.
"""

QUESTION_OPTIONS_DOC = """
**Options format:** Send `options` as a list of objects: `[{\"text\": \"...\", \"is_correct\": true|false}, ...]`.
Exactly **one** option must have `is_correct: true`. The backend validates this and returns **400** if not.

**correct_option_index:** Do **not** send this field. It is **automatically calculated** from the option with `is_correct: true` (0-based index) and is read-only in responses.
"""

QUESTION_CREATE_DESC = f"""
Create a question within a QuestionGroup. Returns **400** if parent MockTest is PUBLISHED or if options do not have exactly one correct answer.

{QUESTION_OPTIONS_DOC}
"""
QUESTION_UPDATE_DESC = f"Update question. Returns **400** if parent MockTest is PUBLISHED. {QUESTION_OPTIONS_DOC}"

question_viewset_schema = extend_schema_view(
    list=extend_schema(
        tags=["Questions"],
        summary="List questions",
        description=QUESTION_LIST_DESC,
        parameters=[
            OpenApiParameter(name="group", type=str, ),
            OpenApiParameter(name="section", type=str, ),
            OpenApiParameter(name="mock_test", type=str, ),
            OpenApiParameter(name="ordering", type=str),
        ],
        responses={200: QuestionSerializer(many=True), 401: RESP_401, 403: RESP_403},
    ),
    retrieve=extend_schema(
        tags=["Questions"],
        summary="Get question",
        responses={200: QuestionSerializer, 401: RESP_401, 403: RESP_403, 404: RESP_404},
        examples=[
            OpenApiExample(
                "Teacher/Admin view (with correct answer)",
                value={
                    "id": "880e8400-e29b-41d4-a716-446655440003",
                    "group": "770e8400-e29b-41d4-a716-446655440002",
                    "text": "彼は毎日学校へ___。",
                    "question_number": 1,
                    "image": None,
                    "audio_file": None,
                    "score": 1,
                    "order": 1,
                    "correct_option_index": 1,
                    "options": [
                        {"text": "いきます", "is_correct": False},
                        {"text": "いきました", "is_correct": True},
                        {"text": "いって", "is_correct": False},
                        {"text": "いきません", "is_correct": False}
                    ],
                    "created_at": "2026-02-01T10:00:00Z",
                    "updated_at": "2026-02-01T10:00:00Z"
                },
                response_only=True,
                description="Full response with correct_option_index and is_correct flags for CENTER_ADMIN/TEACHER."
            ),
            OpenApiExample(
                "Student/Guest view (answers hidden)",
                value={
                    "id": "880e8400-e29b-41d4-a716-446655440003",
                    "group": "770e8400-e29b-41d4-a716-446655440002",
                    "text": "彼は毎日学校へ___。",
                    "question_number": 1,
                    "image": None,
                    "audio_file": None,
                    "score": 1,
                    "order": 1,
                    "options": [
                        {"text": "いきます"},
                        {"text": "いきました"},
                        {"text": "いって"},
                        {"text": "いきません"}
                    ],
                    "created_at": "2026-02-01T10:00:00Z",
                    "updated_at": "2026-02-01T10:00:00Z"
                },
                response_only=True,
                description="Same question for STUDENT/GUEST: correct_option_index removed, is_correct stripped from all options. Answer protection prevents cheating."
            ),
        ],
    ),
    create=extend_schema(
        tags=["Questions"],
        summary="Create question",
        description=QUESTION_CREATE_DESC,
        request=QuestionSerializer,
        responses={
            201: QuestionSerializer,
            400: OpenApiResponse(
                description="Cannot modify published test, or options validation failed (not a list, missing fields, wrong correct count).",
                examples=[
                    OpenApiExample(
                        "Published test",
                        value={"detail": PUBLISHED_TEST_EDIT_MESSAGE},
                        response_only=True,
                    ),
                    OpenApiExample(
                        "Options not a list",
                        value={"options": "Options must be a list."},
                        response_only=True,
                        description="Sent options as object instead of array."
                    ),
                    OpenApiExample(
                        "Missing text field",
                        value={"options": "Option at index 0 must have a 'text' field."},
                        response_only=True,
                        description="Option object missing 'text' key."
                    ),
                    OpenApiExample(
                        "Missing is_correct field",
                        value={"options": "Option at index 1 must have an 'is_correct' field."},
                        response_only=True,
                    ),
                    OpenApiExample(
                        "is_correct not boolean",
                        value={"options": "Option at index 2 'is_correct' must be a boolean."},
                        response_only=True,
                        description="Sent is_correct as string 'true' instead of boolean true."
                    ),
                    OpenApiExample(
                        "No correct option",
                        value={"options": "There must be exactly one correct option. Found 0."},
                        response_only=True,
                        description="All options have is_correct: false."
                    ),
                    OpenApiExample(
                        "Multiple correct options",
                        value={"options": "There must be exactly one correct option. Found 2."},
                        response_only=True,
                        description="Two or more options have is_correct: true."
                    ),
                    OpenApiExample(
                        "Empty options array",
                        value={"options": "At least one option is required."},
                        response_only=True,
                    ),
                ],
            ),
            401: RESP_401,
            403: RESP_403,
        },
        examples=[
            OpenApiExample(
                "Create question with options (Mondai-style)",
                value={
                    "group": "770e8400-e29b-41d4-a716-446655440002",
                    "text": "正しい読み方を選びなさい。",
                    "question_number": 1,
                    "image": None,
                    "audio_file": None,
                    "score": 1,
                    "order": 1,
                    "options": QUESTION_OPTIONS_EXAMPLE,
                },
                request_only=True,
                description="options: list of { text, is_correct }; exactly one is_correct: true. correct_option_index is auto-calculated.",
            ),
        ],
    ),
    update=extend_schema(
        tags=["Questions"],
        summary="Full update question",
        description=QUESTION_UPDATE_DESC,
        request=QuestionSerializer,
        responses={200: QuestionSerializer, 400: RESP_400_PUBLISHED, 401: RESP_401, 403: RESP_403, 404: RESP_404},
        examples=[
            OpenApiExample(
                "Full update question",
                value={
                    "group": "770e8400-e29b-41d4-a716-446655440002",
                    "text": "正しい読み方を選びなさい。（更新）",
                    "question_number": 1,
                    "image": None,
                    "audio_file": None,
                    "score": 1,
                    "order": 1,
                    "options": QUESTION_OPTIONS_EXAMPLE,
                },
                request_only=True,
            ),
        ],
    ),
    partial_update=extend_schema(
        tags=["Questions"],
        summary="Partial update question",
        description=QUESTION_UPDATE_DESC,
        request=QuestionSerializer,
        responses={200: QuestionSerializer, 400: RESP_400_PUBLISHED, 401: RESP_401, 403: RESP_403, 404: RESP_404},
        examples=[
            OpenApiExample(
                "Partial update question",
                value={
                    "group": "770e8400-e29b-41d4-a716-446655440002",
                    "text": "正しい読み方を選びなさい。（更新）",
                    "question_number": 1,
                    "image": None,
                    "audio_file": None,
                    "score": 1,
                    "order": 1,
                    "options": QUESTION_OPTIONS_EXAMPLE,
                },
                request_only=True,
            ),
        ],
    ),
    destroy=extend_schema(
        tags=["Questions"],
        summary="Delete question",
        description=f"Returns **400** if parent MockTest is PUBLISHED. On success, associated media (image, audio_file) are removed from storage.",
        responses={204: OpenApiResponse(description="Deleted."), 400: RESP_400_PUBLISHED, 401: RESP_401, 403: RESP_403, 404: RESP_404},
    ),
)


# =============================================================================
# Quizzes
# =============================================================================

QUIZ_LIST_DESC = """
List quizzes. **Visibility:** CENTER_ADMIN & TEACHER see all; STUDENT & GUEST see only **active** quizzes (`is_active=True`).

**Filters:** is_active. **Ordering:** created_at.

**Note:** `created_by` field is fetched per-record from public schema (not optimized 
with user_map batch fetch). For large lists, this may result in multiple schema switches.
"""
QUIZ_RETRIEVE_DESC = "Get quiz. Same visibility as list."
QUIZ_CREATE_DESC = "Create quiz. **CENTER_ADMIN** or **TEACHER** only."
QUIZ_UPDATE_DESC = "Update quiz. **CENTER_ADMIN** (any) or **TEACHER** (only own)."
QUIZ_DESTROY_DESC = "Delete quiz. **CENTER_ADMIN** (any) or **TEACHER** (only own)."

quiz_viewset_schema = extend_schema_view(
    list=extend_schema(
        tags=["Quizzes"],
        summary="List quizzes",
        description=QUIZ_LIST_DESC,
        parameters=[
            OpenApiParameter(name="search", type=str),
            OpenApiParameter(name="is_active", type=bool),
            OpenApiParameter(name="ordering", type=str),
        ],
        responses={200: QuizSerializer(many=True), 401: RESP_401, 403: RESP_403},
    ),
    retrieve=extend_schema(
        tags=["Quizzes"],
        summary="Get quiz",
        description=QUIZ_RETRIEVE_DESC,
        responses={200: QuizSerializer, 401: RESP_401, 403: RESP_403, 404: RESP_404},
    ),
    create=extend_schema(
        tags=["Quizzes"],
        summary="Create quiz",
        description=QUIZ_CREATE_DESC,
        request=QuizSerializer,
        responses={201: QuizSerializer, 400: RESP_400_VALIDATION, 401: RESP_401, 403: RESP_403},
        examples=[
            OpenApiExample(
                "Create quiz",
                value={
                    "title": "JLPT N5 Vocabulary Quiz",
                    "description": "Basic vocabulary practice.",
                    "is_active": True,
                    "default_question_duration": 60,
                },
                request_only=True,
            ),
        ],
    ),
    update=extend_schema(
        tags=["Quizzes"],
        summary="Full update quiz",
        request=QuizSerializer,
        responses={200: QuizSerializer, 400: RESP_400_VALIDATION, 401: RESP_401, 403: RESP_403, 404: RESP_404},
        examples=[
            OpenApiExample(
                "Full update quiz",
                value={
                    "title": "JLPT N5 Vocabulary Quiz (Updated)",
                    "description": "Basic vocabulary practice.",
                    "is_active": True,
                    "default_question_duration": 90,
                },
                request_only=True,
            ),
        ],
    ),
    partial_update=extend_schema(
        tags=["Quizzes"],
        summary="Partial update quiz",
        request=QuizSerializer,
        responses={200: QuizSerializer, 400: RESP_400_VALIDATION, 401: RESP_401, 403: RESP_403, 404: RESP_404},
        examples=[
            OpenApiExample(
                "Partial update quiz",
                value={
                    "title": "JLPT N5 Vocabulary Quiz (Updated)",
                    "description": "Basic vocabulary practice.",
                    "is_active": True,
                    "default_question_duration": 90,
                },
                request_only=True,
            ),
        ],
    ),
    destroy=extend_schema(
        tags=["Quizzes"],
        summary="Delete quiz",
        description=QUIZ_DESTROY_DESC,
        responses={204: OpenApiResponse(description="Deleted."), 401: RESP_401, 403: RESP_403, 404: RESP_404},
    ),
)


# =============================================================================
# Quiz Questions
# =============================================================================

QUIZ_QUESTION_LIST_DESC = """
List quiz questions. **Visibility:** CENTER_ADMIN & TEACHER see all; STUDENT & GUEST see only questions of **active** quizzes. **Filter:** `quiz`.
"""
QUIZ_QUESTION_OPTIONS_DOC = """
**Options format:** Same as Questions: `[{\"text\": \"...\", \"is_correct\": true|false}, ...]` with exactly one `is_correct: true`. **correct_option_index** is auto-calculated; do not send.
"""

quiz_question_viewset_schema = extend_schema_view(
    list=extend_schema(
        tags=["Quiz Questions"],
        summary="List quiz questions",
        description=QUIZ_QUESTION_LIST_DESC,
        parameters=[
            OpenApiParameter(name="quiz", type=str, ),
            OpenApiParameter(name="ordering", type=str),
        ],
        responses={200: QuizQuestionSerializer(many=True), 401: RESP_401, 403: RESP_403},
    ),
    retrieve=extend_schema(
        tags=["Quiz Questions"],
        summary="Get quiz question",
        responses={200: QuizQuestionSerializer, 401: RESP_401, 403: RESP_403, 404: RESP_404},
    ),
    create=extend_schema(
        tags=["Quiz Questions"],
        summary="Create quiz question",
        description=f"CENTER_ADMIN or TEACHER. {QUIZ_QUESTION_OPTIONS_DOC}",
        request=QuizQuestionSerializer,
        responses={201: QuizQuestionSerializer, 400: RESP_400_VALIDATION, 401: RESP_401, 403: RESP_403},
        examples=[
            OpenApiExample(
                "Create quiz question with options",
                value={
                    "quiz": "880e8400-e29b-41d4-a716-446655440003",
                    "text": "Tokyo is the capital of Japan.",
                    "question_type": "QUIZ",
                    "image": None,
                    "duration": 20,
                    "points": 1,
                    "order": 1,
                    "options": QUIZ_QUESTION_OPTIONS_EXAMPLE,
                },
                request_only=True,
            ),
        ],
    ),
    update=extend_schema(
        tags=["Quiz Questions"],
        summary="Full update quiz question",
        request=QuizQuestionSerializer,
        responses={200: QuizQuestionSerializer, 400: RESP_400_VALIDATION, 401: RESP_401, 403: RESP_403, 404: RESP_404},
        examples=[
            OpenApiExample(
                "Full update quiz question",
                value={
                    "quiz": "880e8400-e29b-41d4-a716-446655440003",
                    "text": "Tokyo is the capital of Japan. (Updated)",
                    "question_type": "QUIZ",
                    "image": None,
                    "duration": 30,
                    "points": 2,
                    "order": 1,
                    "options": QUIZ_QUESTION_OPTIONS_EXAMPLE,
                },
                request_only=True,
            ),
        ],
    ),
    partial_update=extend_schema(
        tags=["Quiz Questions"],
        summary="Partial update quiz question",
        request=QuizQuestionSerializer,
        responses={200: QuizQuestionSerializer, 400: RESP_400_VALIDATION, 401: RESP_401, 403: RESP_403, 404: RESP_404},
        examples=[
            OpenApiExample(
                "Partial update quiz question",
                value={
                    "quiz": "880e8400-e29b-41d4-a716-446655440003",
                    "text": "Tokyo is the capital of Japan. (Updated)",
                    "question_type": "QUIZ",
                    "image": None,
                    "duration": 30,
                    "points": 2,
                    "order": 1,
                    "options": QUIZ_QUESTION_OPTIONS_EXAMPLE,
                },
                request_only=True,
            ),
        ],
    ),
    destroy=extend_schema(
        tags=["Quiz Questions"],
        summary="Delete quiz question",
        description="On success, associated image is removed from storage.",
        responses={204: OpenApiResponse(description="Deleted."), 401: RESP_401, 403: RESP_403, 404: RESP_404},
    ),
)
