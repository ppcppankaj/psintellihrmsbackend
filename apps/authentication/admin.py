"""
Authentication Admin
"""

from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from .models import User, UserSession, PasswordResetToken, EmailVerificationToken
from .models_hierarchy import OrganizationUser, Branch, BranchUser
from .forms import CustomUserCreationForm, CustomUserChangeForm

# from apps.core.admin_utils import SafeDeleteMixin # Commented for circularity
# from apps.core.org_permissions import OrgAdminMixin # Commented for circularity


class DummyOrgAdminMixin: pass
class DummySafeDeleteMixin: pass
OrgAdminMixin = DummyOrgAdminMixin
SafeDeleteMixin = DummySafeDeleteMixin


@admin.register(User)
class UserAdmin(OrgAdminMixin, SafeDeleteMixin, BaseUserAdmin):
    add_form = CustomUserCreationForm
    form = CustomUserChangeForm
    list_display = ['email', 'full_name', 'organization_id', 'is_org_admin', 'employee_id', 'is_active', 'is_verified', 'last_login']
    list_filter = ['organization_id', 'is_org_admin', 'is_active', 'is_staff', 'is_superuser', 'is_verified', 'is_2fa_enabled']
    search_fields = ['email', 'first_name', 'last_name', 'employee_id', 'username']
    ordering = ['organization_id', 'email']
    
    fieldsets = (
        (None, {'fields': ('email', 'username', 'password')}),
        ('Permissions', {'fields': ('is_org_admin', 'is_active', 'is_staff', 'is_superuser', 'is_verified', 'groups', 'user_permissions')}),
        ('Personal Info', {'fields': ('first_name', 'last_name', 'middle_name', 'phone', 'avatar', 'date_of_birth', 'gender')}),
        ('Employment', {'fields': ('employee_id', 'slug')}),
        ('Security', {'fields': ('is_2fa_enabled', 'must_change_password', 'failed_login_attempts', 'locked_until')}),
        ('Preferences', {'fields': ('timezone', 'language', 'notification_preferences')}),
        ('Important dates', {'fields': ('last_login', 'date_joined', 'password_changed_at')}),
    )
    
    # Fieldsets with organization field (for superusers only)
    # Organization is shown as readonly since editable=False in model
    fieldsets_with_org = (
        (None, {'fields': ('email', 'username', 'password')}),
        ('Organization', {'fields': ('organization_id',), 'classes': ('collapse',)}),
        ('Permissions', {'fields': ('is_org_admin', 'is_active', 'is_staff', 'is_superuser', 'is_verified', 'groups', 'user_permissions')}),
        ('Personal Info', {'fields': ('first_name', 'last_name', 'middle_name', 'phone', 'avatar', 'date_of_birth', 'gender')}),
        ('Employment', {'fields': ('employee_id', 'slug')}),
        ('Security', {'fields': ('is_2fa_enabled', 'must_change_password', 'failed_login_attempts', 'locked_until')}),
        ('Preferences', {'fields': ('timezone', 'language', 'notification_preferences')}),
        ('Important dates', {'fields': ('last_login', 'date_joined', 'password_changed_at')}),
    )
    
    add_fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': ('email', 'username', 'first_name', 'last_name', 'password1', 'password2', 'is_org_admin', 'is_staff', 'is_verified'),
        }),
    )
    
    readonly_fields = ['last_login', 'date_joined', 'password_changed_at']

    def get_queryset(self, request):
        """
        🔒 CRITICAL SECURITY: Filter users based on role
        - Superuser: sees ALL users
        - Org Admin: sees ONLY their organization's users via OrganizationUser mapping
        - Regular staff: should not see this view
        """
        qs = super().get_queryset(request)
        
        # Superuser can see all users
        if request.user.is_superuser:
            return qs
        
        # Org admin: see ONLY their organization's users (excluding superusers)
        if request.user.is_org_admin:
            user_org = request.user.get_organization()
            if user_org:
                return qs.filter(
                    organization_memberships__organization=user_org,
                    organization_memberships__is_active=True,
                    is_superuser=False
                ).distinct()
        
        # Default: no access
        return qs.none()

    def get_fields(self, request, obj=None):
        """
        🔒 SECURITY: Dynamically add organization field for superusers when adding users
        Since organization has editable=False, we can't put it in fieldsets directly
        """
        fields = super().get_fields(request, obj)
        
        # For superusers adding new users, include organization
        if request.user.is_superuser and obj is None:
            # Add organization after username
            fields = list(fields)
            if 'username' in fields and 'organization_id' not in fields:
                username_idx = fields.index('username')
                fields.insert(username_idx + 1, 'organization_id')
            elif 'organization_id' not in fields:
                fields.insert(0, 'organization_id')
        
        return fields
    
    def get_fieldsets(self, request, obj=None):
        """
        🔒 SECURITY: Show organization field ONLY to superusers
        - Superuser (editing): fieldsets_with_org (org is readonly)
        - Org Admin: fieldsets (excludes organization completely)
        """
        # For adding new users, use add_fieldsets (organization added via get_fields)
        if obj is None:
            return self.add_fieldsets
        
        # For editing existing users
        if request.user.is_superuser:
            return self.fieldsets_with_org
        return self.fieldsets

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        """
        🔒 SECURITY: Override to make organization field editable for superusers
        even though it has editable=False in the model
        """
        if db_field.name == 'organization_id' and request.user.is_superuser:
            # For superusers, we want to show and allow editing the organization field
            kwargs['required'] = False
            # from django import forms
            # from apps.core.models import Organization
            # return forms.ModelChoiceField(
            #     queryset=Organization.objects.all(),
            #     required=False,
            #     widget=admin.widgets.ForeignKeyRawIdWidget(db_field.remote_field, self.admin_site)
            # )
            pass # Keep it as simple UUID field for now in admin to break dependency
        return super().formfield_for_foreignkey(db_field, request, **kwargs)

    def get_form(self, request, obj=None, **kwargs):
        """
        🔒 SECURITY: Override form generation to ensure organization field
        is properly handled based on user role
        """
        form_class = super().get_form(request, obj, **kwargs)
        
        # For non-superusers (org admins), ensure organization is not in form
        # We handle this by overriding get_fields and fieldsets, but this is an extra safety layer
        return form_class

    def get_readonly_fields(self, request, obj=None):
        """
        🔒 SECURITY: Lock critical fields for org admins
        Prevents privilege escalation (organization, is_org_admin, is_staff)
        """
        readonly = list(super().get_readonly_fields(request, obj))
        
        # For superusers editing existing users, make organization readonly
        if request.user.is_superuser and obj is not None:
            if 'organization_id' not in readonly:
                readonly.append('organization_id')
            return readonly
        
        # For superusers adding new users, organization is editable (not readonly)
        if request.user.is_superuser and obj is None:
            return readonly
        
        # For org admins: lock organization and privilege escalation fields
        if 'organization_id' not in readonly:
            readonly.append('organization_id')
        if request.user.is_org_admin:
            # Allow org admins to set staff for their org users, but block superuser/org_admin
            readonly.extend(['is_superuser', 'is_org_admin'])
        
        return readonly

    def has_change_permission(self, request, obj=None):
        """
        """
        # Superuser can do anything
        if request.user.is_superuser:
            return True
        
        # No object specified - checking if they have general permission
        if obj is None:
            return request.user.is_org_admin
        
        # Org admin CANNOT edit themselves
        if obj.pk == request.user.pk:
            return False
        
        # Org admin CANNOT edit superusers
        if obj.is_superuser:
            return False
        
        # Org admin can edit users in same organization
        if request.user.is_org_admin:
            return request.user.is_in_same_organization(obj)
        
        return False

    def has_add_permission(self, request):
        """
        🔒 SECURITY: Allow org admins to create users for their organization
        """
        # Superuser and org admins can add users
        return request.user.is_superuser or request.user.is_org_admin

    def has_delete_permission(self, request, obj=None):
        """
        🔒 SECURITY: Org admins can delete users in their organization
        - Cannot delete themselves
        - Cannot delete superusers
        - Cannot delete other organization's users
        """
        # Superuser can do anything
        if request.user.is_superuser:
            return True
        
        # No object specified - checking if they have general permission
        if obj is None:
            return request.user.is_org_admin
        
        # Org admin CANNOT delete themselves
        if obj.pk == request.user.pk:
            return False
        
        # Org admin CANNOT delete superusers
        if obj.is_superuser:
            return False
        
        # Org admin can delete users in same organization
        if request.user.is_org_admin:
            return request.user.is_in_same_organization(obj)
        
        return False

    def log_addition(self, request, object, object_repr):
        """Override to disable logging for Tenant Users to avoid cross-schema FK issues"""
        pass

    def log_change(self, request, object, message):
        """Override to disable logging for Tenant Users to avoid cross-schema FK issues"""
        pass

    def log_deletion(self, request, object, object_repr):
        """Override to disable logging for Tenant Users to avoid cross-schema FK issues"""
        pass

    def _purge_tokens(self, qs):
        try:
            from rest_framework_simplejwt.token_blacklist.models import OutstandingToken, BlacklistedToken
        except Exception:
            return
        # BlacklistedToken links to OutstandingToken via FK; delete blacklisted first, then outstanding
        BlacklistedToken.objects.filter(token__user__in=qs).delete()
        OutstandingToken.objects.filter(user__in=qs).delete()

    def delete_model(self, request, obj):
        self._purge_tokens(User.objects.filter(pk=obj.pk))
        return super().delete_model(request, obj)

    def delete_queryset(self, request, queryset):
        self._purge_tokens(queryset)
        return super().delete_queryset(request, queryset)


