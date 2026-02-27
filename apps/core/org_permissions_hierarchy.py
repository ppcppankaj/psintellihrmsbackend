"""
Organization Admin Permission System (Hierarchical Multi-Tenancy)
Grants org admins full control over their organization's data
Updated to work with OrganizationUser mapping model
"""

from rest_framework.permissions import BasePermission
from django.core.exceptions import PermissionDenied as DjangoPermissionDenied


def _get_user_org(user):
    """Helper to get user's organization via mapping model"""
    if hasattr(user, 'get_organization'):
        return user.get_organization()
    # Fallback for backward compatibility
    return getattr(user, 'organization', None)


def _is_org_admin(user):
    """Helper to check if user is org admin via mapping model"""
    if hasattr(user, 'is_organization_admin'):
        return user.is_organization_admin()
    # Fallback for backward compatibility
    return getattr(user, 'is_org_admin', False)


class IsOrgAdminOrSuperuser(BasePermission):
    """
    Permission: User must be organization admin or superuser
    - Superusers: Full access across all organizations
    - Org Admins: Full access within their organization only
    """
    
    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        
        # Superusers have full access
        if request.user.is_superuser:
            return True
        
        # Org admins have access (via mapping)
        if _is_org_admin(request.user):
            return True
        
        return False
    
    def has_object_permission(self, request, view, obj):
        if not request.user or not request.user.is_authenticated:
            return False
        
        # Superusers have full access
        if request.user.is_superuser:
            return True
        
        # Org admins can only access objects in their organization
        if _is_org_admin(request.user):
            user_org = _get_user_org(request.user)
            if not user_org:
                return False
            
            # Check if object has organization attribute
            if hasattr(obj, 'organization_id'):
                return obj.organization_id == user_org.id
            elif hasattr(obj, 'organization'):
                return obj.organization == user_org
        
        return False


class IsOrgAdminOrReadOnly(BasePermission):
    """
    Permission: Org admins can modify, others can only read
    """
    
    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        
        # Superusers have full access
        if request.user.is_superuser:
            return True
        
        # Read-only access for everyone
        if request.method in ['GET', 'HEAD', 'OPTIONS']:
            return True
        
        # Write access only for org admins
        return _is_org_admin(request.user)
    
    def has_object_permission(self, request, view, obj):
        if not request.user or not request.user.is_authenticated:
            return False
        
        # Superusers have full access
        if request.user.is_superuser:
            return True
        
        user_org = _get_user_org(request.user)
        if not user_org:
            return False
        
        # Check organization membership for object access
        if hasattr(obj, 'organization_id'):
            same_org = obj.organization_id == user_org.id
        elif hasattr(obj, 'organization'):
            same_org = obj.organization == user_org
        else:
            same_org = False
        
        # Read-only if same org
        if request.method in ['GET', 'HEAD', 'OPTIONS']:
            return same_org
        
        # Write access only for org admins in same org
        return same_org and _is_org_admin(request.user)


class IsOrgMember(BasePermission):
    """
    Permission: User must be member of the organization
    """
    
    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        
        # Superusers have full access
        if request.user.is_superuser:
            return True
        
        # Must have an organization
        return _get_user_org(request.user) is not None
    
    def has_object_permission(self, request, view, obj):
        if not request.user or not request.user.is_authenticated:
            return False
        
        # Superusers have full access
        if request.user.is_superuser:
            return True
        
        user_org = _get_user_org(request.user)
        if not user_org:
            return False
        
        # Check organization membership
        if hasattr(obj, 'organization_id'):
            return obj.organization_id == user_org.id
        elif hasattr(obj, 'organization'):
            return obj.organization == user_org
        
        return False


# =============================================================================
# DJANGO ADMIN MIXINS
# =============================================================================

