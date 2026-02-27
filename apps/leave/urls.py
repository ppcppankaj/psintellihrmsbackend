"""
Leave URLs
"""

from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    LeaveTypeViewSet, LeavePolicyViewSet, LeaveRequestViewSet, HolidayViewSet,
    LeaveEncashmentViewSet, CompensatoryLeaveViewSet, LeaveBalanceViewSet
)

router = DefaultRouter()
router.register(r'types', LeaveTypeViewSet, basename='leave-type')
router.register(r'policies', LeavePolicyViewSet, basename='leave-policy')
router.register(r'requests', LeaveRequestViewSet, basename='leave-request')
router.register(r'holidays', HolidayViewSet, basename='holiday')
router.register(r'encashments', LeaveEncashmentViewSet, basename='leave-encashment')
router.register(r'compensatory', CompensatoryLeaveViewSet, basename='compensatory-leave')
router.register(r'balances', LeaveBalanceViewSet, basename='leave-balance')

urlpatterns = [
    path('', include(router.urls)),
]
