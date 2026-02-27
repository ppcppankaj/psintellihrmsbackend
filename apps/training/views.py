"""Training ViewSets"""
from django.db.models import Count, Q
from django.utils import timezone
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.parsers import MultiPartParser, FormParser
from rest_framework.response import Response
from rest_framework.filters import SearchFilter, OrderingFilter
from django_filters.rest_framework import DjangoFilterBackend

from apps.core.tenant_guards import OrganizationViewSetMixin
from apps.core.permissions_branch import BranchPermission, BranchFilterBackend, OrganizationFilterBackend

from .models import (
    TrainingCategory,
    TrainingProgram,
    TrainingMaterial,
    TrainingEnrollment,
    TrainingCompletion,
)
from .serializers import (
    TrainingCategorySerializer,
    TrainingProgramSerializer,
    TrainingMaterialSerializer,
    TrainingEnrollmentSerializer,
    TrainingCompletionSerializer,
)
from .permissions import TrainingManagePermission, TrainingTenantPermission
from .filters import TrainingCategoryFilter, TrainingProgramFilter, TrainingMaterialFilter, TrainingEnrollmentFilter, TrainingCompletionFilter


class TrainingCategoryViewSet(OrganizationViewSetMixin, viewsets.ModelViewSet):
    """Manage training categories"""
    queryset = TrainingCategory.objects.none()
    serializer_class = TrainingCategorySerializer
    permission_classes = [IsAuthenticated, TrainingTenantPermission, TrainingManagePermission]
    filter_backends = [OrganizationFilterBackend, DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_class = TrainingCategoryFilter
    search_fields = ['name', 'code']
    ordering_fields = ['name', 'display_order', 'created_at']

    def get_queryset(self):
        return super().get_queryset().filter(
            is_deleted=False,
        ).annotate(program_count=Count('programs'))

    def perform_create(self, serializer):
        org = self.request.user.get_organization() if hasattr(self.request.user, 'get_organization') else None
        serializer.save(organization=org)


class TrainingProgramViewSet(OrganizationViewSetMixin, viewsets.ModelViewSet):
    """Manage training programs"""
    queryset = TrainingProgram.objects.none()
    serializer_class = TrainingProgramSerializer
    permission_classes = [IsAuthenticated, TrainingTenantPermission, TrainingManagePermission]
    filter_backends = [OrganizationFilterBackend, DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_class = TrainingProgramFilter
    search_fields = ['name', 'code', 'description']
    ordering_fields = ['name', 'start_date', 'created_at']

    def get_queryset(self):
        return super().get_queryset().filter(
            is_deleted=False,
        ).select_related('category').annotate(enrollment_count=Count('enrollments'))

    def perform_create(self, serializer):
        org = self.request.user.get_organization() if hasattr(self.request.user, 'get_organization') else None
        serializer.save(organization=org)

    @action(detail=True, methods=['post'])
    def enroll(self, request, pk=None):
        """Enroll an employee into a program"""
        program = self.get_object()

        employee_id = request.data.get('employee_id') or request.data.get('employee')
        employee = None
        if employee_id:
            from apps.employees.models import Employee
            # SECURITY: Restrict employee lookup to same organization
            org = getattr(request, 'organization', None)
            employee = Employee.objects.filter(
                id=employee_id,
                **(({'organization': org} if org else {}))
            ).first()
        else:
            employee = getattr(request.user, 'employee', None)

        if not employee:
            return Response(
                {'success': False, 'message': 'Employee not found or not linked to user'},
                status=status.HTTP_400_BAD_REQUEST
            )

        enrollment, created = TrainingEnrollment.objects.get_or_create(
            program=program,
            employee=employee,
            defaults={
                'organization': employee.organization if hasattr(employee, 'organization') else None,
                'assigned_by': getattr(request.user, 'employee', None),
                'due_date': request.data.get('due_date') or program.enrollment_deadline
            }
        )

        if not created:
            return Response(
                {'success': False, 'message': 'Employee already enrolled'},
                status=status.HTTP_400_BAD_REQUEST
            )

        return Response(
            {'success': True, 'data': TrainingEnrollmentSerializer(enrollment).data},
            status=status.HTTP_201_CREATED
        )


class TrainingMaterialViewSet(OrganizationViewSetMixin, viewsets.ModelViewSet):
    """Manage training materials"""
    queryset = TrainingMaterial.objects.none()
    serializer_class = TrainingMaterialSerializer
    permission_classes = [IsAuthenticated, TrainingTenantPermission, TrainingManagePermission]
    
    def get_queryset(self):
        return super().get_queryset().filter(
            is_deleted=False,
        ).select_related('program')
    parser_classes = [MultiPartParser, FormParser]
    filter_backends = [OrganizationFilterBackend, DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_class = TrainingMaterialFilter
    search_fields = ['title', 'description']
    ordering_fields = ['order', 'created_at']

    def perform_create(self, serializer):
        org = self.request.user.get_organization() if hasattr(self.request.user, 'get_organization') else None
        serializer.save(
            organization=org,
            uploaded_by=getattr(self.request.user, 'employee', None)
        )


class TrainingEnrollmentViewSet(OrganizationViewSetMixin, viewsets.ModelViewSet):
    """Manage enrollments and progress"""
    queryset = TrainingEnrollment.objects.none()
    serializer_class = TrainingEnrollmentSerializer
    permission_classes = [IsAuthenticated, TrainingTenantPermission, BranchPermission]
    filter_backends = [BranchFilterBackend, DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_class = TrainingEnrollmentFilter
    search_fields = ['program__name', 'employee__user__first_name', 'employee__user__last_name']
    ordering_fields = ['enrolled_at', 'completed_at', 'created_at']

    def get_queryset(self):
        queryset = super().get_queryset().filter(is_deleted=False).select_related('program', 'employee')

        if self.request.user.is_superuser or self.request.user.is_org_admin or self.request.user.is_organization_admin():
            return queryset

        employee = getattr(self.request, 'employee', None)
        if employee:
            return queryset.filter(employee=employee)

        return queryset.none()

    def perform_create(self, serializer):
        org = self.request.user.get_organization() if hasattr(self.request.user, 'get_organization') else None
        serializer.save(organization=org)

    @action(detail=True, methods=['post'])
    def start(self, request, pk=None):
        enrollment = self.get_object()
        if enrollment.status == TrainingEnrollment.STATUS_COMPLETED:
            return Response({'success': False, 'message': 'Already completed'}, status=status.HTTP_400_BAD_REQUEST)

        enrollment.status = TrainingEnrollment.STATUS_IN_PROGRESS
        if not enrollment.started_at:
            enrollment.started_at = timezone.now()
        enrollment.save(update_fields=['status', 'started_at'])
        return Response({'success': True, 'data': TrainingEnrollmentSerializer(enrollment).data})

    @action(detail=True, methods=['post'])
    def progress(self, request, pk=None):
        enrollment = self.get_object()
        progress = request.data.get('progress_percent')
        if progress is None:
            return Response({'success': False, 'message': 'progress_percent is required'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            progress_val = int(progress)
        except (TypeError, ValueError):
            return Response({'success': False, 'message': 'Invalid progress_percent'}, status=status.HTTP_400_BAD_REQUEST)

        enrollment.progress_percent = max(0, min(100, progress_val))
        if enrollment.progress_percent > 0 and enrollment.status == TrainingEnrollment.STATUS_ENROLLED:
            enrollment.status = TrainingEnrollment.STATUS_IN_PROGRESS
            if not enrollment.started_at:
                enrollment.started_at = timezone.now()
        enrollment.save(update_fields=['progress_percent', 'status', 'started_at'])
        return Response({'success': True, 'data': TrainingEnrollmentSerializer(enrollment).data})

    @action(detail=True, methods=['post'])
    def complete(self, request, pk=None):
        enrollment = self.get_object()
        if enrollment.status == TrainingEnrollment.STATUS_COMPLETED:
            return Response({'success': False, 'message': 'Already completed'}, status=status.HTTP_400_BAD_REQUEST)

        enrollment.status = TrainingEnrollment.STATUS_COMPLETED
        enrollment.completed_at = timezone.now()
        enrollment.progress_percent = 100
        if request.data.get('score') is not None:
            enrollment.score = request.data.get('score')
        if request.FILES.get('certificate_file'):
            enrollment.certificate_file = request.FILES['certificate_file']
        enrollment.save()

        completion, _ = TrainingCompletion.objects.get_or_create(
            enrollment=enrollment,
            defaults={
                'organization': enrollment.organization,
                'score': enrollment.score,
                'feedback': request.data.get('feedback', ''),
                'certificate_file': enrollment.certificate_file
            }
        )

        return Response({
            'success': True,
            'data': TrainingEnrollmentSerializer(enrollment).data,
            'completion': TrainingCompletionSerializer(completion).data
        })

    @action(detail=True, methods=['post'])
    def cancel(self, request, pk=None):
        enrollment = self.get_object()
        enrollment.status = TrainingEnrollment.STATUS_CANCELLED
        enrollment.save(update_fields=['status'])
        return Response({'success': True, 'data': TrainingEnrollmentSerializer(enrollment).data})


class TrainingCompletionViewSet(OrganizationViewSetMixin, viewsets.ModelViewSet):
    """View training completion records"""
    queryset = TrainingCompletion.objects.none()
    serializer_class = TrainingCompletionSerializer
    permission_classes = [IsAuthenticated, TrainingTenantPermission, BranchPermission]
    filter_backends = [BranchFilterBackend, DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_class = TrainingCompletionFilter
    search_fields = ['enrollment__program__name', 'enrollment__employee__user__first_name', 'enrollment__employee__user__last_name']
    ordering_fields = ['completed_at', 'created_at']

    def get_queryset(self):
        queryset = super().get_queryset().filter(is_deleted=False).select_related('enrollment', 'enrollment__program', 'enrollment__employee')

        if self.request.user.is_superuser or self.request.user.is_org_admin or self.request.user.is_organization_admin():
            return queryset

        employee = getattr(self.request, 'employee', None)
        if employee:
            return queryset.filter(enrollment__employee=employee)

        return queryset.none()

    def perform_create(self, serializer):
        org = self.request.user.get_organization() if hasattr(self.request.user, 'get_organization') else None
        serializer.save(organization=org)
