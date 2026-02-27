"""
ABAC Permissions - Custom DRF permissions using Attribute-Based Access Control
SECURITY:
- Enforces mandatory organization context
- Prevents silent ABAC execution outside tenant boundary
"""

from rest_framework.permissions import BasePermission
from rest_framework.exceptions import PermissionDenied, NotAuthenticated
from apps.core.context import get_current_organization
from .services import ABACService


class IsPolicyOrgAdmin(BasePermission):
    """Allow only org admins (or superusers) to manage ABAC resources."""

    message = 'Organization admin privileges required.'

    def has_permission(self, request, view):
        user = getattr(request, 'user', None)
        if not user or not user.is_authenticated:
            return False
        if user.is_superuser:
            return True

        org = getattr(request, 'organization', None) or get_current_organization()
        if not org:
            return False

        user_org = user.get_organization() if hasattr(user, 'get_organization') else None
        if not user_org or str(user_org.id) != str(org.id):
            return False

        if hasattr(user, 'is_organization_admin') and user.is_organization_admin():
            return True

        return bool(getattr(user, 'is_org_admin', False))


class HasABACPermission(BasePermission):
    """
    Base ABAC permission class.
    Checks access based on policies using the PolicyEngine.
    """

    def __init__(self, resource_type=None, action_map=None):
        """
        Args:
            resource_type: Type of resource (e.g., 'employee', 'payroll')
            action_map: Mapping of HTTP methods to ABAC actions
        """
        self.resource_type = resource_type
        self.action_map = action_map or {
            'GET': 'view',
            'POST': 'create',
            'PUT': 'update',
            'PATCH': 'update',
            'DELETE': 'delete',
        }

    # ------------------------
    # GLOBAL PERMISSION CHECK
    # ------------------------
    def has_permission(self, request, view):
        if not request.user.is_authenticated:
            raise NotAuthenticated()

        # Superusers bypass ABAC entirely
        if request.user.is_superuser:
            return True

        # 🔒 CRITICAL: ABAC MUST have organization context
        if not get_current_organization():
            raise PermissionDenied(
                "ABAC denied: Organization context missing"
            )

        # Determine resource type
        resource_type = self.resource_type or getattr(view, 'abac_resource_type', None)
        if not resource_type:
            resource_type = self._infer_resource_type(view)

        # Determine action
        action = self.action_map.get(request.method, 'view')
        if hasattr(view, 'action'):
            action = getattr(view, 'abac_action', view.action)

        decision = ABACService.evaluate_access(
            user=request.user,
            resource_type=resource_type,
            resource_id=None,
            action=action,
            resource_attributes=None,
        )
        return decision.allowed

    # ------------------------
    # OBJECT-LEVEL PERMISSION
    # ------------------------
    def has_object_permission(self, request, view, obj):
        if not request.user.is_authenticated:
            raise NotAuthenticated()

        if request.user.is_superuser:
            return True

        # 🔒 CRITICAL: ABAC MUST have organization context
        if not get_current_organization():
            raise PermissionDenied(
                "ABAC denied: Organization context missing"
            )

        resource_type = self.resource_type or getattr(view, 'abac_resource_type', None)
        if not resource_type:
            resource_type = self._infer_resource_type(view)

        action = self.action_map.get(request.method, 'view')
        if hasattr(view, 'action'):
            action = getattr(view, 'abac_action', view.action)

        resource_attrs = self._extract_resource_attributes(obj)
        resource_id = str(obj.id) if hasattr(obj, 'id') else None

        decision = ABACService.evaluate_access(
            user=request.user,
            resource_type=resource_type,
            resource_id=resource_id,
            action=action,
            resource_attributes=resource_attrs,
        )
        return decision.allowed

    # ------------------------
    # HELPERS
    # ------------------------
    def _infer_resource_type(self, view):
        """
        Infer resource type from view class name.
        Example: EmployeeViewSet → employee
        """
        return (
            view.__class__.__name__
            .replace('ViewSet', '')
            .replace('View', '')
            .lower()
        )

    def _extract_resource_attributes(self, obj):
        """
        Extract resource attributes for ABAC evaluation.
        """
        attrs = {
            'id': str(obj.id) if hasattr(obj, 'id') else None
        }

        if hasattr(obj, 'department'):
            attrs['department'] = obj.department.name if obj.department else None
            attrs['department_id'] = str(obj.department.id) if obj.department else None

        if hasattr(obj, 'location'):
            attrs['location'] = obj.location.name if obj.location else None
            attrs['location_id'] = str(obj.location.id) if obj.location else None

        if hasattr(obj, 'owner') or hasattr(obj, 'user') or hasattr(obj, 'created_by'):
            owner = (
                getattr(obj, 'owner', None)
                or getattr(obj, 'user', None)
                or getattr(obj, 'created_by', None)
            )
            attrs['owner_id'] = str(owner.id) if owner else None

        if hasattr(obj, 'confidential'):
            attrs['confidential'] = obj.confidential

        if hasattr(obj, 'status'):
            attrs['status'] = obj.status

        return attrs


