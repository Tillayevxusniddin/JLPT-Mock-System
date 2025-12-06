"""
Input sanitization utilities
"""
import re
from django.utils.html import strip_tags


def sanitize_text_input(value):
    """
    Sanitize text input by stripping HTML tags and extra whitespace
    """
    if not value:
        return value
    
    # Strip HTML tags
    value = strip_tags(str(value))
    
    # Remove extra whitespace
    value = ' '.join(value.split())
    
    return value.strip()


def sanitize_email(value):
    """
    Normalize email address to lowercase
    """
    if not value:
        return value
    
    return value.lower().strip()


def sanitize_phone(value):
    """
    Remove non-numeric characters from phone number
    """
    if not value:
        return value
    
    # Keep only digits and +
    return re.sub(r'[^\d+]', '', str(value))
