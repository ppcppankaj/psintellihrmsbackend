"""
Hierarchical Multi-Tenancy Admin
Supports Organization → User → Branch structure with mapping models
"""

from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.db.models import Q
from .models import User, UserSession, PasswordResetToken, EmailVerificationToken
from .models_hierarchy import OrganizationUser, Branch, BranchUser
from apps.core.admin_utils import SafeDeleteMixin
from apps.core.org_permissions import OrgAdminMixin


# ============================================================================
# ORGANIZATION-USER MAPPING ADMIN
# ============================================================================

@admin.register(OrganizationUser)
class OrganizationUserAdmin(admin.ModelAdmin):
    """Admin for OrganizationUser mapping"""
    
    list_display = ['user_email', 'user_name', 'organization', 'role', 'is_active', 'created_at']
    list_filter = ['role', 'is_active', 'organization', 'created_at']
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
        if not change:  # New record
            obj.created_by = request.user
        super().save_model(request, obj, form, change)
    
    def get_queryset(self, request):
        """Filter by organization for org admins"""
        qs = super().get_queryset(request)
        
        if request.user.is_superuser:
            return qs
        
        # Org admins can only see their organization's mappings
        user_org = request.user.get_organization()
        if user_org:
            return qs.filter(organization=user_org)
        
        return qs.none()


# ============================================================================
# BRANCH ADMIN
# ============================================================================

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
                    kwargs['queryset'] = user_org.__class__.objects.filter(id=user_org.id)
        return super().formfield_for_foreignkey(db_field, request, **kwargs)


# ============================================================================
# BRANCH-USER MAPPING ADMIN
# ============================================================================

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
        """Limit choices to user's organization"""
        if not request.user.is_superuser:
            user_org = request.user.get_organization()
            
            if db_field.name == 'branch' and user_org:
                kwargs['queryset'] = Branch.objects.filter(organization=user_org)
            
            if db_field.name == 'user' and user_org:
                # Only show users from same organization
                kwargs['queryset'] = User.objects.filter(
                    organization_memberships__organization=user_org,
                    organization_memberships__is_active=True
                )
        
        return super().formfield_for_foreignkey(db_field, request, **kwargs)


# ============================================================================
# USER ADMIN (Updated for Hierarchical Multi-Tenancy)
# ============================================================================

@admin.register(User)
class UserAdminHierarchy(OrgAdminMixin, SafeDeleteMixin, BaseUserAdmin):
    """
    User Admin with Hierarchical Multi-Tenancy support.
    Organization assignment is now done via OrganizationUser mapping model.
    """
    
    # Display organization from mapping
    def get_organization(self, obj):
        """Get organization from mapping"""
        org = obj.get_organization()
        return org.name if org else '-'
    get_organization.short_description = 'Organization'
    
    def get_is_org_admin(self, obj):
        """Check if user is org admin from mapping"""
        return obj.is_organization_admin()
    get_is_org_admin.short_description = 'Org Admin'
    get_is_org_admin.boolean = True
    
    list_display = ['email', 'full_name', 'get_organization', 'get_is_org_admin', 'employee_id', 'is_active', 'is_verified', 'last_login']
    list_filter = ['is_active', 'is_staff', 'is_superuser', 'is_verified', 'is_2fa_enabled']
    search_fields = ['email', 'first_name', 'last_name', 'employee_id', 'username']
    ordering = ['email']
    
    fieldsets = (
        (None, {'fields': ('email', 'username', 'password')}),
        ('Permissions', {'fields': ('is_active', 'is_staff', 'is_superuser', 'is_verified', 'groups', 'user_permissions')}),
        ('Personal Info', {'fields': ('first_name', 'last_name', 'middle_name', 'phone', 'avatar', 'date_of_birth', 'gender')}),
        ('Employment', {'fields': ('employee_id', 'slug')}),
        ('Security', {'fields': ('is_2fa_enabled', 'must_change_password', 'failed_login_attempts', 'locked_until')}),
        ('Preferences', {'fields': ('timezone', 'language', 'notification_preferences')}),
        ('Important dates', {'fields': ('last_login', 'date_joined', 'password_changed_at')}),
    )
    
    add_fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': ('email', 'username', 'first_name', 'last_name', 'password1', 'password2', 'is_staff', 'is_verified'),
        }),
    )
    
    readonly_fields = ['last_login', 'date_joined', 'password_changed_at']
    
    # Inline for organization assignment
    class OrganizationUserInline(admin.TabularInline):
        model = OrganizationUser
        extra = 0
        max_num = 1  # User can only belong to one organization
        fields = ['organization', 'role', 'is_active']
        readonly_fields = ['created_at']
        
        def has_add_permission(self, request, obj=None):
            """Only superusers can assign organizations"""
            return request.user.is_superuser
        
        def has_change_permission(self, request, obj=None):
            """Only superusers can change organization assignments"""
            return request.user.is_superuser
        
        def has_delete_permission(self, request, obj=None):
            """Only superusers can delete organization assignments"""
            return request.user.is_superuser
    
    # Inline for branch assignments
    class BranchUserInline(admin.TabularInline):
        model = BranchUser
        extra = 0
        fields = ['branch', 'role', 'is_active']
        readonly_fields = ['created_at']
        
        def formfield_for_foreignkey(self, db_field, request, **kwargs):
            """Filter branches by user's organization"""
            if db_field.name == 'branch':
                # Get the user being edited from the URL
                user_id = request.resolver_match.kwargs.get('object_id')
                if user_id:
                    try:
                        user = User.objects.get(pk=user_id)
                        user_org = user.get_organization()
                        if user_org:
                            kwargs['queryset'] = Branch.objects.filter(organization=user_org)
                    except User.DoesNotExist:
                        pass
            return super().formfield_for_foreignkey(db_field, request, **kwargs)
    
    inlines = [OrganizationUserInline, BranchUserInline]
    
    def get_queryset(self, request):
        """Filter users by organization for org admins"""
        qs = super().get_queryset(request)
        
        if request.user.is_superuser:
            return qs
        
        # Org admins can only see users in their organization
        user_org = request.user.get_organization()
        if user_org:
            return qs.filter(
                organization_memberships__organization=user_org,
                organization_memberships__is_active=True
            ).distinct()
        
        return qs.none()
    
    def get_readonly_fields(self, request, obj=None):
        """Lock critical fields for org admins"""
        readonly = list(super().get_readonly_fields(request, obj))
        
        # Org admins cannot change staff/superuser status
        if not request.user.is_superuser:
            readonly.extend(['is_staff', 'is_superuser', 'groups', 'user_permissions'])
        
        return readonly


# ============================================================================
# OTHER ADMINS (unchanged)
# ============================================================================

@admin.register(UserSession)
class UserSessionAdmin(admin.ModelAdmin):
    list_display = ['user', 'ip_address', 'device_type', 'browser', 'is_active', 'last_activity']
    list_filter = ['is_active', 'device_type']
    search_fields = ['user__email', 'ip_address']
    readonly_fields = ['created_at', 'last_activity']


@admin.register(PasswordResetToken)
class PasswordResetTokenAdmin(admin.ModelAdmin):
    list_display = ['user', 'created_at', 'expires_at', 'is_used']
    list_filter = ['is_used']
    search_fields = ['user__email']
    readonly_fields = ['created_at']


@admin.register(EmailVerificationToken)
class EmailVerificationTokenAdmin(admin.ModelAdmin):
    list_display = ['user', 'created_at', 'expires_at', 'is_used']
    list_filter = ['is_used']
    search_fields = ['user__email']
    readonly_fields = ['created_at']
