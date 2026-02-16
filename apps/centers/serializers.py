
#apps/centers/serializers.py
from rest_framework import serializers
from django.db.models import Q
from django.utils import timezone
from drf_spectacular.utils import extend_schema_field
from datetime import timedelta
import uuid
import logging

logger = logging.getLogger(__name__)

try:
    from apps.centers.models import Invitation, ContactRequest, Center, Subscription
except Exception:  # pragma: no cover
    Invitation = None
    ContactRequest = None
    Center = None
    Subscription = None

from apps.authentication.models import User
from apps.authentication.serializers import UserSerializer
from apps.core.utils import generate_code


# --- SUBSCRIPTION SERIALIZERS ---

class SubscriptionSerializer(serializers.ModelSerializer):
    """Subscription details for the center."""
    plan_display = serializers.CharField(source='get_plan_display', read_only=True)
    is_expired = serializers.BooleanField(read_only=True)
    days_remaining = serializers.IntegerField(read_only=True)
    
    class Meta:
        model = Subscription
        fields = [
            'id', 'plan', 'plan_display', 'price', 'currency', 
            'billing_cycle', 'next_billing_date', 'starts_at', 'ends_at',
            'is_active', 'auto_renew', 'is_expired', 'days_remaining',
            'created_at', 'updated_at'
        ]
        read_only_fields = [
            'id', 'created_at', 'updated_at', 'plan_display', 
            'is_expired', 'days_remaining'
        ]


class SubscriptionDetailSerializer(serializers.ModelSerializer):
    """Detailed subscription view including center information."""
    plan_display = serializers.CharField(source='get_plan_display', read_only=True)
    is_expired = serializers.BooleanField(read_only=True)
    days_remaining = serializers.IntegerField(read_only=True)
    center_name = serializers.CharField(source='center.name', read_only=True)
    center_id = serializers.IntegerField(source='center.id', read_only=True)
    
    class Meta:
        model = Subscription
        fields = [
            'id', 'center_id', 'center_name', 'plan', 'plan_display', 
            'price', 'currency', 'billing_cycle', 'next_billing_date',
            'starts_at', 'ends_at', 'is_active', 'auto_renew',
            'is_expired', 'days_remaining', 'created_at', 'updated_at'
        ]
        read_only_fields = [
            'id', 'center_id', 'center_name', 'created_at', 'updated_at',
            'plan_display', 'is_expired', 'days_remaining'
        ]


class SubscriptionUpdateSerializer(serializers.ModelSerializer):
    """
    Serializer for Owner to update subscription plans.
    Only plan can be changed; dates and pricing are auto-calculated.
    """
    
    class Meta:
        model = Subscription
        fields = ['plan']
    
    def validate_plan(self, value):
        """Ensure plan is valid for upgrade."""
        valid_plans = [Subscription.Plan.FREE, Subscription.Plan.BASIC, 
                      Subscription.Plan.PRO, Subscription.Plan.ENTERPRISE]
        if value not in valid_plans:
            raise serializers.ValidationError("Invalid subscription plan.")
        return value
    
    def update(self, instance, validated_data):
        """
        Update subscription plan and adjust dates/pricing accordingly.
        """
        new_plan = validated_data.get('plan')
        old_plan = instance.plan
        
        if new_plan == old_plan:
            return instance
        
        # Update plan
        instance.plan = new_plan
        
        # Set pricing based on plan (placeholder values - adjust as needed)
        plan_pricing = {
            Subscription.Plan.FREE: {'price': 0, 'months': 2},
            Subscription.Plan.BASIC: {'price': 29.99, 'months': 1},
            Subscription.Plan.PRO: {'price': 79.99, 'months': 1},
            Subscription.Plan.ENTERPRISE: {'price': 199.99, 'months': 1},
        }
        
        pricing = plan_pricing.get(new_plan, {'price': 0, 'months': 1})
        instance.price = pricing['price']
        
        # Update subscription dates
        now = timezone.now()
        instance.starts_at = now
        instance.ends_at = now + timedelta(days=30 * pricing['months'])
        
        # Activate subscription and update center status
        instance.is_active = True
        instance.auto_renew = new_plan != Subscription.Plan.FREE
        instance.save()
        
        # Update center status to ACTIVE (if not FREE)
        if new_plan != Subscription.Plan.FREE:
            instance.center.status = instance.center.Status.ACTIVE
            instance.center.save(update_fields=['status', 'updated_at'])
            logger.info(
                f"✅ Upgraded center {instance.center.name} to {new_plan}",
                extra={'center_id': instance.center.id, 'plan': new_plan}
            )
        
        return instance