class OrgAdminMixin:
    """
    Mixin for Django admin to enforce organization-level permissions
    Updated to work with OrganizationUser mapping model
    - Superusers see all data
    - Org admins see only their organization's data
    - Regular users cannot access admin
    """
    
    def has_module_permission(self, request):
        """Control access to admin module"""
        if not request.user.is_authenticated:
            return False
        
        # Superusers have full access
        if request.user.is_superuser:
            return True
        
        # Org admins need is_staff to access admin
        if _is_org_admin(request.user) and request.user.is_staff:
            return True
        
        return False
    
    def has_add_permission(self, request):
        """Control add permission"""
        if not request.user.is_authenticated:
            return False
        
        # Superusers have full access
        if request.user.is_superuser:
            return True
        
        # Org admins can add objects
        if _is_org_admin(request.user) and request.user.is_staff:
            return True
        
        return False
    
    def has_change_permission(self, request, obj=None):
        """Control change permission"""
        if not request.user.is_authenticated:
            return False
        
        # Superusers have full access
        if request.user.is_superuser:
            return True
        
        # Org admins can change objects in their organization
        if _is_org_admin(request.user) and request.user.is_staff:
            if obj is None:
                return True
            
            user_org = _get_user_org(request.user)
            if not user_org:
                return False
            
            # Check organization membership
            if hasattr(obj, 'organization_id'):
                return obj.organization_id == user_org.id
            elif hasattr(obj, 'organization'):
                return obj.organization == user_org
        
        return False
    
    def has_delete_permission(self, request, obj=None):
        """Control delete permission"""
        if not request.user.is_authenticated:
            return False
        
        # Superusers have full access
        if request.user.is_superuser:
            return True
        
        # Org admins can delete objects in their organization
        if _is_org_admin(request.user) and request.user.is_staff:
            if obj is None:
                return True
            
            user_org = _get_user_org(request.user)
            if not user_org:
                return False
            
            # Check organization membership
            if hasattr(obj, 'organization_id'):
                return obj.organization_id == user_org.id
            elif hasattr(obj, 'organization'):
                return obj.organization == user_org
        
        return False
    
    def has_view_permission(self, request, obj=None):
        """Control view permission"""
        if not request.user.is_authenticated:
            return False
        
        # Superusers have full access
        if request.user.is_superuser:
            return True
        
        # Org admins can view objects in their organization
        if _is_org_admin(request.user) and request.user.is_staff:
            if obj is None:
                return True
            
            user_org = _get_user_org(request.user)
            if not user_org:
                return False
            
            # Check organization membership
            if hasattr(obj, 'organization_id'):
                return obj.organization_id == user_org.id
            elif hasattr(obj, 'organization'):
                return obj.organization == user_org
        
        return False
    
    def get_queryset(self, request):
        """Filter queryset by organization (via mapping model)"""
        qs = super().get_queryset(request)
        
        # Superusers see all data
        if request.user.is_superuser:
            return qs
        
        # Org admins see only their organization's data
        if _is_org_admin(request.user) and request.user.is_staff:
            user_org = _get_user_org(request.user)
            if not user_org:
                return qs.none()
            
            if hasattr(qs.model, 'organization'):
                return qs.filter(organization=user_org)
            elif hasattr(qs.model, 'organization_id'):
                return qs.filter(organization_id=user_org.id)
        
        return qs.none()
    
    def save_model(self, request, obj, form, change):
        """Auto-assign organization when creating objects"""
        if not change:  # New object being created
            user_org = _get_user_org(request.user)
            
            # For User model specifically: handle organization via mapping
            # (OrganizationUser will be created separately)
            if obj.__class__.__name__ == 'User':
                # Skip auto-assignment for User model
                # Organization will be set via OrganizationUser inline
                pass
            elif hasattr(obj, 'organization') and not obj.organization_id:
                # For other models: auto-assign to requesting user's org
                if not request.user.is_superuser:
                    if user_org:
                        obj.organization = user_org
        
        super().save_model(request, obj, form, change)
    
    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        """Filter foreign key choices by organization"""
        # Skip for superusers
        if not request.user.is_superuser:
            if _is_org_admin(request.user) and request.user.is_staff:
                user_org = _get_user_org(request.user)
                if user_org:
                    # Filter organization-scoped foreign keys
                    if hasattr(db_field.remote_field.model, 'organization'):
                        kwargs["queryset"] = db_field.remote_field.model.objects.filter(
                            organization=user_org
                        )
        
        return super().formfield_for_foreignkey(db_field, request, **kwargs)


# =============================================================================
# DECORATOR FOR FUNCTION-BASED VIEWS
# =============================================================================

def org_admin_required(view_func):
    """
    Decorator to require org admin or superuser access
    Usage:
        @org_admin_required
        def my_view(request):
            ...
    """
    from functools import wraps
    
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            raise DjangoPermissionDenied("Authentication required")
        
        if request.user.is_superuser or _is_org_admin(request.user):
            return view_func(request, *args, **kwargs)
        
        raise DjangoPermissionDenied("Organization admin access required")
    
    return wrapper


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def check_org_admin(user):
    """Check if user is org admin or superuser (via mapping)"""
    if not user or not user.is_authenticated:
        return False
    return user.is_superuser or _is_org_admin(user)


def check_same_organization(user, obj):
    """Check if object belongs to user's organization (via mapping)"""
    if not user or not user.is_authenticated:
        return False
    
    if user.is_superuser:
        return True
    
    user_org = _get_user_org(user)
    if not user_org:
        return False
    
    if hasattr(obj, 'organization_id'):
        return obj.organization_id == user_org.id
    elif hasattr(obj, 'organization'):
        return obj.organization == user_org
    
    return False
