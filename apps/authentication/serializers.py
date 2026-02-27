"""
Authentication Serializers
"""

from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from django.contrib.auth import authenticate
from django.contrib.auth.password_validation import validate_password
from rest_framework.exceptions import AuthenticationFailed
from drf_spectacular.utils import extend_schema_field
from drf_spectacular.types import OpenApiTypes

from .models import User, UserSession
from .models_hierarchy import OrganizationUser, Branch, BranchUser
# from apps.core.models import Organization # Removed for circular dependency


class CustomTokenObtainPairSerializer(TokenObtainPairSerializer):
    """
    Enhanced JWT token serializer with tenant binding.
    SECURITY: Includes organization_id claim to prevent cross-tenant token reuse.
    """

    email = serializers.CharField(required=True, write_only=True)
    username = None  # Disable the default username field

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if 'username' in self.fields:
            del self.fields['username']

    @classmethod
    def get_token(cls, user):
        print(f"[Login Debug] get_token called for {user}", flush=True)
        token = super().get_token(user)
        organization = user.get_organization()

        # SECURITY: Non-superusers MUST belong to an organization
        if not user.is_superuser and not organization:
            raise AuthenticationFailed(
                'User is not assigned to any organization'
            )

        # SECURITY: Hard tenant binding from source-of-truth membership
        branch_ids = []

        if organization:
            token['organization_id'] = str(organization.id)
            token['organization_name'] = getattr(organization, 'name', None)
            token['organization_slug'] = getattr(organization, 'slug', None)

            try:
                branch_ids = list(
                    user.branch_memberships.filter(
                        is_active=True,
                        branch__organization=organization
                    ).values_list('branch_id', flat=True)
                )
            except Exception:
                branch_ids = []
        else:
            # Superuser only
            token['organization_id'] = None
            token['organization_name'] = None
            token['organization_slug'] = None
            branch_ids = []
        # User identity claims (unchanged)
        token['user_id'] = str(user.id)
        token['email'] = user.email
        token['full_name'] = user.full_name
        token['employee_id'] = user.employee_id

        # ðŸ”’ SECURITY: Freeze role context (even if ABAC is used)
        # Empty list is acceptable, but claim must exist
        token['role_ids'] = []
        token['branch_ids'] = [str(branch_id) for branch_id in branch_ids]

        return token

    def validate(self, attrs):
        print(f"[Login Debug] Serializer validate called for {attrs.get('email')}", flush=True)
        email = attrs.get('email')
        password = attrs.get('password')

        if not email or not password:
            raise serializers.ValidationError(
                {'detail': 'Must include "email" and "password".'}
            )

        print("[Login Debug] Calling authenticate...", flush=True)
        user = authenticate(username=email, password=password)
        print(f"[Login Debug] Authenticate result: {user}", flush=True)

        if not user:
            raise serializers.ValidationError(
                {'detail': 'Invalid email or password.'}
            )

        if user.is_locked():
            raise serializers.ValidationError(
                'Account is locked. Please try again later or contact support.'
            )

        request = self.context.get('request')
        request_org = getattr(request, 'organization', None) if request else None

        if not user.is_superuser:
            membership_qs = user.organization_memberships.filter(is_active=True)

            if request_org:
                membership_qs = membership_qs.filter(organization=request_org)

            if not membership_qs.exists():
                raise AuthenticationFailed('User is not a member of this organization')

        # ðŸ”’ SECURITY: Token creation already enforces org binding
        refresh = self.get_token(user)

        return {
            'refresh': str(refresh),
            'access': str(refresh.access_token),
        }