# --- CENTER SERIALIZERS ---

class CenterSerializer(serializers.ModelSerializer):
    """
    Public Center serializer.
    Used for lists or public profiles.
    """
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    subscription = SubscriptionSerializer(read_only=True)

    class Meta:
        model = Center
        fields = [
            'id', 'name', 'slug', 'avatar', 'description', 
            'email', 'phone', 'website', 'address', 'primary_color',
            'status', 'status_display', 'is_ready',
            'subscription', 'created_at'
        ]
        read_only_fields = ['id', 'slug', 'is_ready', 'created_at', 'subscription']

class OwnerCenterSerializer(serializers.ModelSerializer):
    """
    Serializer for Owner/Admin to manage center details.
    Includes editable contact info and branding.
    """
    class Meta:
        model = Center
        fields = [
            'id', 'name', 'slug', 'avatar', 'description',
            'email', 'phone', 'website', 'address', 'primary_color',
            'status', 'is_ready', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'slug', 'is_ready', 'created_at', 'updated_at']

class OwnerCenterListSerializer(serializers.ModelSerializer):
    """
    Optimized serializer for listing centers for the Owner.
    """
    center_name = serializers.CharField(source='name', read_only=True)
    centeradmin_emails = serializers.SerializerMethodField()
    teacher_count = serializers.IntegerField(read_only=True)
    center_avatar = serializers.ImageField(source='avatar', read_only=True)
    plan_name = serializers.CharField(source='subscription.get_plan_display', read_only=True)
    
    class Meta:
        model = Center
        fields = [
            "id", "center_name", "center_avatar", 
            "centeradmin_emails", "teacher_count", "plan_name",
            "status", "created_at",
        ]
        read_only_fields = ["id", "created_at"]
    
    def get_centeradmin_emails(self, obj) -> list:
        """Get CENTER_ADMIN users for this center (use prefetched center_admins when available)."""
        admins = getattr(obj, "center_admins", None)
        if admins is not None:
            return [
                {"id": a.id, "email": a.email, "first_name": a.first_name, "last_name": a.last_name}
                for a in admins
            ]
        return list(
            User.objects.filter(
                center_id=obj.id,
                role=User.Role.CENTERADMIN,
                is_active=True,
            ).values("id", "email", "first_name", "last_name")
        )

# --- INVITATION SERIALIZERS ---

class InvitationCreateSerializer(serializers.ModelSerializer):
    """
    Invitation creation - CENTER_ADMIN only.
    Roles: TEACHER, STUDENT (Assistant removed).
    """
    quantity = serializers.IntegerField(default=1, min_value=1, max_value=100, write_only=True)

    class Meta:
        model = Invitation
        fields = ["id", "role", "is_guest", "quantity"]

    def validate(self, data):
        request = self.context["request"]
        inviter: User = request.user
        role = data.get("role")
        is_guest = data.get("is_guest", False)

        # Only CENTER_ADMIN can create invitations
        if inviter.role != User.Role.CENTERADMIN:
            raise serializers.ValidationError("Only CENTER_ADMIN can create invitations.")

        if not inviter.center_id:
            raise serializers.ValidationError("You must belong to a center to create invitations.")

        # Guest mode rules
        if is_guest:
            if role != User.Role.STUDENT:
                raise serializers.ValidationError(
                    {"role": "Guest mode is only available for STUDENT role."}
                )

        # Assistant role removed, so no need to check teacher existence
        if role not in (User.Role.TEACHER, User.Role.STUDENT):
             raise serializers.ValidationError("Invalid role. Allowed: TEACHER, STUDENT.")

        return data

    def create(self, validated_data):
        quantity = validated_data.pop('quantity', 1)
        inviter = self.context["request"].user
        
        # Verify center exists
        try:
            center = Center.objects.get(id=inviter.center_id)
        except Center.DoesNotExist:
            raise serializers.ValidationError("Center not found.")
        
        # Calculate expiration if guest
        expires_at = None
        if validated_data.get("is_guest", False):
            expires_at = timezone.now() + timedelta(hours=24)

        base_data = {
            **validated_data,
            "center_id": center.id,
            "invited_by_id": inviter.id,
        }
        if expires_at:
            base_data["expires_at"] = expires_at

        invitations = []
        for _ in range(quantity):
            data = base_data.copy()
            data["code"] = generate_code(10)
            data["id"] = uuid.uuid4()
            invitations.append(Invitation(**data))
        
        created = Invitation.objects.bulk_create(invitations)
        return created[0] if quantity == 1 else created

