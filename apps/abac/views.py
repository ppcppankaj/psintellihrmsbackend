"""
ABAC Views - Attribute-Based Access Control management
"""

from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.exceptions import PermissionDenied

from apps.core.context import get_current_organization
from apps.core.tenant_guards import OrganizationViewSetMixin

from .models import (
    AttributeType,
    Policy,
    PolicyLog,
    PolicyRule,
    UserPolicy,
    GroupPolicy,
    Role,
    Permission,
    RoleAssignment,
)
from .permissions import ABACPermission, IsPolicyOrgAdmin
from .serializers import (
    AttributeTypeSerializer,
    PolicySerializer,
    PolicyDetailSerializer,
    PolicyRuleSerializer,
    UserPolicySerializer,
    GroupPolicySerializer,
    PolicyLogSerializer,
    RoleSerializer,
    PermissionSerializer,
    RoleAssignmentSerializer,
)
from .services import ABACService

from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.filters import SearchFilter, OrderingFilter
from .filters import (
    AttributeTypeFilter, PolicyFilter, PolicyRuleFilter, UserPolicyFilter,
    GroupPolicyFilter, PolicyLogFilter, RoleFilter, PermissionFilter,
    RoleAssignmentFilter,
)


class TenantScopedViewMixin:
    """Utilities for enforcing organization context inside viewsets."""

    def _get_organization(self):
        org = getattr(self.request, 'organization', None) or get_current_organization()
        if not org and not self.request.user.is_superuser:
            raise PermissionDenied('Organization context required for ABAC management.')
        return org

    def _filter_by_org(self, queryset):
        org = self._get_organization()
        if org and hasattr(queryset.model, 'organization_id'):
            queryset = queryset.filter(organization=org)
        return queryset


class AttributeTypeViewSet(TenantScopedViewMixin, OrganizationViewSetMixin, viewsets.ModelViewSet):
    """ViewSet for managing attribute types"""

    queryset = AttributeType.objects.none()
    serializer_class = AttributeTypeSerializer
    permission_classes = [IsAuthenticated, IsPolicyOrgAdmin, ABACPermission]
    abac_resource_type = 'abac_attribute_type'

    def get_queryset(self):
        return super().get_queryset().filter(is_deleted=False)

    def perform_create(self, serializer):
        serializer.save(organization=self._get_organization())

    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_class = AttributeTypeFilter
    search_fields = ['name', 'code', 'description']