@admin.register(UserSession)
class UserSessionAdmin(admin.ModelAdmin):
    list_display = ['user', 'device_type', 'ip_address', 'is_active', 'created_at', 'last_activity']
    list_filter = ['device_type', 'is_active', 'created_at']
    search_fields = ['user__email', 'ip_address']
    readonly_fields = ['id', 'session_key', 'created_at', 'last_activity']
    ordering = ['-last_activity']


@admin.register(PasswordResetToken)
class PasswordResetTokenAdmin(admin.ModelAdmin):
    list_display = ['user', 'created_at', 'expires_at', 'is_used']
    list_filter = ['is_used', 'created_at']
    search_fields = ['user__email']
    readonly_fields = ['id', 'token', 'created_at']


@admin.register(EmailVerificationToken)
class EmailVerificationTokenAdmin(admin.ModelAdmin):
    list_display = ['user', 'created_at', 'expires_at', 'is_used']
    list_filter = ['is_used', 'created_at']
    search_fields = ['user__email']
    readonly_fields = ['id', 'token', 'created_at']


# ============================================================================
# HIERARCHICAL MULTI-TENANCY ADMIN
# ============================================================================

@admin.register(OrganizationUser)
class OrganizationUserAdmin(admin.ModelAdmin):
    """Admin for OrganizationUser mapping"""
    
    list_display = ['user_email', 'user_name', 'organization', 'role', 'is_active', 'created_at']
    list_filter = ['role', 'is_active', 'created_at']  # Removed 'organization'
    search_fields = ['user__email', 'user__first_name', 'user__last_name', 'organization__name']
    readonly_fields = ['created_at', 'updated_at', 'created_by']
    
    fieldsets = (
        ('Assignment', {
            'fields': ('user', 'organization', 'role', 'is_active')
        }),
        ('Audit', {
            'fields': ('created_at', 'updated_at', 'created_by'),
            'classes': ('collapse',)
        }),
    )
    
    def user_email(self, obj):
        return obj.user.email
    user_email.short_description = 'Email'
    user_email.admin_order_field = 'user__email'
    
    def user_name(self, obj):
        return obj.user.full_name
    user_name.short_description = 'Name'
    user_name.admin_order_field = 'user__first_name'
    
    def save_model(self, request, obj, form, change):
        """Auto-populate created_by field"""
        if not request.user.is_superuser:
            user_org = request.user.get_organization()
            if user_org:
                obj.organization = user_org
        if not change:  # New record
            obj.created_by = request.user
        super().save_model(request, obj, form, change)
    
    def get_queryset(self, request):
        """
        CRITICAL SECURITY: Org admins can ONLY see their organization's users.
        Exclude superusers and other organizations completely.
        """
        qs = super().get_queryset(request)
        
        if request.user.is_superuser:
            return qs
        
        # Org admins: Show ONLY their organization, EXCLUDE superusers
        user_org = request.user.get_organization()
        if user_org:
            return qs.filter(
                organization=user_org,
                user__is_superuser=False  # CRITICAL: Don't show superusers
            )
        
        return qs.none()
    
    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        """
        CRITICAL SECURITY FIX: 
        1. Limit organization choices for org admins
        2. Hide superusers from user dropdown
        3. Show only users without OrganizationUser mappings (unassigned users)
        """
        if not request.user.is_superuser:
            user_org = request.user.get_organization()
            if user_org:
                # Org admin can ONLY see their own organization
                if db_field.name == 'organization':
                    from apps.core.models import Organization
                    kwargs['queryset'] = Organization.objects.filter(id=user_org.id)
                
                # Only show non-superuser, non-staff users OR users already in this organization
                if db_field.name == 'user':
                    from apps.authentication.models import User
                    # Show users that: are not superuser AND (are not yet assigned OR already in this org)
                    kwargs['queryset'] = User.objects.filter(
                        is_superuser=False,
                        is_staff=False
                    ).exclude(
                        organization_memberships__organization__isnull=False
                    ) | User.objects.filter(
                        organization_memberships__organization=user_org
                    )
        # Superusers can see all organizations and all users
        return super().formfield_for_foreignkey(db_field, request, **kwargs)


