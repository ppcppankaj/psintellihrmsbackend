"""
Permission Decorators & Mixins - Enterprise RBAC enforcement
"""

from functools import wraps
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import BasePermission
from django.core.exceptions import PermissionDenied as DjangoPermissionDenied


# =============================================================================
# DECORATORS
# =============================================================================

def require_permission(*permission_codes):
    """
    Decorator to require specific permissions.
    
    Usage:
        @require_permission("attendance.punch_in")
        def punch_in(request):
            ...
        
        @require_permission("employees.view", "employees.edit")
        def manage_employee(request):
            ...
    """
    def decorator(view_func):
        @wraps(view_func)
        def wrapper(request, *args, **kwargs):
            user = request.user
            
            if not user.is_authenticated:
                raise PermissionDenied("Authentication required")
            
            if user.is_superuser:
                return view_func(request, *args, **kwargs)
            
            # Check all required permissions
            for code in permission_codes:
                if not user.has_permission_for(code):
                    raise PermissionDenied(f"Permission denied: {code}")
            
            return view_func(request, *args, **kwargs)
        return wrapper
    return decorator


def require_role(*role_names):
    """
    Decorator to require specific roles.
    
    Usage:
        @require_role("HR_ADMIN", "HR_MANAGER")
        def hr_dashboard(request):
            ...
    """
    def decorator(view_func):
        @wraps(view_func)
        def wrapper(request, *args, **kwargs):
            user = request.user
            
            if not user.is_authenticated:
                raise PermissionDenied("Authentication required")
            
            if user.is_superuser:
                return view_func(request, *args, **kwargs)
            
            # Check if user has any of the required roles
            for role_name in role_names:
                if user.has_role(role_name):
                    return view_func(request, *args, **kwargs)
            
            raise PermissionDenied(f"Required role: {' or '.join(role_names)}")
        return wrapper
    return decorator


def require_any_permission(*permission_codes):
    """
    Decorator to require ANY of the specified permissions.
    
    Usage:
        @require_any_permission("employees.view", "employees.view_own")
        def view_employee(request):
            ...
    """
    def decorator(view_func):
        @wraps(view_func)
        def wrapper(request, *args, **kwargs):
            user = request.user
            
            if not user.is_authenticated:
                raise PermissionDenied("Authentication required")
            
            if user.is_superuser:
                return view_func(request, *args, **kwargs)
            
            for code in permission_codes:
                if user.has_permission_for(code):
                    return view_func(request, *args, **kwargs)
            
            raise PermissionDenied("Insufficient permissions")
        return wrapper
    return decorator


# =============================================================================
# DRF PERMISSION CLASSES
# =============================================================================

class HasPermission(BasePermission):
    """
    DRF permission class for checking specific permissions.
    
    Usage in ViewSet:
        permission_classes = [HasPermission]
        required_permissions = {
            'list': ['employees.view'],
            'create': ['employees.create'],
            'update': ['employees.edit'],
            'destroy': ['employees.delete'],
        }
    """
    
    def has_permission(self, request, view):
        if not request.user.is_authenticated:
            return False
        
        if request.user.is_superuser:
            return True
        
        # Get required permissions from view
        required = getattr(view, 'required_permissions', {})
        action = getattr(view, 'action', None)
        
        if action and action in required:
            for perm in required[action]:
                if not request.user.has_permission_for(perm):
                    return False
        
        return True


class IsSuperAdmin(BasePermission):
    """
    Allows access only to superusers.
    """
    def has_permission(self, request, view):
        return bool(request.user and request.user.is_superuser)


class IsOrganizationAdmin(BasePermission):
    """Allow access to superusers or administrators of their organization."""

    def has_permission(self, request, view):
        user = request.user
        if not user or not user.is_authenticated:
            return False

        if user.is_superuser:
            return True

        return bool(getattr(user, 'is_org_admin', False) and getattr(user, 'organization_id', None))

    def has_object_permission(self, request, view, obj):
        user = request.user
        if not user or not user.is_authenticated:
            return False

        if user.is_superuser:
            return True

        if not getattr(user, 'is_org_admin', False) or not getattr(user, 'organization_id', None):
            return False

        if hasattr(obj, 'organization_id') and obj.organization_id is not None:
            return obj.organization_id == user.organization_id

        if obj.__class__.__name__ == 'Organization':
            return obj.id == user.organization_id

        return False


class HasRole(BasePermission):
    """
    DRF permission class for checking roles.
    
    Usage:
        permission_classes = [HasRole]
        required_roles = ['HR_ADMIN', 'HR_MANAGER']
    """
    
    def has_permission(self, request, view):
        if not request.user.is_authenticated:
            return False
        
        if request.user.is_superuser:
            return True
        
        required_roles = getattr(view, 'required_roles', [])
        
        for role in required_roles:
            if request.user.has_role(role):
                return True
        
        return not required_roles  # If no roles specified, allow


class IsSelfOrHasPermission(BasePermission):
    """
    Allow access to own resources or if has permission.
    
    Usage:
        permission_classes = [IsSelfOrHasPermission]
        self_permission = 'employees.view_own'
        all_permission = 'employees.view_all'
    """
    
    def has_object_permission(self, request, view, obj):
        if not request.user.is_authenticated:
            return False
        
        if request.user.is_superuser:
            return True
        
        # Check if accessing own resource
        user_id = request.user.id
        
        if hasattr(obj, 'user_id') and obj.user_id == user_id:
            return True
        if hasattr(obj, 'employee') and obj.employee.user_id == user_id:
            return True
        if hasattr(obj, 'user') and obj.user.id == user_id:
            return True
        
        # Check for "view all" permission
        all_permission = getattr(view, 'all_permission', None)
        if all_permission and request.user.has_permission_for(all_permission):
            return True
        
        return False


