"""
Shared base ViewSet classes for all HRMS apps.

Every tenant-scoped ModelViewSet should inherit from ``TenantScopedModelViewSet``
so that organisation isolation, standard response wrapping, pagination, filtering,
search, ordering, bulk import/export and permission enforcement come for free.
"""

from rest_framework import viewsets, status, filters
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from django_filters.rest_framework import DjangoFilterBackend

from apps.core.tenant_guards import OrganizationViewSetMixin
from apps.core.permissions import (
    FilterByPermissionMixin,
    HasPermission,
    IsOrganizationAdmin,
    PermissionRequiredMixin,
)
from apps.core.mixins import BulkImportExportMixin
from apps.core.response import success_response, success_detail_response


# ---------------------------------------------------------------------------
# Base ViewSet — wraps responses in the standard envelope
# ---------------------------------------------------------------------------

class StandardResponseMixin:
    """Wraps *non-paginated* responses in ``{success, data, message}``."""

    def finalize_response(self, request, response, *args, **kwargs):
        response = super().finalize_response(request, response, *args, **kwargs)
        # Only wrap when we have an actual dict/list and it hasn't been wrapped
        if (
            hasattr(response, 'data')
            and response.data is not None
            and not isinstance(response.data, bytes)
            and response.status_code < 400
        ):
            data = response.data
            # Already wrapped by paginator or exception handler
            if isinstance(data, dict) and 'success' in data:
                return response
            response.data = {
                'success': True,
                'data': data,
                'message': self._get_success_message(request, response),
            }
        return response

    def _get_success_message(self, request, response):
        method = request.method
        messages = {
            'POST': 'Created successfully.',
            'PUT': 'Updated successfully.',
            'PATCH': 'Updated successfully.',
            'DELETE': 'Deleted successfully.',
        }
        return messages.get(method, 'OK')


# ---------------------------------------------------------------------------
# Tenant-Scoped ModelViewSet — the backbone for every HRMS app
# ---------------------------------------------------------------------------

class TenantScopedModelViewSet(
    StandardResponseMixin,
    BulkImportExportMixin,
    FilterByPermissionMixin,
    PermissionRequiredMixin,
    OrganizationViewSetMixin,
    viewsets.ModelViewSet,
):
    """
    Production-grade ModelViewSet with built-in:

    • **Multi-tenancy** — auto-filters queryset by ``request.organization`` and
      injects it on create.
    • **Permission enforcement** — per-action ``permission_map`` checked
      via ``PermissionRequiredMixin``.
    • **Scope-based filtering** — ``FilterByPermissionMixin`` restricts records
      to own / team / all based on user permissions.
    • **Pagination / filter / search / ordering** — ``DjangoFilterBackend``,
      ``SearchFilter`` and ``OrderingFilter`` registered globally or per-ViewSet.
    • **Bulk import / export** — ``template``, ``export`` and ``import_data``
      actions from ``BulkImportExportMixin``.
    • **Standard response envelope** — ``{success, data, message}`` via
      ``StandardResponseMixin``.
    """

    permission_classes = [IsAuthenticated, HasPermission]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    ordering = ['-created_at']

    # -- Subclasses SHOULD set these ----------------------------------------
    # queryset = MyModel.objects.none()
    # serializer_class = MySerializer
    # filterset_fields = [...]
    # search_fields = [...]
    # ordering_fields = [...]
    # permission_map = { 'list': [...], 'create': [...], ... }
    # permission_category = 'myapp'
    # scope_field = 'employee'  # or 'user' / 'self'

    # -- Optional: separate list / detail serializers -----------------------
    list_serializer_class = None
    detail_serializer_class = None

    def get_serializer_class(self):
        if self.action == 'list' and self.list_serializer_class:
            return self.list_serializer_class
        if self.action == 'retrieve' and self.detail_serializer_class:
            return self.detail_serializer_class
        return super().get_serializer_class()

    # -- Tenant isolation ---------------------------------------------------

    def _resolve_organization(self, required=True):
        org = getattr(self.request, 'organization', None) or getattr(
            self.request.user, 'organization', None
        )
        if org:
            return org
        if self.request.user.is_superuser and not required:
            return None
        if required:
            raise PermissionDenied('Organization context required.')
        return None

    def get_queryset(self):
        qs = super().get_queryset()
        if getattr(self, 'swagger_fake_view', False):
            return qs.none()
        org = self._resolve_organization(required=False)
        if org and hasattr(qs.model, 'organization_id'):
            qs = qs.filter(organization=org)
        elif not self.request.user.is_superuser:
            return qs.none()
        return qs

    def perform_create(self, serializer):
        org = self._resolve_organization()
        kwargs = {'organization': org}
        if hasattr(serializer.Meta.model, 'created_by_id'):
            kwargs['created_by'] = self.request.user
        serializer.save(**kwargs)

    def perform_update(self, serializer):
        serializer.save()

    def perform_destroy(self, instance):
        # Soft-delete if the model supports it; hard-delete otherwise
        if hasattr(instance, 'is_active'):
            instance.is_active = False
            instance.save(update_fields=['is_active'])
        else:
            instance.delete()


# ---------------------------------------------------------------------------
# Read-only variant
# ---------------------------------------------------------------------------

class TenantScopedReadOnlyViewSet(
    StandardResponseMixin,
    FilterByPermissionMixin,
    PermissionRequiredMixin,
    OrganizationViewSetMixin,
    viewsets.ReadOnlyModelViewSet,
):
    """Read-only tenant-scoped ViewSet (list + retrieve only)."""

    permission_classes = [IsAuthenticated, HasPermission]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    ordering = ['-created_at']
    list_serializer_class = None
    detail_serializer_class = None

    def get_serializer_class(self):
        if self.action == 'list' and self.list_serializer_class:
            return self.list_serializer_class
        if self.action == 'retrieve' and self.detail_serializer_class:
            return self.detail_serializer_class
        return super().get_serializer_class()

    def _resolve_organization(self, required=True):
        org = getattr(self.request, 'organization', None) or getattr(
            self.request.user, 'organization', None
        )
        if org:
            return org
        if self.request.user.is_superuser and not required:
            return None
        if required:
            raise PermissionDenied('Organization context required.')
        return None

    def get_queryset(self):
        qs = super().get_queryset()
        if getattr(self, 'swagger_fake_view', False):
            return qs.none()
        org = self._resolve_organization(required=False)
        if org and hasattr(qs.model, 'organization_id'):
            qs = qs.filter(organization=org)
        elif not self.request.user.is_superuser:
            return qs.none()
        return qs


# ---------------------------------------------------------------------------
# File-upload aware variant
# ---------------------------------------------------------------------------

class TenantScopedFileUploadViewSet(TenantScopedModelViewSet):
    """Adds ``MultiPartParser`` + ``FormParser`` for endpoints accepting files."""

    parser_classes = [MultiPartParser, FormParser, JSONParser]
