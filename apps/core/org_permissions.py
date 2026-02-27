"""
Organization Admin Permission System
Grants org admins full control over their organization's data
"""

from rest_framework.permissions import BasePermission
from django.core.exceptions import PermissionDenied as DjangoPermissionDenied


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
        
        # Org admins have access
        if request.user.is_org_admin:
            return True
        
        return False
    
    def has_object_permission(self, request, view, obj):
        if not request.user or not request.user.is_authenticated:
            return False
        
        # Superusers have full access
        if request.user.is_superuser:
            return True
        
        # Org admins can only access objects in their organization
        if request.user.is_org_admin:
            # Check if object has organization attribute
            if hasattr(obj, 'organization_id'):
                return obj.organization_id == request.user.organization_id
            elif hasattr(obj, 'organization'):
                return obj.organization == request.user.organization
        
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
        return request.user.is_org_admin
    
    def has_object_permission(self, request, view, obj):
        if not request.user or not request.user.is_authenticated:
            return False
        
        # Superusers have full access
        if request.user.is_superuser:
            return True
        
        # Check organization membership for object access
        if hasattr(obj, 'organization_id'):
            same_org = obj.organization_id == request.user.organization_id
        elif hasattr(obj, 'organization'):
            same_org = obj.organization == request.user.organization
        else:
            same_org = False
        
        # Read-only if same org
        if request.method in ['GET', 'HEAD', 'OPTIONS']:
            return same_org
        
        # Write access only for org admins in same org
        return same_org and request.user.is_org_admin


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
        return request.user.organization_id is not None
    
    def has_object_permission(self, request, view, obj):
        if not request.user or not request.user.is_authenticated:
            return False
        
        # Superusers have full access
        if request.user.is_superuser:
            return True
        
        # Check organization membership
        if hasattr(obj, 'organization_id'):
            return obj.organization_id == request.user.organization_id
        elif hasattr(obj, 'organization'):
            return obj.organization == request.user.organization
        
        return False


# =============================================================================
# DJANGO ADMIN MIXINS
# =============================================================================

class OrgAdminMixin:
    """
    Mixin for Django admin to enforce organization-level permissions
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
        if request.user.is_org_admin and request.user.is_staff:
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
        if request.user.is_org_admin and request.user.is_staff:
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
        if request.user.is_org_admin and request.user.is_staff:
            if obj is None:
                return True
            
            # Check organization membership
            if hasattr(obj, 'organization_id'):
                return obj.organization_id == request.user.organization_id
            elif hasattr(obj, 'organization'):
                return obj.organization == request.user.organization
        
        return False
    
    def has_delete_permission(self, request, obj=None):
        """Control delete permission"""
        if not request.user.is_authenticated:
            return False
        
        # Superusers have full access
        if request.user.is_superuser:
            return True
        
        # Org admins can delete objects in their organization
        if request.user.is_org_admin and request.user.is_staff:
            if obj is None:
                return True
            
            # Check organization membership
            if hasattr(obj, 'organization_id'):
                return obj.organization_id == request.user.organization_id
            elif hasattr(obj, 'organization'):
                return obj.organization == request.user.organization
        
        return False
    
    def has_view_permission(self, request, obj=None):
        """Control view permission"""
        if not request.user.is_authenticated:
            return False
        
        # Superusers have full access
        if request.user.is_superuser:
            return True
        
        # Org admins can view objects in their organization
        if request.user.is_org_admin and request.user.is_staff:
            if obj is None:
                return True
            
            # Check organization membership
            if hasattr(obj, 'organization_id'):
                return obj.organization_id == request.user.organization_id
            elif hasattr(obj, 'organization'):
                return obj.organization == request.user.organization
        
        return False
    
    def get_queryset(self, request):
        """Filter queryset by organization"""
        qs = super().get_queryset(request)
        
        # Superusers see all data
        if request.user.is_superuser:
            return qs
        
        # Org admins see only their organization's data
        if request.user.is_org_admin and request.user.is_staff:
            if hasattr(qs.model, 'organization'):
                return qs.filter(organization=request.user.organization)
            elif hasattr(qs.model, 'organization_id'):
                return qs.filter(organization_id=request.user.organization_id)
        
        return qs.none()
    
    def save_model(self, request, obj, form, change):
        """Auto-assign organization when creating objects"""
        if not change:  # New object being created
            # For User model specifically: auto-assign organization
            if hasattr(obj, 'organization') and obj.__class__.__name__ == 'User':
                if not obj.organization_id:
                    if request.user.is_superuser:
                        # Superuser can assign any organization
                        # If not specified in form, use their org (if they have one)
                        if not obj.organization_id:
                            obj.organization = request.user.organization
                    else:
                        # Org admin always gets their own organization
                        obj.organization = request.user.organization
            elif hasattr(obj, 'organization') and not obj.organization_id:
                # For other models: auto-assign to requesting user's org
                if not request.user.is_superuser:
                    obj.organization = request.user.organization
        
        super().save_model(request, obj, form, change)
    
    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        """Filter foreign key choices by organization"""
        # Skip for superusers
        if not request.user.is_superuser:
            if request.user.is_org_admin and request.user.is_staff:
                # Filter organization-scoped foreign keys
                if hasattr(db_field.remote_field.model, 'organization'):
                    kwargs["queryset"] = db_field.remote_field.model.objects.filter(
                        organization=request.user.organization
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
        
        if request.user.is_superuser or request.user.is_org_admin:
            return view_func(request, *args, **kwargs)
        
        raise DjangoPermissionDenied("Organization admin access required")
    
    return wrapper


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def check_org_admin(user):
    """Check if user is org admin or superuser"""
    if not user or not user.is_authenticated:
        return False
    return user.is_superuser or user.is_org_admin


def check_same_organization(user, obj):
    """Check if object belongs to user's organization"""
    if not user or not user.is_authenticated:
        return False
    
    if user.is_superuser:
        return True
    
    if hasattr(obj, 'organization_id'):
        return obj.organization_id == user.organization_id
    elif hasattr(obj, 'organization'):
        return obj.organization == user.organization
    
    return False
