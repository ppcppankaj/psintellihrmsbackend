"""Compliance URLs"""
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    DataRetentionPolicyViewSet,
    ConsentRecordViewSet,
    LegalHoldViewSet,
    DataSubjectRequestViewSet,
    AuditExportRequestViewSet,
    RetentionExecutionViewSet,
)

router = DefaultRouter()
router.register(r'retention', DataRetentionPolicyViewSet)
router.register(r'consents', ConsentRecordViewSet)
router.register(r'legal-holds', LegalHoldViewSet)
router.register(r'dsar', DataSubjectRequestViewSet)
router.register(r'audit-exports', AuditExportRequestViewSet)
router.register(r'retention-executions', RetentionExecutionViewSet)

urlpatterns = [
    path('', include(router.urls)),
]