class IsManagerOf(BasePermission):
    """
    Check if user is manager of the target employee.
    """
    
    def has_object_permission(self, request, view, obj):
        if not request.user.is_authenticated:
            return False
        
        if request.user.is_superuser:
            return True
        
        # Get employee from object
        employee = None
        if hasattr(obj, 'employee'):
            employee = obj.employee
        elif hasattr(obj, 'user') and hasattr(obj.user, 'employee'):
            employee = obj.user.employee
        elif obj.__class__.__name__ == 'Employee':
            employee = obj
        
        if not employee:
            return False
        
        # Check if current user is manager
        if hasattr(request.user, 'employee'):
            current_employee = request.user.employee
            if employee.reporting_manager_id == current_employee.id:
                return True
            if employee.hr_manager_id == current_employee.id:
                return True
        
        return False


# =============================================================================
# VIEW MIXINS
# =============================================================================

class PermissionRequiredMixin:
    """
    Mixin for class-based views requiring permissions.
    
    Usage:
        class EmployeeViewSet(PermissionRequiredMixin, viewsets.ModelViewSet):
            permission_map = {
                'list': ['employees.view'],
                'retrieve': ['employees.view'],
                'create': ['employees.create'],
                'update': ['employees.edit'],
                'partial_update': ['employees.edit'],
                'destroy': ['employees.delete'],
            }
    """
    
    permission_map = {}
    
    def get_required_permissions(self):
        """Get permissions required for current action"""
        action = self.action
        return self.permission_map.get(action, [])
    
    def check_permissions(self, request):
        super().check_permissions(request)
        
        user = request.user
        if user.is_superuser:
            return
        
        required = self.get_required_permissions()
        for perm in required:
            if not user.has_permission_for(perm):
                raise PermissionDenied(f"Permission required: {perm}")


class FieldMaskingMixin:
    """
    Mixin to mask sensitive fields based on permissions.
    
    Usage:
        class EmployeeSerializer(FieldMaskingMixin, serializers.ModelSerializer):
            masked_fields = {
                'salary': 'payroll.view_salary',
                'pan_number': 'employees.view_sensitive',
                'aadhaar_number': 'employees.view_sensitive',
                'bank_account': 'payroll.view_bank_details',
            }
    """
    
    masked_fields = {}
    mask_char = '*'
    
    def to_representation(self, instance):
        data = super().to_representation(instance)
        
        request = self.context.get('request')
        if not request or not hasattr(request, 'user'):
            return data
        
        user = request.user
        
        # Don't mask for superusers
        if user.is_superuser:
            return data
        
        # Mask fields user doesn't have permission for
        for field_name, permission in self.masked_fields.items():
            if field_name in data and not user.has_permission_for(permission):
                value = data[field_name]
                if value:
                    if isinstance(value, str):
                        # Show last 4 chars
                        data[field_name] = self.mask_char * (len(value) - 4) + value[-4:]
                    else:
                        data[field_name] = self.mask_char * 8
        
        return data


class FilterByPermissionMixin:
    """
    Mixin to filter queryset based on user permissions.
    
    Usage:
        class EmployeeViewSet(FilterByPermissionMixin, viewsets.ModelViewSet):
            scope_field = 'department'  # or 'reporting_manager'
    """
    
    scope_field = None
    permission_category = None
    
    def get_queryset(self):
        queryset = super().get_queryset()
        
        # Guard for tests/initialization
        if not hasattr(self.request, 'user') or self.request.user is None:
            return queryset.none()

        user = self.request.user
        if user.is_superuser:
            return queryset
        
        # Determine permission category (default to basename)
        category = self.permission_category or self.basename
        
        # Special case for transitions
        if category in ['transfer', 'promotion', 'resignation']:
            category = 'employees'
            all_perm = 'employees.transitions'
            team_perm = 'employees.transitions'
        else:
            all_perm = f'{category}.view_all'
            team_perm = f'{category}.view_team'

        # Check for "view all" permission
        if user.has_permission_for(all_perm):
            return queryset
        
        # Check for "view team" permission
        if user.has_permission_for(team_perm):
            if hasattr(user, 'employee'):
                # Get team members
                team_ids = user.employee.direct_reports.values_list('id', flat=True)
                # For transfers/promotions, we might be filtering by the employee being transferred/promoted
                if self.scope_field == 'employee' or hasattr(queryset.model, 'employee'):
                    return queryset.filter(employee_id__in=list(team_ids) + [user.employee.id])
                if self.scope_field == 'self' or queryset.model.__name__ == 'Employee':
                    return queryset.filter(id__in=list(team_ids) + [user.employee.id])
                return queryset.filter(id__in=list(team_ids) + [user.employee.id])
        
        # Default: own records only
        if hasattr(user, 'employee'):
            if self.scope_field == 'employee':
                return queryset.filter(employee=user.employee)
            elif self.scope_field == 'user':
                return queryset.filter(user=user)
            elif hasattr(queryset.model, 'employee'):
                return queryset.filter(employee=user.employee)
            elif self.scope_field == 'self' or queryset.model.__name__ == 'Employee':
                return queryset.filter(id=user.employee.id)
        
        return queryset.none()
