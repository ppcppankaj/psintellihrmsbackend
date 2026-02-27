"""
Workflow ViewSets with Branch Filtering
"""

from rest_framework import viewsets, status, filters, permissions
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework.exceptions import ValidationError as DRFValidationError
from django_filters.rest_framework import DjangoFilterBackend
from django.db.models import Q
from django.core.exceptions import ValidationError as DjangoValidationError

from .models import WorkflowDefinition, WorkflowInstance, WorkflowAction, WorkflowStep
from .serializers import (
    WorkflowDefinitionSerializer, WorkflowInstanceSerializer, 
    WorkflowActionSerializer, WorkflowStepSerializer, EscalateSerializer,
    WorkflowStartSerializer, WorkflowActionRequestSerializer,
)
from .services import WorkflowEngine
from .filters import (
    WorkflowDefinitionFilter, WorkflowStepFilter,
    WorkflowInstanceFilter, WorkflowActionFilter,
)
from apps.core.permissions_branch import BranchPermission
from apps.core.tenant_guards import OrganizationViewSetMixin
from .permissions import WorkflowsTenantPermission


class WorkflowStepViewSet(OrganizationViewSetMixin, viewsets.ModelViewSet):
    """Workflow Steps - Configuration (read-only for most users)"""
    queryset = WorkflowStep.objects.none()
    serializer_class = WorkflowStepSerializer
    permission_classes = [IsAuthenticated, WorkflowsTenantPermission]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_class = WorkflowStepFilter
    search_fields = ['name']
    ordering_fields = ['order', 'created_at']
    ordering = ['order']
    
    def get_queryset(self):
        return super().get_queryset().select_related('workflow')


class IsHRAdminOrReadOnly(permissions.BasePermission):
    """Allow read for authenticated, write only for HR admins/superusers."""
    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        if request.method in permissions.SAFE_METHODS:
            return True
        # Check for superuser or org admin
        if request.user.is_superuser:
            return True
        if hasattr(request.user, 'is_org_admin') and request.user.is_org_admin:
            return True
        # Check for HR admin permission
        if hasattr(request.user, 'has_permission_for'):
            return request.user.has_permission_for('workflows.manage')
        return False