class UserSerializer(serializers.ModelSerializer):
    """User serializer for profile"""

    full_name = serializers.ReadOnlyField()
    roles = serializers.SerializerMethodField()
    permissions = serializers.SerializerMethodField()
    organization = serializers.SerializerMethodField()
    is_org_admin = serializers.SerializerMethodField()
    branch_ids = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = [
            'id', 'email', 'employee_id', 'first_name', 'last_name',
            'middle_name', 'full_name', 'phone', 'avatar', 'date_of_birth',
            'gender', 'is_verified', 'is_2fa_enabled', 'is_superuser', 'is_staff',
            'is_org_admin', 'is_active', 'branch_ids',
            'timezone', 'language', 'roles', 'permissions', 'organization',
            'date_joined', 'last_login'
        ]
        read_only_fields = [
            'id', 'email', 'is_verified', 'is_superuser',
            'is_staff', 'is_org_admin', 'date_joined', 'last_login'
        ]

    @extend_schema_field(OpenApiTypes.BOOL)
    def get_is_org_admin(self, obj):
        return obj.is_organization_admin()

    @extend_schema_field({'type': 'array', 'items': {'type': 'string'}})
    def get_roles(self, obj):
        return obj.get_role_codes()

    @extend_schema_field({'type': 'array', 'items': {'type': 'string'}})
    def get_permissions(self, obj):
        return obj.get_all_permissions()

    @extend_schema_field({'type': 'object', 'nullable': True, 'properties': {'id': {'type': 'string'}, 'name': {'type': 'string'}, 'slug': {'type': 'string', 'nullable': True}, 'subscription_status': {'type': 'string', 'nullable': True}}})
    def get_organization(self, obj):
        try:
            organization = obj.get_organization()
            if not organization:
                return None

            return {
                'id': str(organization.id),
                'name': organization.name,
                'slug': getattr(organization, 'slug', None),
                'subscription_status': getattr(organization, 'subscription_status', None)
            }
        except Exception:
            return None

    @extend_schema_field({'type': 'array', 'items': {'type': 'string'}})
    def get_branch_ids(self, obj):
        try:
            memberships = obj.branch_memberships.filter(is_active=True)
            request = self.context.get('request') if self.context else None
            request_org = getattr(request, 'organization', None) if request else None
            if request_org:
                memberships = memberships.filter(branch__organization=request_org)
            return [str(branch_id) for branch_id in memberships.values_list('branch_id', flat=True)]
        except Exception:
            return []


class UserCreateSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, validators=[validate_password])
    password_confirm = serializers.CharField(write_only=True)

    class Meta:
        model = User
        fields = [
            'email', 'first_name', 'last_name', 'phone',
            'password', 'password_confirm'
        ]

    def validate(self, attrs):
        if attrs['password'] != attrs['password_confirm']:
            raise serializers.ValidationError(
                {'password_confirm': 'Passwords do not match.'}
            )
        return attrs

    def create(self, validated_data):
        validated_data.pop('password_confirm')
        return User.objects.create_user(**validated_data)


