"""Reports URLs"""
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    ReportViewSet,
    ReportTemplateViewSet,
    ScheduledReportViewSet,
    ReportExecutionViewSet,
    ReportExecuteView,
    ReportExportView,
)

router = DefaultRouter()
router.register(r'', ReportViewSet, basename='reports')
router.register(r'templates', ReportTemplateViewSet, basename='report-templates')
router.register(r'schedules', ScheduledReportViewSet, basename='report-schedules')
router.register(r'executions', ReportExecutionViewSet, basename='report-executions')

urlpatterns = [
    path('', include(router.urls)),
    path('execute/', ReportExecuteView.as_view()),
    path('export/', ReportExportView.as_view()),
]
