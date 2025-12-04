from rest_framework import serializers
from .models import Organization

class OrganizationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Organization
        fields = ('id', 'name', 'slug', 'schema_name', 'status', 'created_at')
        read_only_fields = ('id', 'slug', 'schema_name', 'created_at')