# apps/mock_tests/services.py
from django.core.exceptions import ValidationError
from .models import MockTest, TestSection, QuestionGroup, Question


def validate_mock_test_editable(mock_test_instance):
    """
    Validate that a MockTest instance is editable.
    
    Raises ValidationError if the MockTest status is PUBLISHED.
    This function should be called before any create/update/delete operations
    on MockTest or its child objects (TestSection, QuestionGroup, Question).
    
    Args:
        mock_test_instance: MockTest instance to validate
        
    Raises:
        ValidationError: If the MockTest is PUBLISHED and cannot be edited
    """
    if not mock_test_instance:
        raise ValidationError("MockTest instance is required.")
    
    if mock_test_instance.status == MockTest.Status.PUBLISHED:
        raise ValidationError(
            "Cannot modify a published MockTest. Please change the status to DRAFT first."
        )


def get_parent_mock_test(obj):
    """
    Get the parent MockTest instance from any child object.
    
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


def validate_child_object_editable(obj):
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
