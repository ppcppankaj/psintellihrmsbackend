"""Integration URLs"""
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import IntegrationViewSet, WebhookViewSet, APIKeyViewSet

router = DefaultRouter()
router.register(r'external', IntegrationViewSet)
router.register(r'webhooks', WebhookViewSet)
router.register(r'api-keys', APIKeyViewSet)

urlpatterns = [
    path('', include(router.urls)),
]
