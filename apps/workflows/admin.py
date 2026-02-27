"""Workflows Admin"""
from django.contrib import admin
from django.contrib.auth import get_user_model
from apps.core.models import Organization
from apps.employees.models import Employee
from .models import WorkflowDefinition, WorkflowStep, WorkflowInstance, WorkflowAction

User = get_user_model()


class OrganizationScopedAdminMixin:
    def _get_user_org(self, request):
        if request.user.is_superuser:
            return None
        return request.user.get_organization()

    def get_queryset(self, request):
        qs = super().get_queryset(request)

        if request.user.is_superuser:
            return qs

        user_org = self._get_user_org(request)
        if user_org:
            return qs.filter(organization=user_org)

        return qs.none()

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if request.user.is_superuser:
            return super().formfield_for_foreignkey(db_field, request, **kwargs)

        user_org = self._get_user_org(request)
        if not user_org:
            kwargs["queryset"] = db_field.related_model.objects.none()
            return super().formfield_for_foreignkey(db_field, request, **kwargs)

        if db_field.name == "organization":
            kwargs["queryset"] = Organization.objects.filter(id=user_org.id)
        elif db_field.related_model is User:
            kwargs["queryset"] = User.objects.filter(
                organization_memberships__organization=user_org,
                organization_memberships__is_active=True,
            ).distinct()
        elif db_field.related_model is Employee:
            kwargs["queryset"] = Employee.objects.filter(
                organization=user_org,
                is_active=True,
                is_deleted=False,
            )
        elif db_field.related_model is WorkflowDefinition:
            kwargs["queryset"] = WorkflowDefinition.objects.filter(organization=user_org, is_deleted=False)
        elif db_field.related_model is WorkflowInstance:
            kwargs["queryset"] = WorkflowInstance.objects.filter(organization=user_org, is_deleted=False)
        elif db_field.related_model is WorkflowStep:
            kwargs["queryset"] = WorkflowStep.objects.filter(organization=user_org, is_deleted=False)

        return super().formfield_for_foreignkey(db_field, request, **kwargs)

    def save_model(self, request, obj, form, change):
        if hasattr(obj, "organization") and not request.user.is_superuser:
            user_org = self._get_user_org(request)
            if user_org:
                obj.organization = user_org

        if hasattr(obj, "created_by") and not obj.created_by:
            obj.created_by = request.user
        if hasattr(obj, "updated_by"):
            obj.updated_by = request.user

        super().save_model(request, obj, form, change)


@admin.register(WorkflowDefinition)
class WorkflowDefinitionAdmin(OrganizationScopedAdminMixin, admin.ModelAdmin):
    list_display = ['name', 'code', 'organization', 'entity_type', 'sla_hours', 'is_active']
    list_filter = ['organization', 'entity_type', 'is_active']
    search_fields = ['name', 'code']


@admin.register(WorkflowStep)
class WorkflowStepAdmin(OrganizationScopedAdminMixin, admin.ModelAdmin):
    list_display = ['workflow', 'organization', 'order', 'name', 'approver_type', 'is_optional']
    list_filter = ['organization', 'workflow', 'approver_type']
    ordering = ['workflow', 'order']


@admin.register(WorkflowInstance)
class WorkflowInstanceAdmin(OrganizationScopedAdminMixin, admin.ModelAdmin):
    list_display = ['workflow', 'organization', 'entity_type', 'entity_id', 'current_step', 'status', 'started_at']
    list_filter = ['organization', 'status', 'entity_type']
    raw_id_fields = ['workflow', 'current_approver']


@admin.register(WorkflowAction)
class WorkflowActionAdmin(OrganizationScopedAdminMixin, admin.ModelAdmin):
    list_display = ['instance', 'organization', 'step', 'actor', 'action', 'created_at']
    list_filter = ['organization', 'action']
    raw_id_fields = ['instance', 'actor']
