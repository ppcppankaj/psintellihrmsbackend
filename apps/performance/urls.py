"""Performance URLs"""
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    PerformanceCycleViewSet, OKRObjectiveViewSet, KeyResultViewSet,
    PerformanceReviewViewSet, ReviewFeedbackViewSet,
    KeyResultAreaViewSet, EmployeeKRAViewSet, KPIViewSet,
    CompetencyViewSet, EmployeeCompetencyViewSet, TrainingRecommendationViewSet
)

router = DefaultRouter()
router.register(r'cycles', PerformanceCycleViewSet)
router.register(r'okrs', OKRObjectiveViewSet)
router.register(r'key-results', KeyResultViewSet)
router.register(r'reviews', PerformanceReviewViewSet)
router.register(r'feedback', ReviewFeedbackViewSet)
router.register(r'kras', KeyResultAreaViewSet)
router.register(r'employee-kras', EmployeeKRAViewSet)
router.register(r'kpis', KPIViewSet)
router.register(r'competencies', CompetencyViewSet)
router.register(r'employee-competencies', EmployeeCompetencyViewSet)
router.register(r'recommendations', TrainingRecommendationViewSet)

urlpatterns = [
    path('', include(router.urls)),
]
