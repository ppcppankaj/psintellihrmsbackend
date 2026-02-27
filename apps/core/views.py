from rest_framework import permissions, viewsets, filters
from rest_framework.exceptions import PermissionDenied, ValidationError
from django_filters.rest_framework import DjangoFilterBackend

from apps.core.tenant_guards import OrganizationViewSetMixin

from .models import (
    Announcement,
    AuditLog,
    FeatureFlag,
    Organization,
    OrganizationDomain,
    OrganizationSettings,
)
from .permissions import IsOrganizationAdmin
from .serializers import (
    AnnouncementSerializer,
    AuditLogSerializer,
    FeatureFlagSerializer,
    OrganizationDomainSerializer,
    OrganizationSerializer,
    OrganizationSettingsSerializer,
)
from .filters import (
    OrganizationFilter,
    OrganizationDomainFilter,
    AuditLogFilter,
    AnnouncementFilter,
    FeatureFlagFilter,
    OrganizationSettingsFilter,
)
from .viewsets import StandardResponseMixin

from django.http import JsonResponse
from rest_framework.throttling import AnonRateThrottle
from .throttling import LoginRateThrottle

def api_404_view(request, exception=None):
    return JsonResponse(
        {'detail': 'Endpoint not found'},
        status=404
    )


class TenantScopedViewMixin(OrganizationViewSetMixin):
    """Enforce per-organization filtering for tenant data sets."""

    def _resolve_organization(self, required=True):
        org = getattr(self.request, 'organization', None) or getattr(self.request.user, 'organization', None)
        if org:
            return org
        if self.request.user.is_superuser and not required:
            return None
        if required:
            raise PermissionDenied('Organization context required.')
        return None

    def filter_queryset_by_org(self, queryset):
        org = getattr(self.request, 'organization', None) or getattr(self.request.user, 'organization', None)
        if org and hasattr(queryset.model, 'organization_id'):
            return queryset.filter(organization=org)
        if self.request.user.is_superuser:
            return queryset
        raise PermissionDenied('Organization context required.')

# =============================================================================
# ORGANIZATION VIEWSET - SUPERUSER ONLY
# =============================================================================

class IsSuperuser(permissions.BasePermission):
    """
    🔐 Only superusers can manage organizations
    
    Superuser: Create, read, update, delete all organizations
    Org Admin: Read own organization only
    Regular User: No access
    """
    
    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        
        # Superusers full access
        if request.user.is_superuser:
            return True
        
        # Org admins can list/retrieve (own org only)
        if request.user.is_org_admin and request.method in ['GET', 'HEAD', 'OPTIONS']:
            return True
        
        return False
    
    def has_object_permission(self, request, view, obj):
        if request.user.is_superuser:
            return True
        
        # Org admin can only access own org
        if request.user.is_org_admin and request.user.organization_id == obj.id:
            if request.method in ['GET', 'HEAD', 'OPTIONS']:
                return True
        
        return False

class OrganizationViewSet(StandardResponseMixin, viewsets.ModelViewSet):
    """
    🏢 Organization Management - Superuser Only
    
    Rules:
    - Superuser: See all orgs, create, edit, delete
    - Org Admin: See only own organization (read-only)
    - Regular User: No access
    
    Endpoints:
    - GET /api/organizations/ - List (filtered by role)
    - POST /api/organizations/ - Create (superuser only)
    - GET /api/organizations/{id}/ - Retrieve
    - PUT /api/organizations/{id}/ - Update (superuser only)
    - PATCH /api/organizations/{id}/ - Partial update (superuser only)
    - DELETE /api/organizations/{id}/ - Delete (superuser only)
    """
    
    queryset = Organization.objects.none()
    serializer_class = OrganizationSerializer
    permission_classes = [IsSuperuser]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_class = OrganizationFilter
    search_fields = ['name', 'email', 'phone']
    ordering_fields = ['name', 'created_at', 'subscription_status']
    ordering = ['name']
    

    def get_queryset(self):
        # 🔒 Swagger / OpenAPI generation safety
        if getattr(self, 'swagger_fake_view', False):
            return Organization.objects.none()

        user = self.request.user

        if user.is_superuser:
            return Organization.objects.all()

        if getattr(user, 'is_org_admin', False) and getattr(user, 'organization', None):
            return Organization.objects.filter(id=user.organization_id)

        return Organization.objects.none()

    

    
    def create(self, request, *args, **kwargs):
        """🔐 SUPERUSER ONLY - Create organization"""
        if not request.user.is_superuser:
            raise PermissionDenied("Only superusers can create organizations.")
        
        return super().create(request, *args, **kwargs)
    
    def update(self, request, *args, **kwargs):
        """🔐 SUPERUSER ONLY - Update organization"""
        if not request.user.is_superuser:
            raise PermissionDenied("Only superusers can modify organizations.")
        
        return super().update(request, *args, **kwargs)
    
    def partial_update(self, request, *args, **kwargs):
        """🔐 SUPERUSER ONLY - Partial update"""
        if not request.user.is_superuser:
            raise PermissionDenied("Only superusers can modify organizations.")
        
        return super().partial_update(request, *args, **kwargs)
    
    def destroy(self, request, *args, **kwargs):
        """🔐 SUPERUSER ONLY - Delete organization"""
        if not request.user.is_superuser:
            raise PermissionDenied("Only superusers can delete organizations.")
        
        return super().destroy(request, *args, **kwargs)


