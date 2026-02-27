"""Authentication permissions."""
from rest_framework.permissions import BasePermission


class IsSameOrganization(BasePermission):
    """Prevent cross-tenant access for authenticated users."""

    message = 'Cross-tenant access denied'

    def has_permission(self, request, view):
        user = getattr(request, 'user', None)
        if not user or not user.is_authenticated:
            return False
        if user.is_superuser:
            return True
        return bool(getattr(request, 'organization', None))

    def has_object_permission(self, request, view, obj):
        if not self.has_permission(request, view):
            return False
        if request.user.is_superuser:
            return True

        request_org = getattr(request, 'organization', None)
        if not request_org:
            return False

        obj_org_id = self._resolve_org_id(obj)
        if obj_org_id is None:
            return False

        return str(obj_org_id) == str(request_org.id)

    def _resolve_org_id(self, obj):
        """Best-effort extraction of organization identifier from an object."""
        if hasattr(obj, 'organization_id') and getattr(obj, 'organization_id'):
            return getattr(obj, 'organization_id')

        organization = getattr(obj, 'organization', None)
        if organization and hasattr(organization, 'id'):
            return organization.id

        branch = getattr(obj, 'branch', None)
        if branch and hasattr(branch, 'organization_id'):
            return branch.organization_id

        if hasattr(obj, 'user'):
            user_org = obj.user.get_organization() if hasattr(obj.user, 'get_organization') else None
            if user_org:
                return user_org.id

        if hasattr(obj, 'get_organization'):
            resolved_org = obj.get_organization()
            if resolved_org:
                return resolved_org.id

        return None
