"""
Asset Management URLs
"""

from django.urls import path, include
from rest_framework.routers import DefaultRouter

from .views import (
    AssetCategoryViewSet, AssetViewSet, AssetAssignmentViewSet,
    AssetMaintenanceViewSet, AssetRequestViewSet
)

router = DefaultRouter()
router.register(r'categories', AssetCategoryViewSet, basename='asset-categories')
router.register(r'assets', AssetViewSet, basename='assets')
router.register(r'assignments', AssetAssignmentViewSet, basename='asset-assignments')
router.register(r'maintenance', AssetMaintenanceViewSet, basename='asset-maintenance')
router.register(r'requests', AssetRequestViewSet, basename='asset-requests')

urlpatterns = [
    path('', include(router.urls)),
]