class WorkflowDefinitionViewSet(OrganizationViewSetMixin, viewsets.ModelViewSet):
    """
    Workflow Definitions - Organization-scoped templates
    Defines approval chains for leave, expenses, etc.
    
    SECURITY: Read access for authenticated users, write only for HR admins.
    """
    queryset = WorkflowDefinition.objects.none()
    serializer_class = WorkflowDefinitionSerializer
    permission_classes = [IsAuthenticated, WorkflowsTenantPermission, IsHRAdminOrReadOnly]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_class = WorkflowDefinitionFilter
    search_fields = ['name', 'code']
    ordering_fields = ['name', 'entity_type', 'is_active', 'created_at']
    ordering = ['-created_at']

    @action(detail=False, methods=['get'])
    def by_entity_type(self, request):
        """Get workflow definition for a specific entity type"""
        entity_type = request.query_params.get('entity_type')
        if not entity_type:
            return Response(
                {'error': 'entity_type parameter required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        workflow = self.get_queryset().filter(
            entity_type=entity_type, is_active=True
        ).first()
        if workflow:
            return Response(self.get_serializer(workflow).data)
        return Response(
            {'error': f'No workflow defined for {entity_type}'},
            status=status.HTTP_404_NOT_FOUND
        )


class WorkflowInstanceViewSet(OrganizationViewSetMixin, viewsets.ModelViewSet):
    """
    Workflow Instances - Branch-filtered via current_approver's branch
    Tracks individual approval requests
    """
    queryset = WorkflowInstance.objects.none()
    serializer_class = WorkflowInstanceSerializer
    permission_classes = [IsAuthenticated, WorkflowsTenantPermission, BranchPermission]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_class = WorkflowInstanceFilter
    search_fields = ['entity_type']
    ordering_fields = ['status', 'entity_type', 'created_at', 'started_at', 'completed_at']
    ordering = ['-created_at']

    def create(self, request, *args, **kwargs):
        instance = self._start_instance(request)
        serializer = self.get_serializer(instance)
        return Response(serializer.data, status=status.HTTP_201_CREATED)

    @action(detail=False, methods=['post'], url_path='start')
    def start_workflow(self, request):
        """Explicit workflow start endpoint used by BPM clients."""
        instance = self._start_instance(request)
        serializer = self.get_serializer(instance)
        return Response(serializer.data, status=status.HTTP_201_CREATED)

    def get_queryset(self):
        queryset = self._get_org_queryset()
        user = self.request.user

        if user.is_superuser:
            return queryset

        organization = user.get_organization()
        if not organization:
            return queryset.none()

        branch_ids = self._get_accessible_branch_ids(user, organization)
        employee = self._get_employee(self.request)

        if not employee:
            return queryset.none()

        visibility_q = Q(current_approver=employee) | Q(current_approver__isnull=True)
        if branch_ids:
            visibility_q |= Q(current_approver__branch_id__in=branch_ids)

        return queryset.filter(visibility_q).distinct()

    def _get_employee(self, request):
        """Helper to get employee profile for current user"""
        if not hasattr(request, '_employee'):
            from apps.employees.models import Employee
            request._employee = Employee.objects.filter(user=request.user).first()
        return request._employee

    def _get_org_queryset(self):
        """Base queryset scoped to user's organization (or all for superusers)."""
        queryset = WorkflowInstance.objects.select_related(
            'workflow', 'current_approver'
        ).prefetch_related('steps', 'steps__approver')
        user = self.request.user

        if user.is_superuser:
            return queryset

        organization = user.get_organization()
        if not organization:
            return queryset.none()

        return queryset.filter(organization=organization)

    def _get_accessible_branch_ids(self, user, organization):
        """Return branch IDs the user can access within the organization."""
        if not organization or not getattr(user, 'is_authenticated', False):
            return []

        from apps.authentication.models_hierarchy import BranchUser

        return list(
            BranchUser.objects.filter(
                user=user,
                is_active=True,
                organization=organization
            ).values_list('branch_id', flat=True)
        )

    def _start_instance(self, request):
        serializer = WorkflowStartSerializer(data=request.data, context={'request': request})
        serializer.is_valid(raise_exception=True)
        organization = serializer.validated_data['organization']
        workflow_code = (serializer.validated_data.get('workflow_code') or '').strip()
        resolved = serializer.validated_data['resolved_entity']
        try:
            if workflow_code:
                return WorkflowEngine.start_for_code(
                    entity=resolved.instance,
                    workflow_code=workflow_code,
                    organization=organization,
                    initiator=self._get_employee(request),
                )
            return WorkflowEngine.start(
                organization=organization,
                entity_type=serializer.validated_data['entity_type'],
                entity_id=serializer.validated_data['entity_id'],
                initiator_user=request.user,
            )
        except DjangoValidationError as exc:
            detail = getattr(exc, 'message_dict', None) or exc.messages
            raise DRFValidationError(detail)

    def _perform_action(self, request, instance, *, action_override=None, data_override=None):
        # ── S7: Workflow approval hardening ──────────────────────────────
        # 1. Verify instance.organization == request.organization
        request_org = getattr(request, 'organization', None)
        if request_org and instance.organization_id:
            if str(instance.organization_id) != str(request_org.id):
                from rest_framework.exceptions import PermissionDenied
                raise PermissionDenied(
                    'Cannot act on workflow instance from a different organization.'
                )

        actor = self._get_employee(request)
        if not actor:
            return Response({"error": "No employee record found"}, status=status.HTTP_400_BAD_REQUEST)

        # 2. Verify actor is the assigned approver (non-superusers only)
        if not request.user.is_superuser:
            current_approver = getattr(instance, 'current_approver', None)
            if current_approver and current_approver.id != actor.id:
                from rest_framework.exceptions import PermissionDenied
                raise PermissionDenied(
                    'You are not the assigned approver for this workflow instance.'
                )
        # ── End S7 ───────────────────────────────────────────────────────

        payload_data = self._build_action_data(request, action_override, data_override)
        serializer = WorkflowActionRequestSerializer(
            data=payload_data,
            context=self._action_serializer_context(request, instance),
        )
        serializer.is_valid(raise_exception=True)

        try:
            WorkflowEngine.take_action(instance, actor=actor, payload=serializer.to_action_payload())
        except DjangoValidationError as exc:
            detail = getattr(exc, 'message_dict', None) or exc.messages
            raise DRFValidationError(detail)

        instance.refresh_from_db()
        return Response(self.get_serializer(instance).data)

    def _build_action_data(self, request, action_override, data_override):
        if hasattr(request.data, 'dict'):
            data = request.data.dict()
        else:
            data = dict(request.data)
        if data_override:
            data.update({k: v for k, v in data_override.items() if v is not None})
        if action_override:
            data['action'] = action_override
        return data

    def _action_serializer_context(self, request, instance):
        branch_ids = None
        if not request.user.is_superuser:
            branch_ids = self._get_accessible_branch_ids(request.user, instance.organization)
        return {
            'request': request,
            'organization': instance.organization,
            'branch_ids': branch_ids,
        }

    @action(detail=True, methods=['post'])
    def approve(self, request, pk=None):
        """Approve a workflow instance"""
        instance = self.get_object()
        return self._perform_action(request, instance, action_override='approve')

    @action(detail=True, methods=['post'])
    def reject(self, request, pk=None):
        """Reject a workflow instance"""
        instance = self.get_object()
        return self._perform_action(request, instance, action_override='reject')

    @action(detail=True, methods=['post'])
    def delegate(self, request, pk=None):
        """Delegate approval to another user"""
        instance = self.get_object()
        return self._perform_action(request, instance, action_override='delegate')

    @action(detail=True, methods=['post'], url_path='action')
    def take_action(self, request, pk=None):
        """General action endpoint for approve/reject/forward/delegate operations."""
        instance = self.get_object()
        return self._perform_action(request, instance)

    @action(detail=False, methods=['get'], url_path='my-approvals')
    def my_approvals(self, request):
        """Get pending approvals for current user"""
        actor = self._get_employee(request)
        if not actor:
            return Response(
                {"error": "No employee record found"}, 
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Pending items where user is the current approver
        pending = self.get_queryset().filter(
            current_approver=actor, 
            status='in_progress'
        ).order_by('-created_at')
        
        serializer = self.get_serializer(pending, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=['get'], url_path='my_pending')
    def my_pending(self, request):
        """Alias for my_approvals - matches frontend API call"""
        return self.my_approvals(request)

    @action(detail=False, methods=['get'], url_path='my-requests')
    def my_requests(self, request):
        """Get workflow instances initiated by current user"""
        actor = self._get_employee(request)
        queryset = self._get_org_queryset()

        filters = Q(created_by=request.user)
        if actor:
            filters |= Q(workflowaction__actor=actor)

        queryset = queryset.filter(filters).distinct().order_by('-created_at')

        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)

        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=['get'])
    def stats(self, request):
        """Get approval statistics for current user"""
        actor = self._get_employee(request)
        if not actor:
            return Response(
                {"error": "No employee record found"}, 
                status=status.HTTP_400_BAD_REQUEST
            )
        
        from django.utils import timezone
        from datetime import timedelta
        user_org = request.user.get_organization()
        
        today_start = timezone.now().replace(hour=0, minute=0, second=0, microsecond=0)
        queryset = self.get_queryset()
        
        # Pending count (assigned to current user and in progress)
        pending_count = queryset.filter(
            current_approver=actor, 
            status='in_progress'
        ).count()
        
        # Actions taken today
        today_actions = WorkflowAction.objects.filter(
            actor=actor,
            created_at__gte=today_start
        )
        if user_org:
            today_actions = today_actions.filter(organization=user_org)
        approved_today = today_actions.filter(action='approved').count()
        rejected_today = today_actions.filter(action='rejected').count()
        
        # Overdue (SLA exceeded) - check instances where SLA deadline has passed
        overdue_count = queryset.filter(
            current_approver=actor,
            status='in_progress',
            workflow__sla_hours__isnull=False
        ).extra(
            where=["started_at + (workflow.sla_hours || ' hours')::interval < NOW()"]
        ).count() if hasattr(queryset, 'extra') else 0
        
        # Simplified overdue calculation without complex SQL
        # Check instances older than typical SLA (e.g., 48 hours)
        sla_cutoff = timezone.now() - timedelta(hours=48)
        overdue_count = queryset.filter(
            current_approver=actor,
            status='in_progress',
            started_at__lt=sla_cutoff
        ).count()
        
        # Average turnaround (completed instances where user was approver)
        completed_instances = WorkflowAction.objects.filter(
            actor=actor,
            action__in=['approved', 'rejected'],
            instance__completed_at__isnull=False
        ).select_related('instance')
        if user_org:
            completed_instances = completed_instances.filter(organization=user_org)
        
        avg_turnaround_hours = 0
        if completed_instances.exists():
            total_hours = 0
            count = 0
            for action in completed_instances[:100]:  # Limit for performance
                if action.instance.completed_at and action.instance.started_at:
                    delta = action.instance.completed_at - action.instance.started_at
                    total_hours += delta.total_seconds() / 3600
                    count += 1
            if count > 0:
                avg_turnaround_hours = round(total_hours / count, 1)
        
        stats = {
            'pending_count': pending_count,
            'approved_today': approved_today,
            'rejected_today': rejected_today,
            'overdue_count': overdue_count,
            'avg_turnaround_hours': avg_turnaround_hours,
            # Keep legacy fields for compatibility
            'pending': pending_count,
            'approved_by_me': WorkflowAction.objects.filter(
                actor=actor,
                action='approved',
                organization=user_org
            ).count() if user_org else 0,
            'rejected_by_me': WorkflowAction.objects.filter(
                actor=actor,
                action='rejected',
                organization=user_org
            ).count() if user_org else 0,
            'delegated_by_me': WorkflowAction.objects.filter(
                actor=actor,
                action='delegated',
                organization=user_org
            ).count() if user_org else 0,
        }
        return Response(stats)

    @action(detail=False, methods=['get'], url_path='team-requests')
    def team_requests(self, request):
        """Get workflow instances for user's subordinates"""
        actor = self._get_employee(request)
        if not actor:
            return Response([])
        
        # Get subordinates (employees who report to this user)
        from apps.employees.models import Employee
        subordinate_qs = Employee.objects.filter(
            reporting_manager=actor,
            organization=actor.organization,
            is_active=True
        )
        subordinate_ids = list(subordinate_qs.values_list('id', flat=True))
        subordinate_user_ids = list(subordinate_qs.values_list('user_id', flat=True))
        
        status_filter = request.query_params.get('status')
        base_queryset = self._get_org_queryset()
        queryset = base_queryset.filter(
            Q(created_by_id__in=subordinate_user_ids) |
            Q(workflowaction__actor_id__in=subordinate_ids)
        ).distinct()
        
        if status_filter:
            queryset = queryset.filter(status=status_filter)
        queryset = queryset.order_by('-created_at')

        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)

        limited_queryset = queryset[:50]
        serializer = self.get_serializer(limited_queryset, many=True)
        return Response({
            'results': serializer.data,
            'count': queryset.count()
        })

    @action(detail=False, methods=['get'], url_path='history')
    def workflow_history(self, request):

        """Get workflow history for current user (completed approvals)"""
        actor = self._get_employee(request)
        if not actor:
            return Response({
                'results': [],
                'count': 0
            })
        
        # Get instances where user took an action (approved, rejected, delegated)
        action_instance_ids = WorkflowAction.objects.filter(
            actor=actor,
            organization=actor.organization
        ).values_list('instance_id', flat=True).distinct()
        
        queryset = self._get_org_queryset().filter(
            id__in=action_instance_ids
        ).order_by('-completed_at', '-created_at')
        
        # Apply type filter if provided
        type_filter = request.query_params.get('type')
        if type_filter:
            queryset = queryset.filter(entity_type=type_filter)
        
        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        
        serializer = self.get_serializer(queryset, many=True)
        return Response({
            'results': serializer.data,
            'count': queryset.count()
        })

    @action(detail=True, methods=['get'])
    def history(self, request, pk=None):
        """Get approval history for a workflow instance"""
        instance = self.get_object()
        actions = WorkflowAction.objects.filter(
            instance=instance,
            organization=instance.organization
        ).select_related('actor').order_by('created_at')
        
        return Response(WorkflowActionSerializer(actions, many=True).data)
    
    @action(detail=True, methods=['post'])
    def escalate(self, request, pk=None):
        """Manually escalate a workflow instance to a higher authority"""
        instance = self.get_object()
        actor = self._get_employee(request)
        
        if not actor:
            return Response(
                {"error": "No employee record found"}, 
                status=status.HTTP_400_BAD_REQUEST
            )
        
        serializer = EscalateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        reason = serializer.validated_data['reason']
        escalate_to_id = serializer.validated_data.get('escalate_to')
        
        if instance.status != 'in_progress':
            return Response(
                {"error": "Only in-progress workflows can be escalated"},
                status=status.HTTP_400_BAD_REQUEST
            )

        target_employee = None
        if escalate_to_id:
            from apps.employees.models import Employee
            target_employee = Employee.objects.filter(
                id=escalate_to_id,
                organization=instance.organization
            ).first()
            if not target_employee:
                return Response(
                    {"error": "Escalation target not found"},
                    status=status.HTTP_404_NOT_FOUND
                )

        try:
            WorkflowEngine.escalate(
                instance=instance,
                actor=actor,
                reason=reason,
                target=target_employee
            )
        except DjangoValidationError as exc:
            detail = getattr(exc, 'message_dict', None) or exc.messages
            raise DRFValidationError(detail)

        instance.refresh_from_db()
        return Response(self.get_serializer(instance).data)
    
    @action(detail=True, methods=['post'], url_path='process-parallel')
    def process_parallel(self, request, pk=None):
        """Process parallel approval step - for steps that require multiple approvers"""
        instance = self.get_object()
        action_type = request.data.get('action', 'approved')
        comments = request.data.get('comments', '')
        
        if action_type not in ['approved', 'rejected']:
            return Response(
                {"error": "Action must be 'approved' or 'rejected'"},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        if action_type == 'rejected' and not comments:
            return Response(
                {"error": "Comments required for rejection"},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        mapped_action = 'approve' if action_type == 'approved' else 'reject'
        return self._perform_action(
            request,
            instance,
            action_override=mapped_action,
            data_override={'comments': comments}
        )


class WorkflowActionViewSet(OrganizationViewSetMixin, viewsets.ReadOnlyModelViewSet):
    """
    Workflow Actions - Read-only audit trail
    Records all approval/rejection/delegation actions
    """
    queryset = WorkflowAction.objects.none()
    serializer_class = WorkflowActionSerializer
    permission_classes = [IsAuthenticated, WorkflowsTenantPermission]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_class = WorkflowActionFilter
    search_fields = ['action', 'comments']
    ordering_fields = ['action', 'created_at']
    ordering = ['-created_at']

    def get_queryset(self):
        """Filter by user's accessible branches through actor"""
        queryset = WorkflowAction.objects.select_related(
            'instance', 'actor'
        )
        user = self.request.user
        
        if user.is_superuser:
            return queryset

        user_org = user.get_organization()
        if not user_org:
            return queryset.none()

        queryset = queryset.filter(organization=user_org)
        
        from apps.authentication.models_hierarchy import BranchUser
        branch_ids = BranchUser.objects.filter(
            user=user, is_active=True,
            organization=user_org
        ).values_list('branch_id', flat=True)
        
        return queryset.filter(actor__branch_id__in=branch_ids)
