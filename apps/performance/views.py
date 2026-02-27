"""
Performance ViewSets with Branch Filtering
"""

from rest_framework import viewsets, filters, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django_filters.rest_framework import DjangoFilterBackend

from .models import (
    PerformanceCycle, OKRObjective, KeyResult, PerformanceReview, ReviewFeedback,
    KeyResultArea, EmployeeKRA, KPI, Competency, EmployeeCompetency, TrainingRecommendation
)
from .serializers import (
    PerformanceCycleSerializer, OKRObjectiveSerializer, KeyResultSerializer,
    PerformanceReviewSerializer, ReviewFeedbackSerializer,
    KeyResultAreaSerializer, EmployeeKRASerializer, KPISerializer,
    CompetencySerializer, EmployeeCompetencySerializer, TrainingRecommendationSerializer
)
from apps.core.permissions import FilterByPermissionMixin
from apps.core.tenant_guards import OrganizationViewSetMixin
from .permissions import PerformanceTenantPermission
from apps.core.permissions_branch import BranchFilterBackend, BranchPermission
from .filters import (
    PerformanceCycleFilter, OKRObjectiveFilter, KeyResultFilter,
    PerformanceReviewFilter, ReviewFeedbackFilter, KeyResultAreaFilter,
    EmployeeKRAFilter, KPIFilter, CompetencyFilter, EmployeeCompetencyFilter,
    TrainingRecommendationFilter,
)


class PerformanceCycleViewSet(OrganizationViewSetMixin, viewsets.ModelViewSet):
    """
    Performance Cycles - Organization-scoped (no branch filtering)
    Cycles are shared across all branches in an organization
    """
    queryset = PerformanceCycle.objects.none()
    serializer_class = PerformanceCycleSerializer

    def get_queryset(self):
        queryset = super().get_queryset()
        org = getattr(self.request, 'organization', None)
        if org:
            queryset = queryset.filter(organization=org)
        return queryset
    permission_classes = [IsAuthenticated, PerformanceTenantPermission]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_class = PerformanceCycleFilter
    search_fields = ['name']

    @action(detail=True, methods=['post'])
    def activate(self, request, pk=None):
        """Activate a performance cycle"""
        cycle = self.get_object()
        cycle.status = 'active'
        cycle.save()
        return Response(self.get_serializer(cycle).data)

    @action(detail=True, methods=['post'])
    def close(self, request, pk=None):
        """Close a performance cycle"""
        cycle = self.get_object()
        cycle.status = 'closed'
        cycle.save()
        return Response(self.get_serializer(cycle).data)

    @action(detail=False, methods=['get'])
    def current(self, request):
        """Get current active cycle"""
        cycle = self.get_queryset().filter(status='active').first()
        if cycle:
            return Response(self.get_serializer(cycle).data)
        return Response({'error': 'No active cycle found'}, status=status.HTTP_404_NOT_FOUND)


