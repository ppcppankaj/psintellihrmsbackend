"""
ABAC URLs
"""

from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    AttributeTypeViewSet, PolicyViewSet, PolicyRuleViewSet,
    UserPolicyViewSet, GroupPolicyViewSet, PolicyLogViewSet,
    RoleViewSet, PermissionViewSet, RoleAssignmentViewSet
)

router = DefaultRouter()
router.register('attribute-types', AttributeTypeViewSet, basename='attribute-type')
router.register('policies', PolicyViewSet, basename='policy')
router.register('policy-rules', PolicyRuleViewSet, basename='policy-rule')
router.register('user-policies', UserPolicyViewSet, basename='user-policy')
router.register('group-policies', GroupPolicyViewSet, basename='group-policy')
router.register('policy-logs', PolicyLogViewSet, basename='policy-log')
router.register('roles', RoleViewSet, basename='role')
router.register('permissions', PermissionViewSet, basename='permission')
router.register('user-roles', RoleAssignmentViewSet, basename='user-role')

urlpatterns = [
    path('', include(router.urls)),
]

