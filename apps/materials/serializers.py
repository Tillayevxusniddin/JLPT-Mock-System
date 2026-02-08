# apps/materials/serializers.py
import os
import mimetypes
import logging
from rest_framework import serializers
from .models import Material
from apps.core.serializers import UserSummarySerializer
from apps.groups.models import Group

logger = logging.getLogger(__name__)

# Try to import python-magic for robust MIME detection from file content
try:
    import magic
    HAS_MAGIC = True
except ImportError:
    HAS_MAGIC = False

class GroupSummarySerializer(serializers.ModelSerializer):
    class Meta:
        model = Group
        fields = ['id', 'name']

class MaterialSerializer(serializers.ModelSerializer):
    created_by = serializers.SerializerMethodField()
    groups = GroupSummarySerializer(many=True, read_only=True)
    group_ids = serializers.ListField(
        child=serializers.UUIDField(),
        write_only=True,
        required=False,
        help_text="List of Group IDs to assign this material to."
    )

    ALLOWED_EXTENSIONS = {
        Material.FileType.PDF: {".pdf"},
        Material.FileType.AUDIO: {".mp3", ".wav", ".ogg"},
        Material.FileType.IMAGE: {".jpg", ".jpeg", ".png"},
        Material.FileType.DOCX: {".doc", ".docx"},
    }

    class Meta:
        model = Material
        fields = [
            "id",
            "name",
            "file",
            "file_type",
            "created_by",
            "is_public",
            "groups",
            "group_ids",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at", "created_by", "groups"]

    def get_created_by(self, obj):
        user_map = self.context.get('user_map')
        if user_map is not None and obj.created_by_id:
            user = user_map.get(obj.created_by_id)
            return UserSummarySerializer.from_user(user)
        return UserSummarySerializer.from_user(obj.created_by)

    def validate(self, attrs):
        attrs = super().validate(attrs)
        instance = getattr(self, "instance", None)
        effective_file = attrs.get("file") or (getattr(instance, "file", None) if instance else None)
        effective_type = attrs.get("file_type") or (instance.file_type if instance else None)

        if effective_type in self.ALLOWED_EXTENSIONS and effective_file:
            ext = os.path.splitext(getattr(effective_file, "name", "") or "")[1].lower()
            allowed = self.ALLOWED_EXTENSIONS[effective_type]
            if ext not in allowed:
                raise serializers.ValidationError({
                    "file": f"File extension '{ext or 'unknown'}' does not match file_type '{effective_type}'. Allowed: {', '.join(sorted(allowed))}."
                })

            # SECURITY FIX: Detect MIME type from file content, NOT from Content-Type header
            # This prevents MIME spoofing attacks (e.g., uploading .exe as PDF)
            mime_type = self._detect_mime_type_from_content(effective_file)

            EXPECTED_MIME_TYPES = {
                Material.FileType.PDF: {'application/pdf'},
                Material.FileType.AUDIO: {
                    'audio/mpeg', 'audio/mp3', 'audio/x-mpeg',  # MPEG variants
                    'audio/wav', 'audio/wave', 'audio/x-wav',   # WAV variants
                    'audio/ogg', 'audio/vorbis', 'audio/x-vorbis+ogg',  # OGG variants
                },
                Material.FileType.IMAGE: {'image/jpeg', 'image/jpg', 'image/png'},
                Material.FileType.DOCX: {
                    'application/msword',
                    'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
                    'application/vnd.ms-word.document.macroEnabled.12',  # Word macro-enabled
                },
            }

            if effective_type in EXPECTED_MIME_TYPES and mime_type:
                expected_mimes = EXPECTED_MIME_TYPES[effective_type]
                if mime_type not in expected_mimes:
                    raise serializers.ValidationError({
                        "file": f"File MIME type '{mime_type}' does not match file_type '{effective_type}'. Expected: {', '.join(sorted(expected_mimes))}."
                    })

        # Validate group_ids if provided
        group_ids = attrs.get('group_ids', [])
        if group_ids:
            if not Group.objects.filter(id__in=group_ids).count() == len(set(group_ids)):
                raise serializers.ValidationError({"group_ids": "One or more groups not found."})

        return attrs

    def _detect_mime_type_from_content(self, file_obj):
        """
        Detect MIME type from actual file content (magic bytes), NOT from headers.
        This prevents MIME spoofing attacks.
        
        Args:
            file_obj: Uploaded file object (UploadedFile or similar)
            
        Returns:
            str: MIME type detected from file content (lowercase), or empty string if detection fails
        """
        try:
            # Read first few bytes for magic detection
            if hasattr(file_obj, 'seek'):
                file_obj.seek(0)
            
            file_data = file_obj.read(512)  # Read first 512 bytes for magic detection
            
            # Reset file pointer for later processing
            if hasattr(file_obj, 'seek'):
                file_obj.seek(0)
            
            # Primary: Use python-magic if available (most reliable)
            if HAS_MAGIC and file_data:
                try:
                    mime_type = magic.from_buffer(file_data, mime=True)
                    if mime_type:
                        logger.info(f"MIME detected via magic: {mime_type}")
                        return mime_type.lower()
                except Exception as e:
                    logger.warning(f"Magic library detection failed: {e}")
            
            # Fallback: mimetypes.guess_type() based on filename only (less secure)
            filename = getattr(file_obj, 'name', '')
            if filename:
                guessed, _ = mimetypes.guess_type(filename)
                if guessed:
                    logger.info(f"MIME guessed via filename: {guessed}")
                    return guessed.lower()
            
            # Last resort: Log warning and return empty (will fail validation)
            logger.warning(f"Could not detect MIME type for file: {filename}")
            return ""
            
        except Exception as e:
            logger.error(f"Error detecting MIME type: {e}")
            return ""

    def create(self, validated_data):
        group_ids = validated_data.pop('group_ids', [])
        material = super().create(validated_data)
        if group_ids:
            material.groups.set(group_ids)
        return material

    def update(self, instance, validated_data):
        group_ids = validated_data.pop('group_ids', None)
        material = super().update(instance, validated_data)
        if group_ids is not None:
             material.groups.set(group_ids)
        return material