class OKRObjectiveViewSet(OrganizationViewSetMixin, FilterByPermissionMixin, viewsets.ModelViewSet):
    """
    OKR Objectives - Branch-filtered via employee relationship
    """
    queryset = OKRObjective.objects.none()
    serializer_class = OKRObjectiveSerializer
    permission_classes = [IsAuthenticated, PerformanceTenantPermission, BranchPermission]
    filter_backends = [BranchFilterBackend, DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_class = OKRObjectiveFilter
    search_fields = ['title', 'description']
    scope_field = 'employee'

    def get_queryset(self):
        """Filter by employee's branch"""
        queryset = super().get_queryset().select_related('employee', 'cycle')
        
        # Organization filter
        org = getattr(self.request, 'organization', None)
        if org:
            queryset = queryset.filter(organization=org)
            
        if not self.request.user.is_superuser:
            # Filter through employee's branch
            queryset = queryset.filter(
                employee__branch__in=self._get_user_branches()
            )
        return queryset

    def _get_user_branches(self):
        """Get user's accessible branches"""
        from apps.authentication.models_hierarchy import BranchUser
        return BranchUser.objects.filter(
            user=self.request.user, is_active=True
        ).values_list('branch_id', flat=True)

    @action(detail=False, methods=['get'])
    def my_objectives(self, request):
        """Get current user's objectives"""
        queryset = self.get_queryset().filter(employee__user=request.user)
        cycle_id = request.query_params.get('cycle')
        if cycle_id:
            queryset = queryset.filter(cycle_id=cycle_id)
        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=['get'])
    def team_objectives(self, request):
        """Get objectives for employees reporting to current user"""
        try:
            reporting_employees = request.user.employee.direct_reports.all()
        except Exception:
            return Response([])
        
        queryset = self.get_queryset().filter(employee__in=reporting_employees)
        cycle_id = request.query_params.get('cycle')
        if cycle_id:
            queryset = queryset.filter(cycle_id=cycle_id)
        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)

    @action(detail=True, methods=['post'])
    def update_progress(self, request, pk=None):
        """Update objective progress"""
        objective = self.get_object()
        progress = request.data.get('progress')
        if progress is not None:
            objective.progress = progress
            if int(progress) >= 100:
                objective.status = 'completed'
            elif int(progress) > 0:
                objective.status = 'in_progress'
            objective.save()
            return Response(self.get_serializer(objective).data)
        return Response({'error': 'progress not provided'}, status=status.HTTP_400_BAD_REQUEST)

class KeyResultViewSet(OrganizationViewSetMixin, viewsets.ModelViewSet):
    """
    Key Results - Branch-filtered via objective's employee
    """
    queryset = KeyResult.objects.none()
    serializer_class = KeyResultSerializer
    permission_classes = [IsAuthenticated, PerformanceTenantPermission, BranchPermission]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_class = KeyResultFilter

    def get_queryset(self):
        """Filter by employee's branch through objective"""
        queryset = super().get_queryset().select_related('objective', 'objective__employee')
        
        org = getattr(self.request, 'organization', None)
        if org:
            queryset = queryset.filter(organization=org)
            
        if not self.request.user.is_superuser:
            from apps.authentication.models_hierarchy import BranchUser
            branch_ids = BranchUser.objects.filter(
                user=self.request.user, is_active=True
            ).values_list('branch_id', flat=True)
            queryset = queryset.filter(objective__employee__branch__in=branch_ids)
        return queryset

    @action(detail=True, methods=['post'])
    def update_value(self, request, pk=None):
        """Update key result current value"""
        kr = self.get_object()
        current_value = request.data.get('current_value')
        if current_value is not None:
            kr.current_value = current_value
            # Auto-calculate progress
            if kr.target_value and float(kr.target_value) > 0:
                kr.progress = min(100, int((float(current_value) / float(kr.target_value)) * 100))
            kr.save()
            return Response(self.get_serializer(kr).data)
        return Response({'error': 'current_value required'}, status=status.HTTP_400_BAD_REQUEST)


