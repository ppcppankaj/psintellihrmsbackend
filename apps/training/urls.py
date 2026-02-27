"""Training URLs"""
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    TrainingCategoryViewSet,
    TrainingProgramViewSet,
    TrainingMaterialViewSet,
    TrainingEnrollmentViewSet,
    TrainingCompletionViewSet,
)

router = DefaultRouter()
router.register(r'categories', TrainingCategoryViewSet, basename='training-categories')
router.register(r'programs', TrainingProgramViewSet, basename='training-programs')
router.register(r'materials', TrainingMaterialViewSet, basename='training-materials')
router.register(r'enrollments', TrainingEnrollmentViewSet, basename='training-enrollments')
router.register(r'completions', TrainingCompletionViewSet, basename='training-completions')

urlpatterns = [
    path('', include(router.urls)),
]