# --------------------------------------------------
# SIMPLE PERMISSION ALIAS
# --------------------------------------------------
class ABACPermission(HasABACPermission):
    """
    Default ABAC permission.
    Usage:
        permission_classes = [ABACPermission]
    """
    pass


# --------------------------------------------------
# SPECIALIZED PERMISSIONS
# --------------------------------------------------
class DepartmentABACPermission(HasABACPermission):
    """
    Requires user to be in same department as resource.
    """

    def has_object_permission(self, request, view, obj):
        if not super().has_object_permission(request, view, obj):
            return False

        if hasattr(obj, 'department') and hasattr(request.user, 'employee'):
            emp = request.user.employee
            return emp and emp.department == obj.department

        return False


class ManagerABACPermission(HasABACPermission):
    """
    Requires user to be a manager.
    """

    def has_permission(self, request, view):
        if not request.user.is_authenticated:
            raise NotAuthenticated()

        if request.user.is_superuser:
            return True

        if hasattr(request.user, 'employee'):
            if not getattr(request.user.employee, 'is_manager', False):
                return False

        return super().has_permission(request, view)


class OwnerOrABACPermission(HasABACPermission):
    """
    Allows resource owners or ABAC-approved users.
    """

    def has_object_permission(self, request, view, obj):
        if not request.user.is_authenticated:
            raise NotAuthenticated()

        if request.user.is_superuser:
            return True

        owner = (
            getattr(obj, 'user', None)
            or getattr(obj, 'owner', None)
            or getattr(obj, 'created_by', None)
        )

        if owner and owner == request.user:
            return True

        return super().has_object_permission(request, view, obj)


# --------------------------------------------------
# LEGACY COMPATIBILITY PERMISSIONS
# --------------------------------------------------
class IsHRAdmin(HasABACPermission):
    """Legacy HR admin permission"""

    def __init__(self):
        super().__init__(
            resource_type='hr_module',
            action_map={
                'GET': 'admin',
                'POST': 'admin',
                'PUT': 'admin',
                'PATCH': 'admin',
                'DELETE': 'admin',
            }
        )


class IsCompanyOwner(HasABACPermission):
    """Legacy company owner permission"""

    def __init__(self):
        super().__init__(
            resource_type='company',
            action_map={
                'GET': 'owner',
                'POST': 'owner',
                'PUT': 'owner',
                'PATCH': 'owner',
                'DELETE': 'owner',
            }
        )


class IsManager(ManagerABACPermission):
    """Legacy alias"""
    pass


# --------------------------------------------------
# FUNCTION DECORATOR (VIEWS / FUNCTIONS)
# --------------------------------------------------
def abac_permission_required(resource_type, action):
    """
    Decorator for ABAC permission enforcement on function-based views.
    """

    def decorator(func):
        def wrapper(request, *args, **kwargs):
            if not request.user.is_authenticated:
                raise NotAuthenticated()

            if request.user.is_superuser:
                return func(request, *args, **kwargs)

            if not get_current_organization():
                raise PermissionDenied(
                    "ABAC denied: Organization context missing"
                )

            decision = ABACService.evaluate_access(
                user=request.user,
                resource_type=resource_type,
                resource_id=None,
                action=action,
            )
            if not decision.allowed:
                raise PermissionDenied(
                    f"You do not have permission to {action} {resource_type}"
                )

            return func(request, *args, **kwargs)

        return wrapper

    return decorator
