"""Onboarding Views - API Endpoints"""

from rest_framework import viewsets, status, filters
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework.parsers import MultiPartParser, FormParser
from rest_framework.exceptions import ValidationError
from django.shortcuts import get_object_or_404
from django.core.exceptions import ValidationError as DjangoValidationError
from django_filters.rest_framework import DjangoFilterBackend

from apps.core.tenant_guards import OrganizationViewSetMixin
from apps.core.permissions import FilterByPermissionMixin, HasPermission
from .permissions import OnboardingTenantPermission
from apps.billing.mixins import PlanFeatureRequiredMixin
from apps.billing.services import SubscriptionService
from .models import (
    OnboardingTemplate, OnboardingTaskTemplate,
    EmployeeOnboarding, OnboardingTaskProgress, OnboardingDocument
)
from .serializers import (
    OnboardingTemplateListSerializer, OnboardingTemplateDetailSerializer,
    OnboardingTaskTemplateSerializer,
    EmployeeOnboardingListSerializer, EmployeeOnboardingDetailSerializer,
    OnboardingTaskProgressSerializer, OnboardingDocumentSerializer,
    InitiateOnboardingSerializer, CompleteTaskSerializer, VerifyDocumentSerializer
)
from .services import OnboardingService
from .filters import (
    OnboardingTemplateFilter, OnboardingTaskTemplateFilter,
    EmployeeOnboardingFilter, OnboardingTaskProgressFilter, OnboardingDocumentFilter,
)


class OnboardingTemplateViewSet(OrganizationViewSetMixin, viewsets.ModelViewSet):
    """
    ViewSet for managing onboarding templates.
    
    list: Get all onboarding templates
    retrieve: Get template details with tasks
    create: Create new template
    update: Update template
    delete: Delete template
    """
    queryset = OnboardingTemplate.objects.none()
    permission_classes = [IsAuthenticated, OnboardingTenantPermission]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_class = OnboardingTemplateFilter
    search_fields = ['name', 'code']
    ordering_fields = ['name', 'days_to_complete', 'created_at']
    ordering = ['name']
    
    def get_serializer_class(self):
        if self.action == 'retrieve':
            return OnboardingTemplateDetailSerializer
        return OnboardingTemplateListSerializer
    
    def get_queryset(self):
        queryset = super().get_queryset()
        
        # Filter by active status
        is_active = self.request.query_params.get('is_active')
        if is_active is not None:
            queryset = queryset.filter(is_active=is_active.lower() == 'true')
        
        # Filter by department
        department = self.request.query_params.get('department')
        if department:
            queryset = queryset.filter(department_id=department)
        
        return queryset.select_related('department', 'designation', 'location')
    
    @action(detail=True, methods=['post'])
    def duplicate(self, request, pk=None):
        """Duplicate a template with all its tasks"""
        template = self.get_object()
        
        # Create new template
        new_template = OnboardingTemplate.objects.create(
            organization=template.organization,
            name=f"{template.name} (Copy)",
            code=f"{template.code}_copy",
            description=template.description,
            department=template.department,
            designation=template.designation,
            location=template.location,
            days_before_joining=template.days_before_joining,
            days_to_complete=template.days_to_complete,
            is_default=False,
            is_active=False
        )
        
        # Copy tasks
        for task in template.tasks.all():
            OnboardingTaskTemplate.objects.create(
                organization=template.organization,
                template=new_template,
                title=task.title,
                description=task.description,
                stage=task.stage,
                assigned_to_type=task.assigned_to_type,
                due_days_offset=task.due_days_offset,
                is_mandatory=task.is_mandatory,
                requires_attachment=task.requires_attachment,
                requires_acknowledgement=task.requires_acknowledgement,
                order=task.order
            )
        
        serializer = OnboardingTemplateDetailSerializer(new_template)
        return Response(serializer.data, status=status.HTTP_201_CREATED)


class OnboardingTaskTemplateViewSet(OrganizationViewSetMixin, viewsets.ModelViewSet):
    """ViewSet for managing individual task templates"""
    queryset = OnboardingTaskTemplate.objects.none()
    serializer_class = OnboardingTaskTemplateSerializer
    permission_classes = [IsAuthenticated, OnboardingTenantPermission]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_class = OnboardingTaskTemplateFilter
    search_fields = ['title']
    ordering_fields = ['order', 'stage', 'created_at']
    ordering = ['order']
    
    def get_queryset(self):
        queryset = super().get_queryset()
        
        # Filter by template
        template_id = self.request.query_params.get('template')
        if template_id:
            queryset = queryset.filter(template_id=template_id)
        
        # Filter by stage
        stage = self.request.query_params.get('stage')
        if stage:
            queryset = queryset.filter(stage=stage)
        
        return queryset.select_related('template')