@admin.register(Branch)
class BranchAdmin(admin.ModelAdmin):
    """Admin for Branch model"""
    
    list_display = ['name', 'code', 'organization', 'city', 'is_active', 'created_at']
    list_filter = ['organization', 'is_active', 'country', 'state', 'created_at']
    search_fields = ['name', 'code', 'city', 'email', 'phone']
    readonly_fields = ['created_at', 'updated_at', 'created_by']
    
    fieldsets = (
        ('Basic Information', {
            'fields': ('organization', 'name', 'code', 'is_active')
        }),
        ('Address', {
            'fields': ('address_line1', 'address_line2', 'city', 'state', 'country', 'postal_code'),
            'classes': ('collapse',)
        }),
        ('Contact', {
            'fields': ('phone', 'email'),
            'classes': ('collapse',)
        }),
        ('Audit', {
            'fields': ('created_at', 'updated_at', 'created_by'),
            'classes': ('collapse',)
        }),
    )
    
    def save_model(self, request, obj, form, change):
        """Auto-populate created_by field"""
        if not request.user.is_superuser:
            user_org = request.user.get_organization()
            if user_org:
                obj.organization = user_org
        if not change:  # New record
            obj.created_by = request.user
        super().save_model(request, obj, form, change)
    
    def get_queryset(self, request):
        """Filter by organization for org admins"""
        qs = super().get_queryset(request)
        
        if request.user.is_superuser:
            return qs
        
        # Org admins can only see their organization's branches
        user_org = request.user.get_organization()
        if user_org:
            return qs.filter(organization=user_org)
        
        return qs.none()
    
    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        """Limit organization choices for org admins"""
        if db_field.name == 'organization':
            if not request.user.is_superuser:
                user_org = request.user.get_organization()
                if user_org:
                    from apps.core.models import Organization
                    kwargs['queryset'] = Organization.objects.filter(id=user_org.id)
        return super().formfield_for_foreignkey(db_field, request, **kwargs)


