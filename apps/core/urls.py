"""
Core URLs
"""

from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    AnnouncementViewSet,
    AuditLogViewSet,
    DomainViewSet,
    FeatureFlagViewSet,
    OrganizationSettingsViewSet,
    OrganizationViewSet,
)

router = DefaultRouter()
router.register(r'organizations', OrganizationViewSet, basename='organization')
router.register('domains', DomainViewSet, basename='organization-domain')
router.register('announcements', AnnouncementViewSet, basename='announcement')
router.register('settings', OrganizationSettingsViewSet, basename='organization-settings')
router.register('flags', FeatureFlagViewSet, basename='feature-flag')
router.register('audit', AuditLogViewSet, basename='audit-log')

urlpatterns = [
    path('', include(router.urls)),
]