class EmployeeOnboardingViewSet(OrganizationViewSetMixin, FilterByPermissionMixin, viewsets.ModelViewSet):
    """
    ViewSet for employee onboarding instances.
    """
    queryset = EmployeeOnboarding.objects.none()
    permission_classes = [IsAuthenticated, OnboardingTenantPermission, HasPermission]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_class = EmployeeOnboardingFilter
    search_fields = ['employee__first_name', 'employee__last_name']
    ordering_fields = ['status', 'joining_date', 'created_at']
    ordering = ['-created_at']
    required_permissions = {
        'list': ['onboarding.view'],
        'retrieve': ['onboarding.view'],
        'create': ['onboarding.manage'],
        'update': ['onboarding.manage'],
        'partial_update': ['onboarding.manage'],
        'destroy': ['onboarding.manage'],
    }
    scope_field = 'employee'
    
    def get_serializer_class(self):
        if self.action == 'retrieve':
            return EmployeeOnboardingDetailSerializer
        return EmployeeOnboardingListSerializer
    
    def get_queryset(self):
        queryset = super().get_queryset()
        
        # Filter by status
        status_filter = self.request.query_params.get('status')
        if status_filter:
            queryset = queryset.filter(status=status_filter)
        
        # Filter by HR responsible
        hr_responsible = self.request.query_params.get('hr_responsible')
        if hr_responsible:
            queryset = queryset.filter(hr_responsible_id=hr_responsible)
        
        return queryset.select_related(
            'employee', 'template', 'hr_responsible', 'buddy'
        ).prefetch_related('task_progress', 'documents')
    
    @action(detail=False, methods=['post'])
    def initiate(self, request):
        """Initiate onboarding for an employee"""
        serializer = InitiateOnboardingSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        from apps.employees.models import Employee
        
        employee = get_object_or_404(
            Employee, 
            id=serializer.validated_data['employee_id'],
            organization=request.organization
        )
        
        template = None
        if serializer.validated_data.get('template_id'):
            template = get_object_or_404(
                OnboardingTemplate, 
                id=serializer.validated_data['template_id'],
                organization=request.organization
            )
        
        hr_responsible = None
        if serializer.validated_data.get('hr_responsible_id'):
            hr_responsible = get_object_or_404(
                Employee, 
                id=serializer.validated_data['hr_responsible_id'],
                organization=request.organization
            )
        
        buddy = None
        if serializer.validated_data.get('buddy_id'):
            buddy = get_object_or_404(
                Employee, 
                id=serializer.validated_data['buddy_id'],
                organization=request.organization
            )
        
        try:
            onboarding = OnboardingService.initiate_onboarding(
                employee=employee,
                template=template,
                joining_date=serializer.validated_data['joining_date'],
                hr_responsible=hr_responsible,
                buddy=buddy
            )
            
            return Response(
                EmployeeOnboardingDetailSerializer(onboarding).data,
                status=status.HTTP_201_CREATED
            )
        except ValueError as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
    
    @action(detail=False, methods=['get'])
    def my_onboarding(self, request):
        """Get current user's onboarding"""
        employee = getattr(request.user, 'employee', None)
        if not employee:
            return Response({'error': 'No employee profile'}, status=status.HTTP_404_NOT_FOUND)
        
        try:
            onboarding = EmployeeOnboarding.objects.get(
                employee=employee,
                organization=request.organization
            )
            serializer = EmployeeOnboardingDetailSerializer(onboarding)
            return Response(serializer.data)
        except EmployeeOnboarding.DoesNotExist:
            return Response({'error': 'No onboarding found'}, status=status.HTTP_404_NOT_FOUND)
    
    @action(detail=False, methods=['get'])
    def my_tasks(self, request):
        """Get onboarding tasks assigned to current user"""
        employee = getattr(request.user, 'employee', None)
        if not employee:
            return Response({'error': 'No employee profile'}, status=status.HTTP_404_NOT_FOUND)
        
        tasks = OnboardingService.get_pending_tasks_for_user(employee)
        serializer = OnboardingTaskProgressSerializer(tasks, many=True)
        return Response(serializer.data)
    
    @action(detail=True, methods=['get'])
    def summary(self, request, pk=None):
        """Get onboarding summary statistics"""
        onboarding = self.get_object()
        summary = OnboardingService.get_onboarding_summary(onboarding)
        return Response(summary)
    
    @action(detail=True, methods=['post'])
    def cancel(self, request, pk=None):
        """Cancel an onboarding"""
        onboarding = self.get_object()
        
        if onboarding.status == EmployeeOnboarding.STATUS_COMPLETED:
            return Response(
                {'error': 'Cannot cancel completed onboarding'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        onboarding.status = EmployeeOnboarding.STATUS_CANCELLED
        onboarding.save(update_fields=['status'])
        
        return Response({'status': 'cancelled'})


class OnboardingTaskProgressViewSet(OrganizationViewSetMixin, FilterByPermissionMixin, viewsets.ModelViewSet):
    """ViewSet for onboarding task progress"""
    queryset = OnboardingTaskProgress.objects.none()
    serializer_class = OnboardingTaskProgressSerializer
    permission_classes = [IsAuthenticated, OnboardingTenantPermission, HasPermission]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_class = OnboardingTaskProgressFilter
    search_fields = ['task_template__title']
    ordering_fields = ['status', 'due_date', 'created_at']
    ordering = ['due_date']
    required_permissions = {
        'list': ['onboarding.view'],
        'retrieve': ['onboarding.view'],
    }
    scope_field = 'onboarding__employee'
    
    def get_queryset(self):
        queryset = super().get_queryset()
        
        # Filter by onboarding
        onboarding_id = self.request.query_params.get('onboarding')
        if onboarding_id:
            queryset = queryset.filter(onboarding_id=onboarding_id)
        
        # Filter by status
        status_filter = self.request.query_params.get('status')
        if status_filter:
            queryset = queryset.filter(status=status_filter)
        
        # Filter by stage
        stage = self.request.query_params.get('stage')
        if stage:
            queryset = queryset.filter(stage=stage)
        
        return queryset.select_related('onboarding', 'assigned_to', 'completed_by')
    
    @action(detail=True, methods=['post'])
    def complete(self, request, pk=None):
        """Mark a task as completed"""
        task = self.get_object()
        serializer = CompleteTaskSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        employee = getattr(request.user, 'employee', None)
        
        task = OnboardingService.complete_task(
            task_progress=task,
            completed_by=employee,
            notes=serializer.validated_data.get('notes', ''),
            attachment=serializer.validated_data.get('attachment'),
            acknowledged=serializer.validated_data.get('acknowledged', False)
        )
        
        return Response(OnboardingTaskProgressSerializer(task).data)
    
    @action(detail=True, methods=['post'])
    def skip(self, request, pk=None):
        """Skip a non-mandatory task"""
        task = self.get_object()
        employee = getattr(request.user, 'employee', None)
        reason = request.data.get('reason', '')
        
        try:
            task = OnboardingService.skip_task(task, employee, reason)
            return Response(OnboardingTaskProgressSerializer(task).data)
        except ValueError as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
    
    @action(detail=True, methods=['post'])
    def start(self, request, pk=None):
        """Mark a task as in progress"""
        task = self.get_object()
        from django.utils import timezone
        
        task.status = OnboardingTaskProgress.STATUS_IN_PROGRESS
        task.started_at = timezone.now()
        task.save(update_fields=['status', 'started_at'])
        
        return Response(OnboardingTaskProgressSerializer(task).data)


class OnboardingDocumentViewSet(PlanFeatureRequiredMixin, OrganizationViewSetMixin, FilterByPermissionMixin, viewsets.ModelViewSet):
    """ViewSet for onboarding documents"""
    queryset = OnboardingDocument.objects.none()
    serializer_class = OnboardingDocumentSerializer
    permission_classes = [IsAuthenticated, OnboardingTenantPermission, HasPermission]
    parser_classes = [MultiPartParser, FormParser]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_class = OnboardingDocumentFilter
    search_fields = ['name']
    ordering_fields = ['status', 'created_at']
    ordering = ['-created_at']
    required_plan_feature = 'document_enabled'
    required_permissions = {
        'list': ['onboarding.view'],
        'retrieve': ['onboarding.view'],
    }
    scope_field = 'onboarding__employee'
    
    def get_queryset(self):
        queryset = super().get_queryset()
        
        # Filter by onboarding
        onboarding_id = self.request.query_params.get('onboarding')
        if onboarding_id:
            queryset = queryset.filter(onboarding_id=onboarding_id)
        
        # Filter by status
        status_filter = self.request.query_params.get('status')
        if status_filter:
            queryset = queryset.filter(status=status_filter)
        
        return queryset.select_related('onboarding', 'verified_by')

    def perform_create(self, serializer):
        organization = getattr(self.request, 'organization', None)
        if not organization:
            raise ValidationError({'detail': 'Organization context missing for upload'})

        upload = self.request.FILES.get('file')
        extra_kwargs = {}
        if upload:
            extra_kwargs['file_size'] = upload.size
            try:
                SubscriptionService.ensure_storage_available(organization, upload.size)
            except DjangoValidationError as exc:
                raise ValidationError({'file': str(exc)}) from exc

        serializer.save(**extra_kwargs)

    def perform_update(self, serializer):
        organization = getattr(self.request, 'organization', None)
        if not organization:
            raise ValidationError({'detail': 'Organization context missing for upload'})

        upload = self.request.FILES.get('file')
        extra_kwargs = {}
        if upload:
            extra_kwargs['file_size'] = upload.size
            try:
                SubscriptionService.ensure_storage_available(organization, upload.size)
            except DjangoValidationError as exc:
                raise ValidationError({'file': str(exc)}) from exc

        serializer.save(**extra_kwargs)
    
    @action(detail=True, methods=['post'])
    def verify(self, request, pk=None):
        """Verify or reject a document"""
        document = self.get_object()
        serializer = VerifyDocumentSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        employee = getattr(request.user, 'employee', None)
        
        document = OnboardingService.verify_document(
            document=document,
            verified_by=employee,
            action=serializer.validated_data['action'],
            rejection_reason=serializer.validated_data.get('rejection_reason', '')
        )
        
        return Response(OnboardingDocumentSerializer(document).data)
