# apps/mock_tests/services.py
from typing import Optional, Union
from django.core.exceptions import ValidationError
from .models import MockTest, TestSection, QuestionGroup, Question

# Message returned as 400 when modifying a published test (used by views and serializers)
PUBLISHED_TEST_EDIT_MESSAGE = "Cannot modify a published test."


def validate_mock_test_editable(mock_test_instance: Optional[MockTest]) -> None:
    """
    Validate that a MockTest instance is editable.
    Raises ValidationError if the MockTest status is PUBLISHED.
    Call before any create/update/delete on MockTest or its children
    (TestSection, QuestionGroup, Question).
    
    Args:
        mock_test_instance: MockTest instance to validate
        
    Raises:
        ValidationError: If MockTest is None or status is PUBLISHED
    """
    if not mock_test_instance:
        raise ValidationError("MockTest instance is required.")
    if mock_test_instance.status == MockTest.Status.PUBLISHED:
        raise ValidationError(PUBLISHED_TEST_EDIT_MESSAGE)


def get_parent_mock_test(obj: Union[MockTest, TestSection, QuestionGroup, Question]) -> Optional[MockTest]:
    """
    Get the parent MockTest instance from any child object.
    Uses select_related optimization to avoid N+1 queries.
    
    Args:
        obj: Instance of MockTest, TestSection, QuestionGroup, or Question
        
    Returns:
        MockTest instance or None
    """
    if isinstance(obj, MockTest):
        return obj
    elif isinstance(obj, TestSection):
        return obj.mock_test
    elif isinstance(obj, QuestionGroup):
        # Use select_related to avoid N+1 queries
        if not hasattr(obj, '_mock_test_cache'):
            obj._mock_test_cache = obj.section.mock_test
        return obj._mock_test_cache
    elif isinstance(obj, Question):
        # Use select_related to avoid N+1 queries
        if not hasattr(obj, '_mock_test_cache'):
            obj._mock_test_cache = obj.group.section.mock_test
        return obj._mock_test_cache
    return None


def validate_child_object_editable(obj: Union[TestSection, QuestionGroup, Question]) -> None:
    """
    Validate that a child object (TestSection, QuestionGroup, Question) is editable
    by checking its parent MockTest status.
    
    Args:
        obj: Instance of TestSection, QuestionGroup, or Question
        
    Raises:
        ValidationError: If the parent MockTest is PUBLISHED
    """
    mock_test = get_parent_mock_test(obj)
    if mock_test:
        validate_mock_test_editable(mock_test)
