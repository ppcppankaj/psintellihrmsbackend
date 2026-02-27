"""
Compliance ViewSets - GDPR, Data Retention, Legal Holds
Security: Requires authentication and organization/branch isolation
"""

from rest_framework import viewsets, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.decorators import action
from rest_framework.response import Response
from django.utils import timezone
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.filters import SearchFilter, OrderingFilter

from apps.core.permissions_branch import BranchFilterBackend, BranchPermission, OrganizationFilterBackend
from apps.core.tenant_guards import OrganizationViewSetMixin
from .permissions import ComplianceTenantPermission
from .models import (
    DataRetentionPolicy,
    ConsentRecord,
    LegalHold,
    DataSubjectRequest,
    AuditExportRequest,
    RetentionExecution,
)
from .serializers import (
    DataRetentionPolicySerializer,
    ConsentRecordSerializer,
    LegalHoldSerializer,
    DataSubjectRequestSerializer,
    AuditExportRequestSerializer,
    RetentionExecutionSerializer,
)
from .services import AuditExportService, RetentionService
from .tasks import run_audit_export, run_retention_execution
from .filters import (
    DataRetentionPolicyFilter, ConsentRecordFilter, LegalHoldFilter,
    DataSubjectRequestFilter, AuditExportRequestFilter, RetentionExecutionFilter,
)


