"""
Attendance URLs
"""

from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    ShiftViewSet, GeoFenceViewSet, AttendanceViewSet, FraudLogViewSet,
    AttendancePunchViewSet, ShiftAssignmentViewSet, AttendancePayrollSummaryView
)

router = DefaultRouter()
router.register(r'shifts', ShiftViewSet, basename='shift')
router.register(r'geo-fences', GeoFenceViewSet, basename='geo-fence')
router.register(r'records', AttendanceViewSet, basename='attendance')
router.register(r'punches', AttendancePunchViewSet, basename='punch')
router.register(r'fraud-logs', FraudLogViewSet, basename='fraud-log')
router.register(r'shift-assignments', ShiftAssignmentViewSet, basename='shift-assignment')

urlpatterns = [
    path('', include(router.urls)),
    path(
        'monthly-summary/<uuid:employee_id>/<int:month>/<int:year>/',
        AttendancePayrollSummaryView.as_view(),
        name='attendance-monthly-summary'
    ),
]
