"""Workflows URLs"""
from django.urls import path, include
from rest_framework.routers import DefaultRouter

from .views import WorkflowDefinitionViewSet, WorkflowInstanceViewSet, WorkflowStepViewSet, WorkflowActionViewSet

router = DefaultRouter()
router.register(r'definitions', WorkflowDefinitionViewSet)
router.register(r'steps', WorkflowStepViewSet)
router.register(r'instances', WorkflowInstanceViewSet)
router.register(r'actions', WorkflowActionViewSet)

urlpatterns = [
    path('', include(router.urls)),
]

