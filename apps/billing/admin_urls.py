"""Admin-only billing dashboard endpoints."""
from django.urls import path

from .views import (
    BillingMetricsView,
    RecentPaymentsView,
    UpcomingRenewalsView,
    GraceListView,
    ExpiredClientsView,
)

urlpatterns = [
    path('metrics/', BillingMetricsView.as_view(), name='admin-billing-metrics'),
    path('recent-payments/', RecentPaymentsView.as_view(), name='admin-billing-recent-payments'),
    path('upcoming-renewals/', UpcomingRenewalsView.as_view(), name='admin-billing-upcoming-renewals'),
    path('in-grace/', GraceListView.as_view(), name='admin-billing-in-grace'),
    path('expired/', ExpiredClientsView.as_view(), name='admin-billing-expired'),
]
