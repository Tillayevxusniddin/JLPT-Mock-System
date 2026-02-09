"""
OpenAPI / Swagger documentation for the mock_tests app.

Enterprise-level API documentation for the 4-level hierarchy: **MockTest** →
**TestSection** → **QuestionGroup (Mondai)** → **Question**. Quizzes are separate:
**Quiz** → **QuizQuestion**.

**Strict immutability (Published protection):**
- Any **PUT**, **PATCH**, or **DELETE** on a MockTest with status **PUBLISHED**, or on
  any of its children (TestSection, QuestionGroup, Question), is blocked with
  **400 Bad Request** and message: *"Cannot modify a published test."*
- This ensures that if a student is taking an exam, the structure does not change mid-way.
- To modify a published test, change its status to DRAFT first (via the publish action).

**Role-based visibility (get_queryset):**
- **CENTER_ADMIN** & **TEACHER:** See all tests (Draft + Published) and all sections/groups/questions.
- **STUDENT** & **GUEST:** See **only** PUBLISHED MockTests and their sections/groups/questions.

**Performance:** MockTest and Quiz list endpoints batch-fetch `created_by` (Public User)
from the public schema via `user_map` (Zero N+1 schema switching).

**Media isolation:** `audio_file` and `image` fields use tenant-isolated upload paths
(same pattern as the materials app) to prevent cross-center media leaks.

**Answer protection:** For STUDENT & GUEST, responses **exclude** `correct_option_index`
and remove `is_correct` from options. Teachers/Admins receive full answer data.
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

**Performance:** The `created_by` field is populated via **batch-fetching** from
the **public schema** in a single query for all tests on the page (Zero N+1 schema switching).

**Filters:** `level` (N5–N1), `status` (DRAFT | PUBLISHED). **Search:** title, description. **Ordering:** created_at, title.
"""

MOCK_TEST_RETRIEVE_DESC = "Retrieve a mock test. Same visibility as list."
MOCK_TEST_CREATE_DESC = "Create a mock test. **CENTER_ADMIN** or **TEACHER** only. Students and guests receive **403**."
MOCK_TEST_UPDATE_DESC = f"""
Update a mock test. **CENTER_ADMIN** (any) or **TEACHER** (only own). If the test
status is **PUBLISHED**, returns **400** with \"{PUBLISHED_TEST_EDIT_MESSAGE}\"
"""
MOCK_TEST_DESTROY_DESC = f"""
Delete a mock test. **CENTER_ADMIN** (any) or **TEACHER** (only own). If the test
is **PUBLISHED**, returns **400** with \"{PUBLISHED_TEST_EDIT_MESSAGE}\"

**Cascade & cleanup:** Deleting a MockTest **cascades** to all its TestSections,
QuestionGroups, and Questions (DB). Associated **media files** (audio, images) on
QuestionGroups and Questions are **removed from S3/storage** via post_delete signals.
"""
MOCK_TEST_PUBLISH_DESC = """
Toggle MockTest status between DRAFT and PUBLISHED. **CENTER_ADMIN** can publish/unpublish any test; **TEACHER** only tests they created (`created_by_id` = user id). Students and guests receive **403**.
"""
MOCK_TEST_CLONE_DESC = """
Clone a mock test (deep copy). Creates a full copy of sections, question groups, and questions.
**Status is reset to DRAFT** and ownership is set to the requesting user.
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
            403: RESP_403,
            404: RESP_404,
        },
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
    ),
    create=extend_schema(
        tags=["Questions"],
        summary="Create question",
        description=QUESTION_CREATE_DESC,
        request=QuestionSerializer,
        responses={
            201: QuestionSerializer,
            400: OpenApiResponse(
                description="Cannot modify published test, or options must have exactly one correct answer.",
                examples=[
                    OpenApiExample("Published test", value={"detail": PUBLISHED_TEST_EDIT_MESSAGE}, response_only=True),
                    OpenApiExample("Options error", value={"options": "There must be exactly one correct option. Found 0."}, response_only=True),
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

**Performance:** `created_by` is batch-fetched from the public schema (user_map). **Filters:** is_active. **Ordering:** created_at.
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
