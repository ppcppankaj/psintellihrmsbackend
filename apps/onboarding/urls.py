"""Onboarding URL Configuration"""

from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    OnboardingTemplateViewSet, OnboardingTaskTemplateViewSet,
    EmployeeOnboardingViewSet, OnboardingTaskProgressViewSet,
    OnboardingDocumentViewSet
)

router = DefaultRouter()
router.register(r'templates', OnboardingTemplateViewSet, basename='onboarding-template')
router.register(r'task-templates', OnboardingTaskTemplateViewSet, basename='onboarding-task-template')
router.register(r'onboardings', EmployeeOnboardingViewSet, basename='employee-onboarding')
router.register(r'tasks', OnboardingTaskProgressViewSet, basename='onboarding-task')
router.register(r'documents', OnboardingDocumentViewSet, basename='onboarding-document')

urlpatterns = [
    path('', include(router.urls)),
    # Compatibility aliases for older frontend paths
    path('employee-onboardings/', EmployeeOnboardingViewSet.as_view({'get': 'list', 'post': 'create'})),
    path('employee-onboardings/<uuid:pk>/', EmployeeOnboardingViewSet.as_view({'get': 'retrieve', 'put': 'update', 'patch': 'partial_update', 'delete': 'destroy'})),
    path('employee-onboardings/initiate/', EmployeeOnboardingViewSet.as_view({'post': 'initiate'})),
    path('employee-onboardings/my_onboarding/', EmployeeOnboardingViewSet.as_view({'get': 'my_onboarding'})),
    path('employee-onboardings/my_tasks/', EmployeeOnboardingViewSet.as_view({'get': 'my_tasks'})),
    path('employee-onboardings/<uuid:pk>/summary/', EmployeeOnboardingViewSet.as_view({'get': 'summary'})),
    path('employee-onboardings/<uuid:pk>/cancel/', EmployeeOnboardingViewSet.as_view({'post': 'cancel'})),

    path('task-progress/', OnboardingTaskProgressViewSet.as_view({'get': 'list', 'post': 'create'})),
    path('task-progress/<uuid:pk>/', OnboardingTaskProgressViewSet.as_view({'get': 'retrieve', 'put': 'update', 'patch': 'partial_update', 'delete': 'destroy'})),
    path('task-progress/<uuid:pk>/complete/', OnboardingTaskProgressViewSet.as_view({'post': 'complete'})),
    path('task-progress/<uuid:pk>/skip/', OnboardingTaskProgressViewSet.as_view({'post': 'skip'})),
    path('task-progress/<uuid:pk>/start/', OnboardingTaskProgressViewSet.as_view({'post': 'start'})),
]