class InvitationDetailSerializer(serializers.ModelSerializer):
    """Serializer for invitation details."""
    invited_by_id = serializers.IntegerField(source='invited_by.id', read_only=True)
    center_id = serializers.IntegerField(source='center.id', read_only=True)
    target_user = UserSerializer(read_only=True)

    class Meta:
        model = Invitation
        fields = ["id", "code", "role", "status", "is_guest", "center_id",
                  "invited_by_id", "target_user", "expires_at", "created_at"]

class InvitationApproveSerializer(serializers.Serializer):
    code = serializers.CharField()

    def validate(self, data):
        code = data.get("code")
        try:
            invitation = Invitation.objects.select_related("invited_by", "center", "target_user")\
                                           .get(code=code, status="PENDING")
        except Invitation.DoesNotExist:
            raise serializers.ValidationError({"code": "Invitation not found or already used."})

        if invitation.is_expired:
            raise serializers.ValidationError({"code": "Invitation has expired."})

        data["invitation"] = invitation

        request = self.context.get("request")
        if request and request.user.role != User.Role.CENTERADMIN:
            raise serializers.ValidationError({"code": "Only CENTER_ADMIN can approve invitations."})

        return data

    def save(self, **kwargs):
        from apps.centers.services import approve_invitation
        approver = self.context["request"].user
        invitation = self.validated_data["invitation"]
        user = approve_invitation(invitation, approver)
        return user

# --- CENTER ADMIN MANAGEMENT SERIALIZERS ---

class CenterAdminCreateSerializer(serializers.Serializer):
    """Serializer for creating CenterAdmin users (by Owner)."""
    email = serializers.EmailField()
    first_name = serializers.CharField(max_length=150)
    last_name = serializers.CharField(max_length=150)
    password = serializers.CharField(write_only=True, min_length=6)

    def validate_email(self, value):
        if User.objects.filter(email=value).exists():
            raise serializers.ValidationError("A user with this email already exists.")
        return value

    def create(self, validated_data):
        center: Center = self.context["center"]
        user = User.objects.create_user(
            email=validated_data["email"],
            password=validated_data["password"],
            first_name=validated_data["first_name"],
            last_name=validated_data["last_name"],
            role=User.Role.CENTERADMIN,
            center=center,
            is_approved=True,
            is_staff=True,
        )
        return user

class CenterAdminListSerializer(serializers.ModelSerializer):
    center_name = serializers.SerializerMethodField()
    
    class Meta:
        model = User
        fields = ["id", "email", "first_name", "last_name", "center", "center_name", "is_approved", "is_active", "created_at"]
    
    def get_center_name(self, obj) -> str | None:
        try:
            from apps.core.tenant_utils import with_public_schema
            return with_public_schema(lambda: obj.center.name if obj.center else None)
        except Exception:
            return None

class CenterAdminDetailSerializer(serializers.ModelSerializer):
    center_name = serializers.SerializerMethodField()
    
    class Meta:
        model = User
        fields = [
            "id", "email", "first_name", "last_name", "role", "center", "center_name",
            "is_approved", "is_active", "avatar", "created_at", "updated_at"
        ]
        read_only_fields = ["id", "email", "role", "center", "center_name", "created_at", "updated_at"]
    
    def get_center_name(self, obj) -> str | None:
        try:
            from apps.core.tenant_utils import with_public_schema
            return with_public_schema(lambda: obj.center.name if obj.center else None)
        except Exception:
            return None

class CenterAdminUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ["first_name", "last_name", "is_approved", "is_active"]
    
    def validate(self, attrs):
        if self.instance and self.instance.role != User.Role.CENTERADMIN:
            raise serializers.ValidationError("Only CenterAdmin users can be updated through this endpoint.")
        return attrs

# --- CONTACT REQUEST SERIALIZERS ---

class ContactRequestCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = ContactRequest
        fields = ["id", "center_name", "full_name", "phone_number", "message"]
    
    def validate(self, attrs):
        center_name = attrs.get('center_name')
        phone_number = attrs.get('phone_number')
        
        # Check duplicates
        existing = ContactRequest.objects.filter(
            Q(center_name__iexact=center_name, phone_number=phone_number) |
            Q(phone_number=phone_number)
        ).filter(status__in=['PENDING', 'CONTACTED']).first()
        
        if existing:
            raise serializers.ValidationError("You have already contacted us. We will get back to you soon.")
        return attrs
    
    def create(self, validated_data):
        request = self.context.get('request')
        if request:
            x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
            validated_data['ip_address'] = x_forwarded_for.split(',')[0] if x_forwarded_for else request.META.get('REMOTE_ADDR')
        return super().create(validated_data)

class ContactRequestListSerializer(serializers.ModelSerializer):
    class Meta:
        model = ContactRequest
        fields = [
            "id", "center_name", "full_name", "phone_number", "message",
            "status", "ip_address", "created_at", "updated_at"
        ]
        read_only_fields = ["id", "ip_address", "created_at", "updated_at"]

class ContactRequestUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = ContactRequest
        fields = ["status"]


# --- GUEST SERIALIZERS ---

class GuestListSerializer(serializers.ModelSerializer):
    """Serializer for listing GUEST users."""
    invitation_code = serializers.SerializerMethodField()
    invitation_expires_at = serializers.SerializerMethodField()
    is_expired = serializers.SerializerMethodField()
    
    class Meta:
        model = User
        fields = [
            "id", "email", "first_name", "last_name", "role", "is_active", "is_approved",
            "invitation_code", "invitation_expires_at", "is_expired", "created_at"
        ]
    
    @extend_schema_field(serializers.CharField(allow_null=True, help_text="Guest invitation code"))
    def get_invitation_code(self, obj):
        try:
            invitation = Invitation.objects.filter(target_user_id=obj.id, is_guest=True).first()
            return invitation.code if invitation else None
        except Exception:
            return None

    @extend_schema_field(serializers.DateTimeField(allow_null=True, help_text="Invitation expiration time"))
    def get_invitation_expires_at(self, obj):
        try:
            invitation = Invitation.objects.filter(target_user_id=obj.id, is_guest=True).first()
            return invitation.expires_at if invitation else None
        except Exception:
            return None

    @extend_schema_field(serializers.BooleanField(help_text="Whether the guest invitation has expired"))
    def get_is_expired(self, obj):
        # Guest expiration logic check
        try:
            invitation = Invitation.objects.filter(target_user_id=obj.id, is_guest=True).first()
            if invitation and invitation.expires_at:
                return timezone.now() > invitation.expires_at
            
            # Fallback to created_at + 24h
            threshold = obj.created_at + timedelta(hours=24)
            return timezone.now() > threshold
        except Exception:
            return True

class GuestUpgradeSerializer(serializers.Serializer):
    """Upgrade GUEST to STUDENT."""
    user_id = serializers.IntegerField()
    
    def validate_user_id(self, value):
        request = self.context.get("request")
        if not request:
            raise serializers.ValidationError("Request context required.")
        
        try:
            user = User.objects.get(id=value, role=User.Role.GUEST)
        except User.DoesNotExist:
            raise serializers.ValidationError("User not found or is not a GUEST.")
        
        if user.center_id != request.user.center_id:
            raise serializers.ValidationError("User belongs to a different center.")
        return value
    
    def save(self, **kwargs):
        from django.db import transaction
        request = self.context.get("request")
        user_id = self.validated_data["user_id"]
        
        with transaction.atomic():
            guest_user = User.objects.select_for_update().get(id=user_id)
            
            # Clean up old invitation
            existing_inv = Invitation.objects.filter(target_user_id=guest_user.id).first()
            if existing_inv:
                existing_inv.target_user = None
                if existing_inv.is_guest:
                    existing_inv.status = "EXPIRED"
                existing_inv.save()
            
            # Create new APPROVED invitation
            Invitation.objects.create(
                id=uuid.uuid4(),
                code=generate_code(10),
                role=User.Role.STUDENT,
                center=guest_user.center,
                invited_by=request.user,
                target_user=guest_user,
                is_guest=False,
                status="APPROVED",
                approved_by=request.user,
            )
            
            # Upgrade user
            guest_user.role = User.Role.STUDENT
            guest_user.is_active = True
            guest_user.is_approved = True
            guest_user.save()
            
        return guest_user