class UserOrgAdminCreateSerializer(serializers.ModelSerializer):
    """
    ðŸ”’ SECURITY: Org admins create users ONLY inside their org
    """

    password = serializers.CharField(write_only=True, validators=[validate_password])
    password_confirm = serializers.CharField(write_only=True)
    organization = serializers.UUIDField(
        required=False,
        allow_null=True
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # qs = ... # Cannot use Organization.objects at top level
        # We'll rely on validation in validate/create
        pass


    class Meta:
        model = User
        fields = [
            'email', 'username', 'first_name', 'last_name', 'middle_name',
            'phone', 'password', 'password_confirm', 'employee_id',
            'gender', 'date_of_birth',
            'is_verified', 'is_active', 'is_org_admin', 'organization'
        ]
        read_only_fields = [
            'is_staff', 'is_superuser'
        ]

    def validate(self, attrs):
        request = self.context.get('request')

        if not request or not request.user:
            raise serializers.ValidationError('Authentication required')

        if not request.user.is_org_admin and not request.user.is_superuser:
            raise serializers.ValidationError(
                'Only organization admins can create users'
            )

        if attrs.get('password') != attrs.get('password_confirm'):
            raise serializers.ValidationError(
                {'password_confirm': 'Passwords do not match.'}
            )

        return attrs

    def create(self, validated_data):
        request = self.context.get('request')
        password_confirm = validated_data.pop('password_confirm', None)
        is_org_admin = validated_data.pop('is_org_admin', False)
        organization_id = validated_data.pop('organization', None)

        if request.user.is_org_admin and not request.user.is_superuser:
            org = request.user.get_organization()
            organization_id = org.id if org else None
        
        # 1. Create the base User
        validated_data['organization_id'] = organization_id
        validated_data['is_org_admin'] = is_org_admin
        validated_data['is_staff'] = is_org_admin # Org admins are staff
        
        user = User.objects.create_user(**validated_data)

        # 2. Create the Organization Mapping (Source of Truth)
        if organization_id:
            from .models_hierarchy import OrganizationUser
            from apps.core.models import Organization
            organization = Organization.objects.filter(id=organization_id).first()
            if not organization:
                return user
            OrganizationUser.objects.get_or_create(
                user=user,
                organization=organization,
                defaults={
                    'role': OrganizationUser.RoleChoices.ORG_ADMIN if is_org_admin else OrganizationUser.RoleChoices.EMPLOYEE,
                    'is_active': True,
                    'created_by': request.user
                }
            )

        return user

    def update(self, instance, validated_data):
        validated_data.pop('organization', None)

        request = self.context.get('request')
        if request.user.is_org_admin and not request.user.is_superuser:
            validated_data.pop('is_org_admin', None)
            validated_data.pop('is_staff', None)
            validated_data.pop('is_superuser', None)

        return super().update(instance, validated_data)


class UserSelfProfileSerializer(serializers.ModelSerializer):
    full_name = serializers.ReadOnlyField()
    organization_name = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = [
            'id', 'email', 'first_name', 'last_name', 'middle_name',
            'full_name', 'phone', 'avatar', 'date_of_birth',
            'gender', 'timezone', 'language',
            'organization_name', 'date_joined', 'last_login'
        ]
        read_only_fields = [
            'id', 'email', 'full_name',
            'organization_name', 'date_joined', 'last_login'
        ]

    @extend_schema_field({'type': 'string', 'nullable': True})
    def get_organization_name(self, obj):
        try:
            organization = obj.get_organization()
            if not organization:
                return None
            return organization.name
        except:
            return "Unknown"

    def update(self, instance, validated_data):
        dangerous_fields = [
            'organization_id', 'is_org_admin', 'is_staff',
            'is_superuser', 'username', 'password',
            'employee_id', 'slug', 'is_active',
            'is_verified', 'permissions', 'groups'
        ]

        for field in dangerous_fields:
            validated_data.pop(field, None)

        return super().update(instance, validated_data)


class PasswordChangeSerializer(serializers.Serializer):
    current_password = serializers.CharField(required=True)
    new_password = serializers.CharField(
        required=True, validators=[validate_password]
    )
    new_password_confirm = serializers.CharField(required=True)

    def validate_current_password(self, value):
        user = self.context['request'].user
        if not user.check_password(value):
            raise serializers.ValidationError(
                'Current password is incorrect.'
            )
        return value

    def validate(self, attrs):
        if attrs['new_password'] != attrs['new_password_confirm']:
            raise serializers.ValidationError(
                {'new_password_confirm': 'Passwords do not match.'}
            )
        return attrs

    def save(self):
        from django.utils import timezone

        user = self.context['request'].user
        user.set_password(self.validated_data['new_password'])
        user.password_changed_at = timezone.now()
        user.must_change_password = False
        user.save(update_fields=['password', 'password_changed_at', 'must_change_password'])


class PasswordResetRequestSerializer(serializers.Serializer):
    email = serializers.EmailField()

    def save(self):
        from django.core.mail import send_mail
        from django.conf import settings
        from django.utils import timezone
        from datetime import timedelta
        import secrets

        from .models import User, PasswordResetToken

        email = self.validated_data['email']

        try:
            user = User.objects.get(email=email, is_active=True, is_deleted=False)
        except User.DoesNotExist:
            return

        PasswordResetToken.objects.filter(user=user, is_used=False).update(is_used=True)

        token = secrets.token_urlsafe(32)
        expires_at = timezone.now() + timedelta(hours=24)

        PasswordResetToken.objects.create(
            user=user,
            token=token,
            expires_at=expires_at
        )

        frontend_url = getattr(settings, 'FRONTEND_URL', 'http://localhost:5173')
        reset_link = f"{frontend_url}/reset-password?token={token}"

        send_mail(
            subject='Password Reset Request',
            message=f'Click the link to reset your password: {reset_link}\n\nThis link expires in 24 hours.',
            from_email=getattr(settings, 'DEFAULT_FROM_EMAIL', 'noreply@example.com'),
            recipient_list=[user.email],
            fail_silently=False,
        )


class PasswordResetConfirmSerializer(serializers.Serializer):
    token = serializers.CharField()
    new_password = serializers.CharField(validators=[validate_password])
    new_password_confirm = serializers.CharField()

    def validate(self, attrs):
        if attrs['new_password'] != attrs['new_password_confirm']:
            raise serializers.ValidationError(
                {'new_password_confirm': 'Passwords do not match.'}
            )

        from .models import PasswordResetToken

        try:
            reset_token = PasswordResetToken.objects.get(
                token=attrs['token'],
                is_used=False
            )
            if not reset_token.is_valid():
                raise serializers.ValidationError(
                    {'token': 'Token has expired.'}
                )
            attrs['reset_token'] = reset_token
        except PasswordResetToken.DoesNotExist:
            raise serializers.ValidationError(
                {'token': 'Invalid or expired token.'}
            )

        return attrs

    def save(self):
        reset_token = self.validated_data['reset_token']
        new_password = self.validated_data['new_password']

        user = reset_token.user
        user.set_password(new_password)
        user.save(update_fields=['password'])

        reset_token.is_used = True
        reset_token.save(update_fields=['is_used'])


class TwoFactorEnableSerializer(serializers.Serializer):
    password = serializers.CharField(required=True)

    def validate_password(self, value):
        user = self.context['request'].user
        if not user.check_password(value):
            raise serializers.ValidationError('Invalid password.')
        return value

    def save(self):
        import pyotp
        import qrcode
        import io
        import base64

        user = self.context['request'].user

        secret = pyotp.random_base32()

        user.two_factor_secret = secret
        user.save(update_fields=['two_factor_secret'])

        totp = pyotp.TOTP(secret)
        issuer_name = 'PS IntelliHR'
        provisioning_uri = totp.provisioning_uri(
            name=user.email,
            issuer_name=issuer_name
        )

        qr = qrcode.QRCode(version=1, box_size=10, border=5)
        qr.add_data(provisioning_uri)
        qr.make(fit=True)
        img = qr.make_image(fill_color='black', back_color='white')

        buffer = io.BytesIO()
        img.save(buffer, format='PNG')
        buffer.seek(0)
        qr_code_base64 = base64.b64encode(buffer.getvalue()).decode('utf-8')

        return {
            'secret': secret,
            'qr_code': f'data:image/png;base64,{qr_code_base64}',
            'provisioning_uri': provisioning_uri,
        }


class TwoFactorVerifySerializer(serializers.Serializer):
    code = serializers.CharField(required=True, min_length=6, max_length=6)

    def validate_code(self, value):
        import pyotp

        user = self.context['request'].user

        if not user.two_factor_secret:
            raise serializers.ValidationError('2FA is not set up.')

        totp = pyotp.TOTP(user.two_factor_secret)
        if not totp.verify(value):
            raise serializers.ValidationError('Invalid verification code.')

        return value

    def save(self):
        import secrets

        user = self.context['request'].user

        user.is_2fa_enabled = True
        backup_codes = [secrets.token_hex(4) for _ in range(10)]
        user.backup_codes = backup_codes
        user.save(update_fields=['is_2fa_enabled', 'backup_codes'])

        return {'backup_codes': backup_codes}


class UserSessionSerializer(serializers.ModelSerializer):
    user_id = serializers.UUIDField(source='user.id', read_only=True)
    organization_id = serializers.SerializerMethodField()

    class Meta:
        model = UserSession
        fields = [
            'id', 'user_id', 'organization_id', 'device_type', 'device_name',
            'browser', 'os', 'ip_address', 'country', 'city',
            'is_active', 'created_at', 'last_activity'
        ]
        read_only_fields = [
            'id', 'user_id', 'organization_id', 'device_type', 'device_name',
            'browser', 'os', 'ip_address', 'country', 'city',
            'is_active', 'created_at', 'last_activity'
        ]

    def get_organization_id(self, obj):
        return str(obj.organization_id) if obj.organization_id else None


class OrganizationUserSerializer(serializers.ModelSerializer):
    user_email = serializers.CharField(source='user.email', read_only=True)
    user_name = serializers.CharField(source='user.full_name', read_only=True)
    organization_name = serializers.CharField(source='organization.name', read_only=True)

    class Meta:
        model = OrganizationUser
        fields = [
            'id', 'user', 'user_email', 'user_name', 'organization',
            'organization_name', 'role', 'is_active', 'created_at', 'updated_at'
        ]
        read_only_fields = ['organization', 'created_at', 'updated_at']

    def validate(self, attrs):
        attrs = super().validate(attrs)
        request = self.context.get('request')
        org = getattr(request, 'organization', None) if request else None
        user = attrs.get('user') or getattr(self.instance, 'user', None)

        if org and user:
            conflict_exists = user.organization_memberships.filter(
                is_active=True
            ).exclude(organization=org).exists()
            if conflict_exists:
                raise serializers.ValidationError('User already belongs to another organization')
        return attrs

    def create(self, validated_data):
        request = self.context.get('request')
        org = getattr(request, 'organization', None) if request else None
        if org:
            validated_data['organization'] = org
        validated_data.setdefault('created_by', request.user if request else None)
        return super().create(validated_data)


class BranchSerializer(serializers.ModelSerializer):
    organization_id = serializers.UUIDField(source='organization.id', read_only=True)

    class Meta:
        model = Branch
        fields = [
            'id', 'organization_id', 'name', 'code', 'branch_type', 'is_headquarters',
            'address_line1', 'address_line2', 'city', 'state', 'country', 'postal_code',
            'phone', 'email', 'is_active', 'created_at', 'updated_at'
        ]
        read_only_fields = ['organization_id', 'created_at', 'updated_at']

    def create(self, validated_data):
        request = self.context.get('request')
        org = getattr(request, 'organization', None) if request else None
        if not org:
            raise serializers.ValidationError('Organization context is required')
        validated_data['organization'] = org
        validated_data.setdefault('created_by', request.user if request else None)
        return super().create(validated_data)


class BranchUserSerializer(serializers.ModelSerializer):
    branch_name = serializers.CharField(source='branch.name', read_only=True)
    user_email = serializers.CharField(source='user.email', read_only=True)

    class Meta:
        model = BranchUser
        fields = [
            'id', 'branch', 'branch_name', 'user', 'user_email', 'role',
            'is_active', 'created_at', 'updated_at'
        ]
        read_only_fields = ['created_at', 'updated_at']

    def validate(self, attrs):
        attrs = super().validate(attrs)
        request = self.context.get('request')
        org = getattr(request, 'organization', None) if request else None
        branch = attrs.get('branch') or getattr(self.instance, 'branch', None)
        user = attrs.get('user') or getattr(self.instance, 'user', None)

        if org:
            if branch and branch.organization_id != org.id:
                raise serializers.ValidationError('Branch does not belong to this organization')
            if user and not user.organization_memberships.filter(organization=org, is_active=True).exists():
                raise serializers.ValidationError('User is not assigned to this organization')
        return attrs

    def create(self, validated_data):
        request = self.context.get('request')
        validated_data.setdefault('created_by', request.user if request else None)
        return super().create(validated_data)
