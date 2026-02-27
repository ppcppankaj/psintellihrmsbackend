"""
Authentication Models - Custom User Model with RBAC
Hierarchical Multi-Tenancy: Organization → User → Branch
"""

import uuid
from django.contrib.auth.models import AbstractBaseUser, PermissionsMixin, BaseUserManager
from django.db import models
from django.utils import timezone
from django.core.validators import RegexValidator
from django.db.models.signals import pre_delete
from django.dispatch import receiver


class UserManager(BaseUserManager):
    """Custom user manager"""
    
    def create_user(self, email, password=None, **extra_fields):
        if not email:
            raise ValueError('Email is required')
        
        # Extract organization from extra_fields if provided
        organization = extra_fields.pop('organization', None)
        
        # Normalize email and create username
        email = self.normalize_email(email)
        org_slug = organization.slug if organization else 'default'
        username = f"{org_slug}@{email}"
        
        user = self.model(
            email=email,
            username=username,
            organization=organization,
            **extra_fields
        )
        
        user.set_password(password)
        user.save(using=self._db)
        return user
    
    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        extra_fields.setdefault('is_verified', True)
        
        return self.create_user(email, password, **extra_fields)


class User(AbstractBaseUser, PermissionsMixin):
    """
    Custom User model - Global identity, organization assigned via OrganizationUser mapping
    
    CRITICAL: User does NOT directly store organization scope in most cases.
    Organization membership is managed via OrganizationUser mapping model.
    The 'organization' field exists for backward compatibility and quick lookups only.
    """
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    
    # Organization (for backward compat + quick lookups, but use OrganizationUser for source of truth)
    organization = models.ForeignKey(
        'core.Organization',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        db_index=True,
        editable=False,  # Set via OrganizationUser, not directly
        help_text="Organization (denormalized for performance). Use OrganizationUser for source of truth."
    )
    
    # Basic Info
    email = models.EmailField(db_index=True)  # Unique per organization, not globally
    username = models.CharField(max_length=255, unique=True, db_index=True, help_text="Composite: org_slug@email")
    employee_id = models.CharField(max_length=50, blank=True, db_index=True)
    slug = models.SlugField(max_length=100, unique=True, blank=True, help_text="URL-friendly identifier")
    
    first_name = models.CharField(max_length=50)
    last_name = models.CharField(max_length=50)
    middle_name = models.CharField(max_length=50, blank=True)
    
    # Contact
    phone = models.CharField(
        max_length=15,
        blank=True,
        validators=[
            RegexValidator(
                regex=r'^\+?[1-9]\d{6,14}$',
                message='Enter a valid phone number'
            )
        ]
    )
    
    # Profile
    avatar = models.ImageField(upload_to='avatars/', null=True, blank=True)
    date_of_birth = models.DateField(null=True, blank=True)
    gender = models.CharField(
        max_length=30,
        choices=[
            ('male', 'Male'),
            ('female', 'Female'),
            ('other', 'Other'),
            ('prefer_not_to_say', 'Prefer not to say'),
        ],
        blank=True
    )
    
    # Status flags
    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)
    is_verified = models.BooleanField(default=False)
    is_org_admin = models.BooleanField(
        default=False,
        db_index=True,
        help_text="User is an admin of their organization (can create/manage users within org)"
    )
    
    # Security
    password_changed_at = models.DateTimeField(null=True, blank=True)
    must_change_password = models.BooleanField(default=False)
    failed_login_attempts = models.PositiveSmallIntegerField(default=0)
    locked_until = models.DateTimeField(null=True, blank=True)
    
    # 2FA
    is_2fa_enabled = models.BooleanField(default=False)
    two_factor_secret = models.CharField(max_length=255, blank=True)
    backup_codes = models.JSONField(default=list, blank=True)
    
    # Session
    last_login_ip = models.GenericIPAddressField(null=True, blank=True)
    last_login_device = models.CharField(max_length=255, blank=True)
    
    # Timestamps
    date_joined = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)
    
    # Soft delete
    is_deleted = models.BooleanField(default=False)
    deleted_at = models.DateTimeField(null=True, blank=True)
    
    # Preferences
    timezone = models.CharField(max_length=50, default='Asia/Kolkata')
    language = models.CharField(max_length=10, default='en')
    notification_preferences = models.JSONField(default=dict, blank=True)
    
    objects = UserManager()
    
    USERNAME_FIELD = 'username'  # Composite username (org@email)
    REQUIRED_FIELDS = ['email', 'first_name', 'last_name']
    
    class Meta:
        ordering = ['first_name', 'last_name']
        indexes = [
            models.Index(fields=['organization', 'email']),
            models.Index(fields=['organization', 'employee_id']),
            models.Index(fields=['organization', 'is_active', 'is_deleted']),
        ]
        # Email must be unique within each organization
        unique_together = [['organization', 'email']]
    
    def __str__(self):
        return f"{self.full_name} ({self.email})"
    
    @property
    def full_name(self):
        parts = [self.first_name]
        if self.middle_name:
            parts.append(self.middle_name)
        parts.append(self.last_name)
        return ' '.join(parts)
    
    # ===== Hierarchical Multi-Tenancy Helper Methods =====
    
    def get_organization_membership(self):
        """
        Get the user's active organization membership.
        Returns: OrganizationUser instance or None
        """
        try:
            return self.organization_memberships.get(is_active=True)
        except:
            return None
    
    def get_organization(self):
        """
        Get the organization this user belongs to.
        Returns: Organization instance or None
        """
        membership = self.get_organization_membership()
        return membership.organization if membership else self.organization
    
    def is_organization_admin(self):
        """Check if user is an org admin via OrganizationUser mapping"""
        try:
            from .models_hierarchy import OrganizationUser
            membership = self.get_organization_membership()
            if not membership:
                return False
            return membership.role == OrganizationUser.RoleChoices.ORG_ADMIN
        except:
            return False
    
    def get_branch_memberships(self, active_only=True):
        """
        Get all branch memberships for this user.
        Returns: QuerySet of BranchUser instances
        """
        qs = self.branch_memberships.select_related('branch')
        if active_only:
            qs = qs.filter(is_active=True)
        return qs
    
    def get_branches(self, active_only=True):
        """
        Get all branches this user is assigned to.
        Returns: QuerySet of Branch instances
        """
        try:
            from .models_hierarchy import Branch
            branch_ids = self.get_branch_memberships(active_only=active_only).values_list('branch_id', flat=True)
            return Branch.objects.filter(id__in=branch_ids)
        except:
            return None
    
    def is_branch_admin_for(self, branch):
        """
        Check if user is admin of a specific branch.
        Args:
            branch: Branch instance or branch ID
        Returns: bool
        """
        try:
            from .models_hierarchy import BranchUser
            branch_id = branch.id if hasattr(branch, 'id') else branch
            return self.branch_memberships.filter(
                branch_id=branch_id,
                role=BranchUser.RoleChoices.BRANCH_ADMIN,
                is_active=True
            ).exists()
        except:
            return False
    
    def get_admin_branches(self):
        """Get all branches where user is admin"""
        try:
            from .models_hierarchy import Branch, BranchUser
            return Branch.objects.filter(
                user_memberships__user=self,
                user_memberships__role=BranchUser.RoleChoices.BRANCH_ADMIN,
                user_memberships__is_active=True
            )
        except:
            return None
    
    # Backward compatibility property
    @property
    def organization_obj(self):
        """Backward compatible property that uses the mapping model"""
        return self.get_organization()
    
    def is_locked(self):
        """Check if user account is locked"""
        if self.locked_until:
            return timezone.now() < self.locked_until
        return False
    
    def record_login_attempt(self, success=True, ip_address=None, device=None):
        """Record login attempt"""
        if success:
            self.failed_login_attempts = 0
            self.locked_until = None
            self.last_login = timezone.now()
            self.last_login_ip = ip_address
            self.last_login_device = device
        else:
            self.failed_login_attempts += 1
            if self.failed_login_attempts >= 5:
                # Lock for 30 minutes
                self.locked_until = timezone.now() + timezone.timedelta(minutes=30)
        self.save()
    
    def get_roles(self):
        """Get all active roles assigned to this user"""
        from django.db import connection
        if connection.schema_name == 'public':
            return self.user_roles.none()

        from django.utils import timezone
        now = timezone.now()
        return self.user_roles.filter(
            is_active=True
        ).filter(
            models.Q(valid_from__isnull=True) | models.Q(valid_from__lte=now)
        ).filter(
            models.Q(valid_until__isnull=True) | models.Q(valid_until__gte=now)
        ).select_related('role')
    
    def has_role(self, role_identifier):
        """
        Check if user has a specific role.
        Accepts role name or code.
        """
        from django.db import connection
        if connection.schema_name == 'public':
            return False

        return self.user_roles.filter(
            models.Q(role__name__iexact=role_identifier) | 
            models.Q(role__code__iexact=role_identifier),
            is_active=True
        ).exists()
    
    def get_role_codes(self):
        """Get list of role codes for this user"""
        return list(self.get_roles().values_list('role__code', flat=True))
    
    def has_permission_for(self, permission_code, module=None):
        """
        Check if user has a specific permission.
        Checks:
        1. Permission overrides (grant or revoke)
        2. Role-based permissions
        """
        from django.db import connection
        if connection.schema_name == 'public':
            return self.is_superuser

        from django.utils import timezone
        
        # Check for superuser
        if self.is_superuser:
            return True
        
        # ABAC policy-based permission check
        try:
            from apps.abac.engine import PolicyEngine
            engine = PolicyEngine(self, log_decisions=False)
            return engine.check_access(module or 'general', permission_code.split('.')[-1])
            
            if override:
                return override.is_granted  # Explicit grant or revoke
        except Exception:
            pass
        
        # Check role-based permissions
        roles = self.get_roles()
        for user_role in roles:
            if user_role.role.has_permission(permission_code, module):
                return True
        
        return False
    
    def get_all_permissions(self):
        """Get all permission codes for this user"""
        permissions = set()
        for user_role in self.get_roles():
            for perm in user_role.role.get_all_permissions():
                permissions.add(perm.code)
        return list(permissions)
    
    def can_manage_organization(self):
        """Check if user can manage their organization"""
        return self.is_superuser or self.is_organization_admin() or self.is_org_admin
    
    def can_manage_users(self):
        """Check if user can manage users in their organization"""
        return self.is_superuser or self.is_organization_admin() or self.is_org_admin
    
    def can_access_admin(self):
        """Check if user can access Django admin"""
        return self.is_staff and (self.is_superuser or self.is_org_admin)
    
    def is_in_same_organization(self, obj):
        """Check if object belongs to user's organization"""
        if self.is_superuser:
            return True
        
        # Get user's organization via mapping
        user_org = self.get_organization()
        if not user_org:
            return False
        
        if hasattr(obj, 'organization_id'):
            return obj.organization_id == user_org.id
        elif hasattr(obj, 'organization'):
            return obj.organization == user_org
        
        return False
    
    def save(self, *args, **kwargs):
        """Auto-generate slug if not provided"""
        if not self.slug:
            from django.utils.text import slugify
            base_slug = slugify(f"{self.first_name}-{self.last_name}")
            slug = base_slug
            counter = 1
            while User.objects.filter(slug=slug).exclude(pk=self.pk).exists():
                slug = f"{base_slug}-{counter}"
                counter += 1
            self.slug = slug
        super().save(*args, **kwargs)

    def delete(self, using=None, keep_parents=False):
        """Ensure JWT blacklist rows are removed before deleting the user"""
        try:
            from rest_framework_simplejwt.token_blacklist.models import OutstandingToken, BlacklistedToken
            BlacklistedToken.objects.filter(token__user=self).delete()
            OutstandingToken.objects.filter(user=self).delete()
        except Exception:
            pass
        return super().delete(using=using, keep_parents=keep_parents)


