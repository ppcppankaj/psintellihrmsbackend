"""AI Services Admin"""
from django.contrib import admin
from django.contrib.auth import get_user_model
from apps.core.models import Organization
from apps.employees.models import Employee
from .models import AIModelVersion, AIPrediction

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
        elif db_field.related_model is AIModelVersion:
            kwargs["queryset"] = AIModelVersion.objects.filter(organization=user_org, is_deleted=False)

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


@admin.register(AIModelVersion)
class AIModelVersionAdmin(OrganizationScopedAdminMixin, admin.ModelAdmin):
    list_display = ['name', 'organization', 'model_type', 'version', 'is_active', 'accuracy', 'created_at']
    list_filter = ['organization', 'model_type', 'is_active']
    search_fields = ['name']


@admin.register(AIPrediction)
class AIPredictionAdmin(OrganizationScopedAdminMixin, admin.ModelAdmin):
    list_display = ['organization', 'entity_type', 'entity_id', 'confidence', 'human_reviewed', 'created_at']
    list_filter = ['organization', 'entity_type', 'human_reviewed']
    raw_id_fields = ['model_version', 'reviewed_by']
