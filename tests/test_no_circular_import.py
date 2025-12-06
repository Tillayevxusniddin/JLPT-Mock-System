"""
Test to verify no circular import between authentication and organizations apps

This test ensures that:
1. UserDetailSerializer can import without circular dependency
2. OrganizationSerializer can import without circular dependency
3. Both can be used together without issues
"""
from django.test import TestCase
from apps.authentication.serializers import (
    UserDetailSerializer, 
    UserListSerializer,
    UserSerializer
)
from apps.organizations.serializers import (
    OrganizationSerializer,
    OrganizationListSerializer
)


class NoCircularImportTest(TestCase):
    """Test that serializers can be imported without circular dependency"""
    
    def test_authentication_serializers_import(self):
        """Test that authentication serializers import successfully"""
        self.assertIsNotNone(UserDetailSerializer)
        self.assertIsNotNone(UserListSerializer)
        self.assertIsNotNone(UserSerializer)
    
    def test_organization_serializers_import(self):
        """Test that organization serializers import successfully"""
        self.assertIsNotNone(OrganizationSerializer)
        self.assertIsNotNone(OrganizationListSerializer)
    
    def test_both_apps_serializers_together(self):
        """Test that both app serializers can coexist without circular import"""
        # If we can instantiate both, there's no circular import
        try:
            user_serializer_class = UserDetailSerializer
            org_serializer_class = OrganizationSerializer
            self.assertTrue(True, "Both serializers loaded successfully")
        except ImportError as e:
            self.fail(f"Circular import detected: {e}")


class UserDetailSerializerTest(TestCase):
    """Test UserDetailSerializer organization field"""
    
    def test_organization_field_is_serializer_method_field(self):
        """Verify organization field uses SerializerMethodField to avoid circular import"""
        from rest_framework import serializers
        
        # Check that organization field is SerializerMethodField
        organization_field = UserDetailSerializer().fields['organization']
        self.assertIsInstance(
            organization_field, 
            serializers.SerializerMethodField,
            "Organization field should be SerializerMethodField to avoid circular import"
        )
    
    def test_get_organization_method_exists(self):
        """Verify get_organization method exists"""
        serializer = UserDetailSerializer()
        self.assertTrue(
            hasattr(serializer, 'get_organization'),
            "UserDetailSerializer should have get_organization method"
        )
