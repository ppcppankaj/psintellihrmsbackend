"""AI URLs"""
from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import AIInferenceView, AIModelVersionViewSet, AIPredictionViewSet

router = DefaultRouter()
router.register(r'models', AIModelVersionViewSet)
router.register(r'predictions', AIPredictionViewSet)

urlpatterns = [
    path('', include(router.urls)),
    path('predict/', AIInferenceView.as_view(), name='ai-predict'),
]
