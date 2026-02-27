"""
Branch-aware DRF permissions and query filtering.
"""

from django.db.models import Q
from rest_framework import permissions
from rest_framework.filters import BaseFilterBackend


def _get_cached_user_branches(user):
    """Resolve branch memberships once per-request user object."""
    if hasattr(user, "_cached_branch_objects"):
        return user._cached_branch_objects

    branches = []
    try:
        from apps.authentication.models_hierarchy import BranchUser

        memberships = BranchUser.objects.filter(
            user=user,
            is_active=True,
        ).select_related("branch")
        branches = [membership.branch for membership in memberships]
    except Exception:
        branches = []

    if not branches:
        try:
            from apps.employees.models import Employee

            employee = Employee.objects.filter(user=user, is_active=True).select_related("branch").first()
            if employee and employee.branch:
                branches = [employee.branch]
        except Exception:
            branches = []

    user._cached_branch_objects = branches
    user._cached_branch_ids = [branch.id for branch in branches]
    return branches


def _get_cached_user_branch_ids(user):
    if hasattr(user, "_cached_branch_ids"):
        return user._cached_branch_ids
    _get_cached_user_branches(user)
    return getattr(user, "_cached_branch_ids", [])


class BranchPermission(permissions.BasePermission):
    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        if request.user.is_superuser:
            return True
        return request.user.get_organization() is not None

    def has_object_permission(self, request, view, obj):
        if request.user.is_superuser:
            return True
        if not hasattr(obj, "branch"):
            return True
        if obj.branch is None:
            return True

        user_org = request.user.get_organization()
        if not user_org:
            return False

        if request.user.is_org_admin or request.user.is_organization_admin():
            return obj.branch.organization == user_org

        return obj.branch in _get_cached_user_branches(request.user)


class OrganizationPermission(permissions.BasePermission):
    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        if request.user.is_superuser:
            return True
        return request.user.get_organization() is not None

    def has_object_permission(self, request, view, obj):
        if request.user.is_superuser:
            return True
        if not hasattr(obj, "organization"):
            return True
        if obj.organization is None:
            return True

        user_org = request.user.get_organization()
        if not user_org:
            return False
        return obj.organization == user_org


class BranchFilterBackend(BaseFilterBackend):
    def filter_queryset(self, request, queryset, view):
        if request.user.is_superuser:
            return queryset

        user_org = request.user.get_organization()
        if not user_org:
            return queryset.none()

        model = queryset.model
        has_branch_field = hasattr(model, "branch")

        if not has_branch_field:
            if hasattr(model, "organization"):
                return queryset.filter(organization=user_org)
            return queryset

        if request.user.is_org_admin or request.user.is_organization_admin():
            return queryset.filter(Q(branch__organization=user_org) | Q(branch__isnull=True))

        branch_ids = _get_cached_user_branch_ids(request.user)
        if branch_ids:
            return queryset.filter(Q(branch__id__in=branch_ids) | Q(branch__isnull=True))

        return queryset.filter(branch__isnull=True)


class OrganizationFilterBackend(BaseFilterBackend):
    def filter_queryset(self, request, queryset, view):
        if request.user.is_superuser:
            return queryset

        user_org = request.user.get_organization()
        if not user_org:
            return queryset.none()

        if hasattr(queryset.model, "organization"):
            return queryset.filter(organization=user_org)
        return queryset


class IsBranchAdmin(permissions.BasePermission):
    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        if request.user.is_superuser:
            return True
        if request.user.is_org_admin or request.user.is_organization_admin():
            return True

        try:
            from apps.authentication.models_hierarchy import BranchUser

            return BranchUser.objects.filter(
                user=request.user,
                is_active=True,
                role=BranchUser.RoleChoices.BRANCH_ADMIN,
            ).exists()
        except Exception:
            return False


class IsSelfOrBranchAdmin(permissions.BasePermission):
    def has_object_permission(self, request, view, obj):
        if request.user.is_superuser:
            return True

        if hasattr(obj, "user") and obj.user == request.user:
            return True
        if hasattr(obj, "employee") and hasattr(obj.employee, "user") and obj.employee.user == request.user:
            return True

        if request.user.is_org_admin or request.user.is_organization_admin():
            return True

        try:
            from apps.authentication.models_hierarchy import BranchUser

            is_branch_admin = BranchUser.objects.filter(
                user=request.user,
                is_active=True,
                role=BranchUser.RoleChoices.BRANCH_ADMIN,
            ).exists()
            if not is_branch_admin:
                return False

            if hasattr(obj, "branch") and obj.branch:
                return obj.branch.id in _get_cached_user_branch_ids(request.user)
            return False
        except Exception:
            return False