class PerformanceReviewViewSet(OrganizationViewSetMixin, FilterByPermissionMixin, viewsets.ModelViewSet):
    """
    Performance Reviews - Branch-filtered via employee
    """
    queryset = PerformanceReview.objects.none()
    serializer_class = PerformanceReviewSerializer
    permission_classes = [IsAuthenticated, PerformanceTenantPermission, BranchPermission]
    filter_backends = [BranchFilterBackend, DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_class = PerformanceReviewFilter
    scope_field = 'employee'

    def get_queryset(self):
        """Filter by employee's branch"""
        queryset = super().get_queryset()
        if not self.request.user.is_superuser:
            from apps.authentication.models_hierarchy import BranchUser
            branch_ids = BranchUser.objects.filter(
                user=self.request.user, is_active=True
            ).values_list('branch_id', flat=True)
            queryset = queryset.filter(employee__branch__in=branch_ids)
        return queryset

    @action(detail=False, methods=['get'])
    def my_reviews(self, request):
        """Get current user's reviews"""
        queryset = self.get_queryset().filter(employee__user=request.user)
        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=['get'])
    def team_reviews(self, request):
        """Get reviews for direct reports"""
        try:
            reporting_employees = request.user.employee.direct_reports.all()
        except Exception:
            return Response([])
        
        queryset = self.get_queryset().filter(employee__in=reporting_employees)
        cycle_id = request.query_params.get('cycle')
        if cycle_id:
            queryset = queryset.filter(cycle_id=cycle_id)
        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=['get'])
    def pending_reviews(self, request):
        """Get reviews pending manager action"""
        try:
            reporting_employees = request.user.employee.direct_reports.all()
        except Exception:
            return Response([])
        
        queryset = self.get_queryset().filter(
            employee__in=reporting_employees,
            status='manager_review'
        )
        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)

    @action(detail=True, methods=['post'])
    def submit_self_review(self, request, pk=None):
        """Submit self-review"""
        review = self.get_object()
        review.self_rating = request.data.get('self_rating')
        review.self_comments = request.data.get('self_comments')
        review.status = 'manager_review'
        review.save()
        return Response(self.get_serializer(review).data)

    @action(detail=True, methods=['post'])
    def submit_manager_review(self, request, pk=None):
        """Submit manager review"""
        review = self.get_object()
        review.manager_rating = request.data.get('manager_rating')
        review.manager_comments = request.data.get('manager_comments')
        review.final_rating = request.data.get('final_rating', review.manager_rating)
        review.status = 'completed'
        review.save()
        return Response(self.get_serializer(review).data)

    @action(detail=True, methods=['post'], url_path='manager_review')
    def manager_review(self, request, pk=None):
        """Compatibility alias for submit_manager_review."""
        return self.submit_manager_review(request, pk=pk)


class ReviewFeedbackViewSet(OrganizationViewSetMixin, viewsets.ModelViewSet):
    """Review Feedback - 360 degree feedback"""
    queryset = ReviewFeedback.objects.none()
    serializer_class = ReviewFeedbackSerializer
    permission_classes = [IsAuthenticated, PerformanceTenantPermission]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_class = ReviewFeedbackFilter

    def get_queryset(self):
        queryset = super().get_queryset()
        org = getattr(self.request, 'organization', None)
        if org:
            queryset = queryset.filter(organization=org)
        return queryset


class KeyResultAreaViewSet(OrganizationViewSetMixin, viewsets.ModelViewSet):
    """
    Key Result Areas - Organization-scoped templates
    """
    queryset = KeyResultArea.objects.none()
    serializer_class = KeyResultAreaSerializer
    permission_classes = [IsAuthenticated, PerformanceTenantPermission]

    def get_queryset(self):
        queryset = super().get_queryset()
        org = getattr(self.request, 'organization', None)
        if org:
            queryset = queryset.filter(organization=org)
        return queryset
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_class = KeyResultAreaFilter
    search_fields = ['name', 'code']


class EmployeeKRAViewSet(OrganizationViewSetMixin, FilterByPermissionMixin, viewsets.ModelViewSet):
    """
    Employee KRAs - Branch-filtered via employee
    """
    queryset = EmployeeKRA.objects.none()
    serializer_class = EmployeeKRASerializer
    permission_classes = [IsAuthenticated, PerformanceTenantPermission, BranchPermission]
    filter_backends = [BranchFilterBackend, DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_class = EmployeeKRAFilter
    scope_field = 'employee'

    def get_queryset(self):
        """Filter by employee's branch"""
        queryset = super().get_queryset()
        if not self.request.user.is_superuser:
            from apps.authentication.models_hierarchy import BranchUser
            branch_ids = BranchUser.objects.filter(
                user=self.request.user, is_active=True
            ).values_list('branch_id', flat=True)
            queryset = queryset.filter(employee__branch__in=branch_ids)
        return queryset

    @action(detail=False, methods=['get'])
    def my_kras(self, request):
        cycle_id = request.query_params.get('cycle')
        queryset = self.get_queryset().filter(employee__user=request.user)
        if cycle_id:
            queryset = queryset.filter(cycle_id=cycle_id)
        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=['get'])
    def team_kras(self, request):
        """Get KRAs for reporting employees"""
        cycle_id = request.query_params.get('cycle')
        
        try:
            # Get employees reporting to current user
            reporting_employees = request.user.employee.direct_reports.all()
        except Exception:
            # User might not have an employee profile
            return Response([])

        queryset = self.get_queryset().filter(employee__in=reporting_employees)
        if cycle_id:
            queryset = queryset.filter(cycle_id=cycle_id)
            
        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)

    @action(detail=True, methods=['post'])
    def self_rate(self, request, pk=None):
        instance = self.get_object()
        self_rating = request.data.get('self_rating')
        summary = request.data.get('achievement_summary')
        
        if self_rating:
            instance.self_rating = self_rating
            instance.achievement_summary = summary
            instance.save()
            return Response(self.get_serializer(instance).data)
        return Response({'error': 'Rating required'}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=['post'])
    def manager_rate(self, request, pk=None):
        instance = self.get_object()
        manager_rating = request.data.get('manager_rating')
        comments = request.data.get('comments')
        
        if manager_rating:
            instance.manager_rating = manager_rating
            instance.final_rating = manager_rating # Auto-set final rating for now
            if comments:
                instance.comments = comments
            instance.save()
            return Response(self.get_serializer(instance).data)
        return Response({'error': 'Rating required'}, status=status.HTTP_400_BAD_REQUEST)

