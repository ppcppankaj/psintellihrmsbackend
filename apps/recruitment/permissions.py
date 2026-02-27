"""Recruitment app permissions."""
from rest_framework.permissions import BasePermission, SAFE_METHODS


class RecruitmentTenantPermission(BasePermission):
    """Organization-scoped access for recruitment."""

    message = 'Organization context required for recruitment operations.'

    def has_permission(self, request, view):
        return bool(
            request.user
            and request.user.is_authenticated
            and getattr(request, 'organization', None)
        )

    def has_object_permission(self, request, view, obj):
        organization = getattr(request, 'organization', None)
        if not organization:
            return False
        obj_org = getattr(obj, 'organization_id', None)
        return obj_org is None or obj_org == organization.id


class CanManageRecruitment(BasePermission):
    """HR and hiring managers can manage recruitment."""

    def has_permission(self, request, view):
        user = request.user
        if not user or not user.is_authenticated:
            return False
        if user.is_superuser:
            return True
        if request.method in SAFE_METHODS:
            return user.has_permission_for('recruitment.view')
        return user.has_permission_for('recruitment.manage')


class CanManageInterviews(BasePermission):
    """Interviewers can manage their assigned interviews."""

    def has_object_permission(self, request, view, obj):
        user = request.user
        if user.is_superuser:
            return True
        if user.has_permission_for('recruitment.manage'):
            return True
        if hasattr(obj, 'interviewers') and obj.interviewers.filter(user=user).exists():
            return True
        return False