class DomainViewSet(StandardResponseMixin, TenantScopedViewMixin, viewsets.ModelViewSet):
    """Manage organization domains with tenant isolation."""

    queryset = OrganizationDomain.objects.all()
    serializer_class = OrganizationDomainSerializer
    permission_classes = [permissions.IsAuthenticated, IsOrganizationAdmin]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_class = OrganizationDomainFilter
    search_fields = ['domain_name']
    ordering_fields = ['domain_name', 'created_at']
    ordering = ['domain_name']

    def get_queryset(self):
        return self.filter_queryset_by_org(super().get_queryset())

    def perform_create(self, serializer):
        serializer.save(organization=self._resolve_organization())

    def perform_update(self, serializer):
        serializer.save(organization=serializer.instance.organization)


class AnnouncementViewSet(StandardResponseMixin, TenantScopedViewMixin, viewsets.ModelViewSet):
    """CRUD for organization announcements."""

    queryset = Announcement.objects.all()
    serializer_class = AnnouncementSerializer
    permission_classes = [permissions.IsAuthenticated, IsOrganizationAdmin]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_class = AnnouncementFilter
    search_fields = ['title', 'content']
    ordering_fields = ['published_at', 'created_at', 'priority']
    ordering = ['-is_pinned', '-published_at']

    def get_queryset(self):
        return self.filter_queryset_by_org(super().get_queryset())

    def perform_create(self, serializer):
        serializer.save(organization=self._resolve_organization())

    def perform_update(self, serializer):
        serializer.save(organization=serializer.instance.organization)


class OrganizationSettingsViewSet(StandardResponseMixin, TenantScopedViewMixin, viewsets.ModelViewSet):
    """Manage per-organization global settings."""

    queryset = OrganizationSettings.objects.all()
    serializer_class = OrganizationSettingsSerializer
    permission_classes = [permissions.IsAuthenticated, IsOrganizationAdmin]
    http_method_names = ['get', 'post', 'put', 'patch', 'head', 'options']
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_class = OrganizationSettingsFilter
    ordering_fields = ['created_at', 'updated_at']
    ordering = ['-updated_at']

    def get_queryset(self):
        return self.filter_queryset_by_org(super().get_queryset())

    def perform_create(self, serializer):
        org = self._resolve_organization()
        if OrganizationSettings.objects.filter(organization=org).exists():
            raise ValidationError('Settings already initialized for this organization.')
        serializer.save(organization=org)

    def perform_update(self, serializer):
        serializer.save(organization=serializer.instance.organization)

class AuditLogViewSet(StandardResponseMixin, TenantScopedViewMixin, viewsets.ReadOnlyModelViewSet):
    """Read-only access to tenant-scoped audit trail."""

    queryset = AuditLog.objects.all()
    serializer_class = AuditLogSerializer
    permission_classes = [permissions.IsAuthenticated, IsOrganizationAdmin]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_class = AuditLogFilter
    search_fields = ['user_email', 'resource_id', 'request_id', 'resource_repr']
    ordering_fields = ['timestamp']
    ordering = ['-timestamp']

    def get_queryset(self):
        if getattr(self, 'swagger_fake_view', False):
            return AuditLog.objects.none()

        queryset = self.filter_queryset_by_org(super().get_queryset())

        resource_type = self.request.query_params.get('resource_type')
        if resource_type:
            queryset = queryset.filter(resource_type=resource_type)

        action = self.request.query_params.get('action')
        if action:
            queryset = queryset.filter(action=action)

        return queryset

            
class FeatureFlagViewSet(StandardResponseMixin, TenantScopedViewMixin, viewsets.ModelViewSet):
    """Tenant-scoped feature flag management."""

    queryset = FeatureFlag.objects.all()
    serializer_class = FeatureFlagSerializer
    permission_classes = [permissions.IsAuthenticated, IsOrganizationAdmin]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_class = FeatureFlagFilter
    search_fields = ['name', 'description']
    ordering_fields = ['name', 'updated_at']
    ordering = ['name']

    def get_queryset(self):
        if getattr(self, 'swagger_fake_view', False):
            return FeatureFlag.objects.none()
        return self.filter_queryset_by_org(super().get_queryset())

    def perform_create(self, serializer):
        serializer.save(organization=self._resolve_organization())

    def perform_update(self, serializer):
        serializer.save(organization=serializer.instance.organization)