class PolicyViewSet(TenantScopedViewMixin, OrganizationViewSetMixin, viewsets.ModelViewSet):
    """ViewSet for managing policies"""
    
    queryset = Policy.objects.none()
    serializer_class = PolicySerializer
    permission_classes = [IsAuthenticated, IsPolicyOrgAdmin, ABACPermission]
    abac_resource_type = 'abac_policy'
    
    def get_queryset(self):
        return super().get_queryset().filter(is_deleted=False)

    def perform_create(self, serializer):
        serializer.save(organization=self._get_organization())
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_class = PolicyFilter
    search_fields = ['name', 'code', 'description']
    ordering_fields = ['priority', 'name', 'created_at']
    ordering = ['-priority', 'name']
    
    def get_serializer_class(self):
        if self.action == 'retrieve':
            return PolicyDetailSerializer
        return PolicySerializer
    
    @action(detail=True, methods=['post'])
    def add_rule(self, request, pk=None):
        """Add a rule to this policy"""
        policy = self.get_object()
        serializer = PolicyRuleSerializer(data=request.data)
        
        if serializer.is_valid():
            serializer.save(policy=policy, organization=policy.organization)
            return Response({
                'success': True,
                'data': serializer.data
            }, status=status.HTTP_201_CREATED)
        
        return Response({
            'success': False,
            'errors': serializer.errors
        }, status=status.HTTP_400_BAD_REQUEST)
    
    @action(detail=True, methods=['delete'], url_path='remove-rule/(?P<rule_id>[^/.]+)')
    def remove_rule(self, request, pk=None, rule_id=None):
        """Remove a rule from this policy"""
        policy = self.get_object()
        
        try:
            rule = PolicyRule.objects.get(id=rule_id, policy=policy)
            rule.delete()
            return Response({'success': True, 'message': 'Rule removed'})
        except PolicyRule.DoesNotExist:
            return Response(
                {'success': False, 'message': 'Rule not found'},
                status=status.HTTP_404_NOT_FOUND
            )
    
    @action(detail=False, methods=['post'])
    def check_access(self, request):
        """Check if current user has access based on policies"""
        resource_type = request.data.get('resource_type')
        action = request.data.get('action')
        resource_attrs = request.data.get('resource_attrs', {})
        resource_id = request.data.get('resource_id')
        
        if not resource_type or not action:
            return Response({
                'success': False,
                'message': 'resource_type and action are required'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        decision = ABACService.evaluate_access(
            user=request.user,
            resource_type=resource_type,
            resource_id=resource_id,
            action=action,
            resource_attributes=resource_attrs,
        )

        return Response({
            'success': True,
            'has_access': decision.allowed,
            'reason': decision.reason,
            'policies': decision.evaluated_policies,
            'user': request.user.email,
            'resource_type': resource_type,
            'action': action,
        })


class PolicyRuleViewSet(TenantScopedViewMixin, OrganizationViewSetMixin, viewsets.ModelViewSet):
    """ViewSet for managing policy rules"""
    
    queryset = PolicyRule.objects.none()
    serializer_class = PolicyRuleSerializer
    permission_classes = [IsAuthenticated, IsPolicyOrgAdmin, ABACPermission]
    abac_resource_type = 'abac_policy_rule'
    
    def get_queryset(self):
        return super().get_queryset().filter(is_deleted=False)

    def perform_create(self, serializer):
        org = self._get_organization()
        policy = serializer.validated_data.get('policy')
        if policy and str(policy.organization_id) != str(org.id):
            raise PermissionDenied('Policy must belong to this organization.')
        serializer.save(organization=org)
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_class = PolicyRuleFilter
    search_fields = ['attribute_path']


class UserPolicyViewSet(TenantScopedViewMixin, OrganizationViewSetMixin, viewsets.ModelViewSet):
    """ViewSet for managing user policy assignments"""
    
    queryset = UserPolicy.objects.none()
    serializer_class = UserPolicySerializer
    permission_classes = [IsAuthenticated, IsPolicyOrgAdmin, ABACPermission]
    abac_resource_type = 'abac_user_policy'
    
    def get_queryset(self):
        return super().get_queryset().filter(is_deleted=False)
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_class = UserPolicyFilter
    search_fields = ['user__email', 'policy__name']
    
    def perform_create(self, serializer):
        serializer.save(
            assigned_by=self.request.user,
            organization=self._get_organization(),
        )
    
    @action(detail=False, methods=['post'])
    def bulk_assign(self, request):
        """Assign policies to multiple users"""
        user_ids = request.data.get('user_ids', [])
        policy_ids = request.data.get('policy_ids', [])
        
        if not user_ids or not policy_ids:
            return Response({
                'success': False,
                'message': 'user_ids and policy_ids are required'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        org = self._get_organization()
        created = []
        for user_id in user_ids:
            for policy_id in policy_ids:
                user_policy, was_created = UserPolicy.objects.get_or_create(
                    user_id=user_id,
                    policy_id=policy_id,
                    organization=org,
                    defaults={'assigned_by': request.user, 'is_active': True}
                )
                if was_created:
                    created.append(user_policy)
        
        serializer = self.get_serializer(created, many=True)
        return Response({
            'success': True,
            'created_count': len(created),
            'data': serializer.data
        }, status=status.HTTP_201_CREATED)


class GroupPolicyViewSet(TenantScopedViewMixin, OrganizationViewSetMixin, viewsets.ModelViewSet):
    """ViewSet for managing group policy assignments"""
    
    queryset = GroupPolicy.objects.none()
    serializer_class = GroupPolicySerializer
    permission_classes = [IsAuthenticated, IsPolicyOrgAdmin, ABACPermission]
    abac_resource_type = 'abac_group_policy'
    
    def get_queryset(self):
        return super().get_queryset().filter(is_deleted=False)
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_class = GroupPolicyFilter
    search_fields = ['name', 'group_value']

    def perform_create(self, serializer):
        serializer.save(organization=self._get_organization())


class PolicyLogViewSet(TenantScopedViewMixin, OrganizationViewSetMixin, viewsets.ReadOnlyModelViewSet):
    """ViewSet for viewing policy evaluation logs (read-only)"""
    
    queryset = PolicyLog.objects.none()
    serializer_class = PolicyLogSerializer
    permission_classes = [IsAuthenticated, ABACPermission]
    abac_resource_type = 'abac_policy_log'
    
    def get_queryset(self):
        return super().get_queryset()
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_class = PolicyLogFilter
    search_fields = ['user__email', 'resource_type', 'resource_id']
    ordering_fields = ['evaluated_at']
    ordering = ['-evaluated_at']
    
    @action(detail=False, methods=['get'])
    def my_logs(self, request):
        """Get logs for current user"""
        logs = self.get_queryset().filter(user=request.user)
        page = self.paginate_queryset(logs)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        
        serializer = self.get_serializer(logs, many=True)
        return Response(serializer.data)
    
    @action(detail=False, methods=['get'])
    def denials(self, request):
        """Get all access denials"""
        denials = self.get_queryset().filter(result=False)
        page = self.paginate_queryset(denials)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        
        serializer = self.get_serializer(denials, many=True)
        return Response(serializer.data)


class RoleViewSet(TenantScopedViewMixin, OrganizationViewSetMixin, viewsets.ModelViewSet):
    """ViewSet for managing roles"""
    
    queryset = Role.objects.none()
    serializer_class = RoleSerializer
    permission_classes = [IsAuthenticated, IsPolicyOrgAdmin, ABACPermission]
    abac_resource_type = 'abac_role'
    
    def get_queryset(self):
        return super().get_queryset().filter(is_deleted=False)
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_class = RoleFilter
    search_fields = ['name', 'code', 'description']
    ordering = ['name']

    def perform_create(self, serializer):
        serializer.save(organization=self._get_organization())


class PermissionViewSet(TenantScopedViewMixin, OrganizationViewSetMixin, viewsets.ModelViewSet):
    """ViewSet for managing permissions"""
    
    queryset = Permission.objects.none()
    serializer_class = PermissionSerializer
    permission_classes = [IsAuthenticated, IsPolicyOrgAdmin, ABACPermission]
    abac_resource_type = 'abac_permission'
    
    def get_queryset(self):
        return super().get_queryset().filter(is_deleted=False)
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_class = PermissionFilter
    search_fields = ['name', 'code', 'description', 'module']
    ordering = ['module', 'name']

    def perform_create(self, serializer):
        serializer.save(organization=self._get_organization())


class RoleAssignmentViewSet(TenantScopedViewMixin, OrganizationViewSetMixin, viewsets.ModelViewSet):
    """ViewSet for managing user role assignments"""
    
    queryset = RoleAssignment.objects.none()
    serializer_class = RoleAssignmentSerializer
    permission_classes = [IsAuthenticated, ABACPermission]
    abac_resource_type = 'abac_role_assignment'
    
    def get_queryset(self):
        return super().get_queryset().filter(is_deleted=False)
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_class = RoleAssignmentFilter
    search_fields = ['user__email', 'role__name']
    ordering = ['-assigned_at']
    
    def perform_create(self, serializer):
        serializer.save(
            assigned_by=self.request.user,
            organization=self._get_organization(),
        )