class KPIViewSet(OrganizationViewSetMixin, FilterByPermissionMixin, viewsets.ModelViewSet):
    queryset = KPI.objects.none()
    serializer_class = KPISerializer
    permission_classes = [IsAuthenticated, PerformanceTenantPermission]
    
    def get_queryset(self):
        queryset = super().get_queryset()
        org = getattr(self.request, 'organization', None)
        if org:
            queryset = queryset.filter(organization=org)
        return queryset
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_class = KPIFilter
    search_fields = ['name']
    scope_field = 'employee'

    @action(detail=False, methods=['get'])
    def my_kpis(self, request):
        queryset = self.get_queryset().filter(employee__user=request.user)
        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)

class CompetencyViewSet(OrganizationViewSetMixin, viewsets.ModelViewSet):
    queryset = Competency.objects.none()
    serializer_class = CompetencySerializer
    permission_classes = [IsAuthenticated, PerformanceTenantPermission]
    
    def get_queryset(self):
        queryset = super().get_queryset()
        org = getattr(self.request, 'organization', None)
        if org:
            queryset = queryset.filter(organization=org)
        return queryset
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_class = CompetencyFilter
    search_fields = ['name', 'code']

class EmployeeCompetencyViewSet(OrganizationViewSetMixin, FilterByPermissionMixin, viewsets.ModelViewSet):
    queryset = EmployeeCompetency.objects.none()
    serializer_class = EmployeeCompetencySerializer
    permission_classes = [IsAuthenticated, PerformanceTenantPermission]
    
    def get_queryset(self):
        queryset = super().get_queryset()
        org = getattr(self.request, 'organization', None)
        if org:
            queryset = queryset.filter(organization=org)
        return queryset
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_class = EmployeeCompetencyFilter
    scope_field = 'employee'

    @action(detail=False, methods=['get'])
    def my_competencies(self, request):
        cycle_id = request.query_params.get('cycle')
        queryset = self.get_queryset().filter(employee__user=request.user)
        if cycle_id:
            queryset = queryset.filter(cycle_id=cycle_id)
        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)

class TrainingRecommendationViewSet(OrganizationViewSetMixin, FilterByPermissionMixin, viewsets.ModelViewSet):
    queryset = TrainingRecommendation.objects.none()
    serializer_class = TrainingRecommendationSerializer
    permission_classes = [IsAuthenticated, PerformanceTenantPermission]
    
    def get_queryset(self):
        queryset = super().get_queryset()
        org = getattr(self.request, 'organization', None)
        if org:
            queryset = queryset.filter(organization=org)
        return queryset
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_class = TrainingRecommendationFilter
    scope_field = 'employee'

    @action(detail=False, methods=['get'])
    def my_recommendations(self, request):
        queryset = self.get_queryset().filter(employee__user=request.user)
        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)