# Cleanup related JWT tokens before a user is deleted to avoid FK violations
@receiver(pre_delete, sender=User)
def delete_user_tokens(sender, instance: User, **kwargs):
    try:
        from rest_framework_simplejwt.token_blacklist.models import OutstandingToken, BlacklistedToken
        OutstandingToken.objects.filter(user=instance).delete()
        BlacklistedToken.objects.filter(token__user=instance).delete()
    except Exception:
        # If blacklist app not installed or models unavailable, fail silently
        pass


class UserSession(models.Model):
    """Track user sessions for security - Organization-scoped"""
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='sessions')
    organization = models.ForeignKey(
        'core.Organization',
        on_delete=models.CASCADE,
        db_index=True,
        help_text="Organization this session belongs to"
    )
    
    # Session info
    session_key = models.CharField(max_length=100, unique=True)
    refresh_token = models.CharField(max_length=500, blank=True)
    
    # Device info
    ip_address = models.GenericIPAddressField()
    user_agent = models.TextField()
    device_type = models.CharField(max_length=50)  # desktop, mobile, tablet
    device_name = models.CharField(max_length=255, blank=True)
    browser = models.CharField(max_length=100, blank=True)
    os = models.CharField(max_length=100, blank=True)
    
    # Location
    country = models.CharField(max_length=100, blank=True)
    city = models.CharField(max_length=100, blank=True)
    
    # Status
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    last_activity = models.DateTimeField(auto_now=True)
    expires_at = models.DateTimeField()
    
    class Meta:
        ordering = ['-last_activity']
        indexes = [
            models.Index(fields=['organization', 'user', 'is_active']),
            models.Index(fields=['user', 'is_active']),
        ]
    
    def __str__(self):
        return f"{self.user.email} - {self.device_type} ({self.ip_address})"
    
    def is_expired(self):
        return timezone.now() > self.expires_at
    
    def save(self, *args, **kwargs):
        """Auto-set organization from user"""
        if not self.organization_id and self.user_id:
            self.organization = self.user.get_organization()
        super().save(*args, **kwargs)


class PasswordResetToken(models.Model):
    """Store password reset tokens"""
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    token = models.CharField(max_length=100, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    is_used = models.BooleanField(default=False)
    
    def is_valid(self):
        return not self.is_used and timezone.now() < self.expires_at


class EmailVerificationToken(models.Model):
    """Store email verification tokens"""
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    token = models.CharField(max_length=100, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    is_used = models.BooleanField(default=False)
    
    def is_valid(self):
        return not self.is_used and timezone.now() < self.expires_at


# Import hierarchy models at the end to avoid circular import issues
# This ensures they're registered with Django
from .models_hierarchy import OrganizationUser, Branch, BranchUser

# Make all models available when importing from this module
__all__ = [
    'User', 'UserManager', 'UserSession', 'PasswordResetToken', 
    'EmailVerificationToken', 'OrganizationUser', 'Branch', 'BranchUser'
]