class DataRetentionPolicyViewSet(OrganizationViewSetMixin, viewsets.ModelViewSet):
    """
    Data Retention Policy management.
    Organization-scoped (policies apply to entire organization).
    """
    queryset = DataRetentionPolicy.objects.none()
    serializer_class = DataRetentionPolicySerializer
    permission_classes = [IsAuthenticated, ComplianceTenantPermission]
    filter_backends = [OrganizationFilterBackend, DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_class = DataRetentionPolicyFilter
    search_fields = ['name', 'entity_type']
    
    def get_queryset(self):
        """Filter by user's organization"""
        queryset = super().get_queryset()
        if hasattr(self.request.user, 'is_superuser') and self.request.user.is_superuser:
            return DataRetentionPolicy.objects.filter() # Superusers can see all if needed, but rule 1 is strict.
        
        org = getattr(self.request, 'organization', None)
        if not org:
            return DataRetentionPolicy.objects.none()
        
        return queryset.filter(organization=org)


class ConsentRecordViewSet(OrganizationViewSetMixin, viewsets.ModelViewSet):
    """
    Consent records for GDPR compliance.
    Branch-scoped through employee relationship.
    """
    queryset = ConsentRecord.objects.none()
    serializer_class = ConsentRecordSerializer
    permission_classes = [IsAuthenticated, ComplianceTenantPermission, BranchPermission]
    filter_backends = [BranchFilterBackend, DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_class = ConsentRecordFilter
    search_fields = ['consent_type']
    
    def get_queryset(self):
        """Filter by user's accessible branches via employee"""
        queryset = super().get_queryset()
        if hasattr(self.request.user, 'is_superuser') and self.request.user.is_superuser:
            return ConsentRecord.objects.filter()
        
        org = getattr(self.request, 'organization', None)
        if not org:
            return ConsentRecord.objects.none()
        
        queryset = queryset.filter(organization=org)
        
        # Get user's branches
        from apps.authentication.models_hierarchy import BranchUser
        branch_ids = list(BranchUser.objects.filter(
            user=self.request.user,
            is_active=True
        ).values_list('branch_id', flat=True))
        
        if not branch_ids:
            return queryset.none()
        
        return queryset.filter(employee__branch_id__in=branch_ids)


class LegalHoldViewSet(OrganizationViewSetMixin, viewsets.ModelViewSet):
    """
    Legal holds for data preservation.
    Organization-scoped with employee references.
    """
    queryset = LegalHold.objects.none()
    serializer_class = LegalHoldSerializer
    permission_classes = [IsAuthenticated, ComplianceTenantPermission, BranchPermission]
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_class = LegalHoldFilter
    search_fields = ['name', 'description']
    
    def get_queryset(self):
        """Filter by user's accessible branches via affected employees"""
        queryset = super().get_queryset()
        
        org = getattr(self.request, 'organization', None)
        if not org:
            return LegalHold.objects.none()
        
        queryset = queryset.filter(employees__branch__organization=org).distinct()

        if self.request.user.is_superuser:
            return queryset
        
        # Filter to legal holds that have affected employees in user's branches
        from apps.authentication.models_hierarchy import BranchUser
        branch_ids = list(BranchUser.objects.filter(
            user=self.request.user,
            is_active=True
        ).values_list('branch_id', flat=True))
        
        if self.request.user.is_org_admin or self.request.user.is_organization_admin():
            # Org admins see all legal holds in their org
            return queryset
        
        if not branch_ids:
            return queryset.none()
        
        return queryset.filter(employees__branch_id__in=branch_ids).distinct()


class DataSubjectRequestViewSet(OrganizationViewSetMixin, viewsets.ModelViewSet):
    """DSAR requests"""
    queryset = DataSubjectRequest.objects.none()
    serializer_class = DataSubjectRequestSerializer
    permission_classes = [IsAuthenticated, ComplianceTenantPermission]
    filter_backends = [OrganizationFilterBackend, DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_class = DataSubjectRequestFilter
    search_fields = ['details', 'notes']

    def get_queryset(self):
        return super().get_queryset()

    def perform_create(self, serializer):
        org = self.request.user.get_organization() if hasattr(self.request.user, 'get_organization') else None
        serializer.save(requested_by=self.request.user, organization=org)

    @action(detail=True, methods=['post'])
    def mark_in_progress(self, request, pk=None):
        dsar = self.get_object()
        dsar.status = DataSubjectRequest.STATUS_IN_PROGRESS
        dsar.processed_by = request.user
        dsar.processed_at = timezone.now()
        dsar.save(update_fields=['status', 'processed_by', 'processed_at'])
        return Response(self.get_serializer(dsar).data)

    @action(detail=True, methods=['post'])
    def fulfill(self, request, pk=None):
        dsar = self.get_object()
        dsar.status = DataSubjectRequest.STATUS_FULFILLED
        dsar.processed_by = request.user
        dsar.processed_at = timezone.now()
        if request.FILES.get('response_file'):
            dsar.response_file = request.FILES['response_file']
        dsar.notes = request.data.get('notes', dsar.notes)
        dsar.save()
        return Response(self.get_serializer(dsar).data)

    @action(detail=True, methods=['post'])
    def reject(self, request, pk=None):
        dsar = self.get_object()
        dsar.status = DataSubjectRequest.STATUS_REJECTED
        dsar.processed_by = request.user
        dsar.processed_at = timezone.now()
        dsar.notes = request.data.get('notes', dsar.notes)
        dsar.save()
        return Response(self.get_serializer(dsar).data)


class AuditExportRequestViewSet(OrganizationViewSetMixin, viewsets.ModelViewSet):
    """Audit export requests"""
    queryset = AuditExportRequest.objects.none()
    serializer_class = AuditExportRequestSerializer
    permission_classes = [IsAuthenticated, ComplianceTenantPermission]
    filter_backends = [OrganizationFilterBackend, DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_class = AuditExportRequestFilter
    search_fields = ['requested_by__email']

    def get_queryset(self):
        return super().get_queryset()

    def perform_create(self, serializer):
        org = self.request.user.get_organization() if hasattr(self.request.user, 'get_organization') else None
        serializer.save(requested_by=self.request.user, organization=org)

    @action(detail=True, methods=['post'])
    def run(self, request, pk=None):
        export_request = self.get_object()
        run_async = request.data.get('run_async', False)
        if run_async:
            run_audit_export.delay(str(export_request.id))
            export_request.status = AuditExportRequest.STATUS_PENDING
            export_request.save(update_fields=['status'])
            return Response(self.get_serializer(export_request).data, status=status.HTTP_202_ACCEPTED)

        AuditExportService.run_export(export_request, request.user)
        return Response(self.get_serializer(export_request).data)

    @action(detail=True, methods=['get'])
    def download(self, request, pk=None):
        export_request = self.get_object()
        if not export_request.file:
            return Response({'detail': 'Export file not available'}, status=status.HTTP_404_NOT_FOUND)
        from django.http import FileResponse
        return FileResponse(export_request.file.open('rb'), as_attachment=True)


class RetentionExecutionViewSet(OrganizationViewSetMixin, viewsets.ModelViewSet):
    """Retention executions"""
    queryset = RetentionExecution.objects.none()
    serializer_class = RetentionExecutionSerializer
    permission_classes = [IsAuthenticated, ComplianceTenantPermission]
    filter_backends = [OrganizationFilterBackend, DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_class = RetentionExecutionFilter
    search_fields = ['policy__name']

    def get_queryset(self):
        return super().get_queryset()

    def perform_create(self, serializer):
        org = self.request.user.get_organization() if hasattr(self.request.user, 'get_organization') else None
        serializer.save(requested_by=self.request.user, organization=org)

    @action(detail=True, methods=['post'])
    def run(self, request, pk=None):
        execution = self.get_object()
        run_async = request.data.get('run_async', False)
        if run_async:
            run_retention_execution.delay(str(execution.id))
            execution.status = RetentionExecution.STATUS_PENDING
            execution.save(update_fields=['status'])
            return Response(self.get_serializer(execution).data, status=status.HTTP_202_ACCEPTED)

        RetentionService.run_execution(execution, request.user)
        return Response(self.get_serializer(execution).data)
