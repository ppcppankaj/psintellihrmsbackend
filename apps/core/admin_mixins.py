"""
Admin Mixins for Multi-Tenancy Support
"""

from django.contrib import admin
from django.db.models import Q


class BranchAwareAdminMixin:
    """
    Mixin for ModelAdmin classes to implement branch-level data isolation.
    
    Access Control:
    - Superusers: See all data across all organizations and branches
    - Org Admins: See all data within their organization (all branches)
    - Branch Admins/Users: See only data from their assigned branch(es)
    
    Usage:
        class MyModelAdmin(BranchAwareAdminMixin, admin.ModelAdmin):
            pass
    """
    
    def get_queryset(self, request):
        """Filter queryset based on user's branch/organization access"""
        qs = super().get_queryset(request)
        
        # Superusers see everything
        if request.user.is_superuser:
            return qs
        
        # Get user's organization
        user_org = request.user.get_organization()
        if not user_org:
            return qs.none()  # No access if no organization
        
        # Check if model has branch field
        model = self.model
        has_branch_field = hasattr(model, 'branch')
        
        if not has_branch_field:
            # If no branch field, filter by organization only
            if hasattr(model, 'organization'):
                return qs.filter(organization=user_org)
            return qs  # No tenant fields, return all
        
        # Model has branch field - apply branch filtering
        
        # Org admins see all branches in their organization
        if request.user.is_org_admin or request.user.is_organization_admin():
            return qs.filter(
                Q(branch__organization=user_org) | Q(branch__isnull=True)
            )
        
        # Regular users see only their branch(es)
        user_branches = self._get_user_branches(request.user)
        if user_branches:
            return qs.filter(
                Q(branch__in=user_branches) | Q(branch__isnull=True)
            )
        
        # No branch access
        return qs.filter(branch__isnull=True)
    
    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        """Limit branch choices based on user's organization"""
        
        # Limit branch choices to user's organization
        if db_field.name == "branch":
            if not request.user.is_superuser:
                user_org = request.user.get_organization()
                if user_org:
                    from apps.authentication.models import Branch
                    kwargs["queryset"] = Branch.objects.filter(
                        organization=user_org,
                        is_active=True
                    )
        
        # Limit organization choices (for superuser only)
        if db_field.name == "organization":
            if not request.user.is_superuser:
                user_org = request.user.get_organization()
                if user_org:
                    from apps.core.models import Organization
                    kwargs["queryset"] = Organization.objects.filter(id=user_org.id)
        
        return super().formfield_for_foreignkey(db_field, request, **kwargs)
    
    def _get_user_branches(self, user):
        """
        Get all branches assigned to the user.
        Returns QuerySet of Branch objects.
        """
        try:
            from apps.authentication.models import BranchUser
            branch_memberships = BranchUser.objects.filter(
                user=user,
                is_active=True
            ).select_related('branch')
            return [membership.branch for membership in branch_memberships]
        except:
            # Fallback: check if Employee model has branch
            try:
                from apps.employees.models import Employee
                employee = Employee.objects.filter(user=user, is_active=True).first()
                if employee and employee.branch:
                    return [employee.branch]
            except:
                pass
        return []
    
    def has_view_permission(self, request, obj=None):
        """Check if user can view the object"""
        if not super().has_view_permission(request, obj):
            return False
        
        if obj is None:
            return True
        
        # Superusers can view everything
        if request.user.is_superuser:
            return True
        
        # Check branch-level access
        if hasattr(obj, 'branch') and obj.branch:
            user_org = request.user.get_organization()
            
            # Org admins can view all branches in their org
            if request.user.is_org_admin or request.user.is_organization_admin():
                return obj.branch.organization == user_org
            
            # Regular users can only view their branches
            user_branches = self._get_user_branches(request.user)
            return obj.branch in user_branches
        
        return True
    
    def has_change_permission(self, request, obj=None):
        """Check if user can change the object"""
        if not super().has_change_permission(request, obj):
            return False
        
        if obj is None:
            return True
        
        # Use same logic as view permission
        return self.has_view_permission(request, obj)
    
    def has_delete_permission(self, request, obj=None):
        """Check if user can delete the object"""
        if not super().has_delete_permission(request, obj):
            return False
        
        if obj is None:
            return True
        
        # Use same logic as view permission
        return self.has_view_permission(request, obj)


class OrganizationAwareAdminMixin:
    """
    Mixin for ModelAdmin classes to implement organization-level data isolation.
    
    For models that have organization field but no branch field.
    
    Usage:
        class MyModelAdmin(OrganizationAwareAdminMixin, admin.ModelAdmin):
            pass
    """
    
    def get_queryset(self, request):
        """Filter queryset based on user's organization"""
        qs = super().get_queryset(request)
        
        # Superusers see everything
        if request.user.is_superuser:
            return qs
        
        # Get user's organization
        user_org = request.user.get_organization()
        if not user_org:
            return qs.none()
        
        # Filter by organization
        if hasattr(self.model, 'organization'):
            return qs.filter(organization=user_org)
        
        return qs
    
    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        """Limit organization choices to user's organization"""
        
        if db_field.name == "organization":
            if not request.user.is_superuser:
                user_org = request.user.get_organization()
                if user_org:
                    from apps.core.models import Organization
                    kwargs["queryset"] = Organization.objects.filter(id=user_org.id)
        
        return super().formfield_for_foreignkey(db_field, request, **kwargs)
    
    def has_view_permission(self, request, obj=None):
        """Check if user can view the object"""
        if not super().has_view_permission(request, obj):
            return False
        
        if obj is None or request.user.is_superuser:
            return True
        
        # Check organization access
        if hasattr(obj, 'organization') and obj.organization:
            user_org = request.user.get_organization()
            return obj.organization == user_org
        
        return True
    
    def has_change_permission(self, request, obj=None):
        """Check if user can change the object"""
        if not super().has_change_permission(request, obj):
            return False
        
        return self.has_view_permission(request, obj)
    
    def has_delete_permission(self, request, obj=None):
        """Check if user can delete the object"""
        if not super().has_delete_permission(request, obj):
            return False
        
        return self.has_view_permission(request, obj)