@admin.register(BranchUser)
class BranchUserAdmin(admin.ModelAdmin):
    """Admin for BranchUser mapping"""
    
    list_display = ['user_email', 'user_name', 'branch', 'role', 'is_active', 'created_at']
    list_filter = ['role', 'is_active', 'branch__organization', 'created_at']
    search_fields = ['user__email', 'user__first_name', 'user__last_name', 'branch__name']
    readonly_fields = ['created_at', 'updated_at', 'created_by']
    
    fieldsets = (
        ('Assignment', {
            'fields': ('user', 'branch', 'role', 'is_active')
        }),
        ('Audit', {
            'fields': ('created_at', 'updated_at', 'created_by'),
            'classes': ('collapse',)
        }),
    )
    
    def user_email(self, obj):
        return obj.user.email
    user_email.short_description = 'Email'
    user_email.admin_order_field = 'user__email'
    
    def user_name(self, obj):
        return obj.user.full_name
    user_name.short_description = 'Name'
    user_name.admin_order_field = 'user__first_name'
    
    def save_model(self, request, obj, form, change):
        """Auto-populate created_by field"""
        if not change:  # New record
            obj.created_by = request.user
        super().save_model(request, obj, form, change)
    
    def get_queryset(self, request):
        """Filter by organization for org admins"""
        qs = super().get_queryset(request)
        
        if request.user.is_superuser:
            return qs
        
        # Org admins can only see their organization's branch assignments
        user_org = request.user.get_organization()
        if user_org:
            return qs.filter(branch__organization=user_org)
        
        return qs.none()
    
    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        """
        Cascading dropdowns for BranchUser creation:
        1. Organization (pre-filled for org admins)
        2. Branch (filtered by organization)
        3. User (filtered by organization and branch)
        """
        if not request.user.is_superuser:
            user_org = request.user.get_organization()
            if not user_org:
                return super().formfield_for_foreignkey(db_field, request, **kwargs)
            
            # Step 1: Branch - Filter to user's organization only
            if db_field.name == 'branch':
                kwargs['queryset'] = Branch.objects.filter(organization=user_org)
            
            # Step 2: User - Show only users from same organization
            elif db_field.name == 'user':
                kwargs['queryset'] = User.objects.filter(
                    organization_memberships__organization=user_org,
                    organization_memberships__is_active=True
                ).distinct()
        
        return super().formfield_for_foreignkey(db_field, request, **kwargs)
