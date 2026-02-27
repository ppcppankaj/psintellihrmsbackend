"""Billing URLs – SaaS Subscription Engine"""
from django.urls import path, include
from rest_framework.routers import DefaultRouter

from .views import (
    BankDetailsViewSet,
    CreatePaymentOrderView,
    InvoiceViewSet,
    OrganizationBillingProfileViewSet,
    OrganizationSubscriptionViewSet,
    PaymentViewSet,
    PlanViewSet,
    RenewSubscriptionView,
    SubscribeView,
    UsageView,
    VerifyPaymentView,
    # Super-admin analytics
    BillingMetricsView,
    RecentPaymentsView,
    UpcomingRenewalsView,
    GraceListView,
    ExpiredClientsView,
)
from .webhooks import RazorpayWebhookView

router = DefaultRouter()
router.register(r'plans', PlanViewSet)
router.register(r'subscriptions', OrganizationSubscriptionViewSet)
router.register(r'invoices', InvoiceViewSet)
router.register(r'payments', PaymentViewSet)
router.register(r'bank-details', BankDetailsViewSet)
router.register(r'billing-profiles', OrganizationBillingProfileViewSet, basename='billing-profile')

urlpatterns = [
    path('', include(router.urls)),

    # Tenant actions
    path('subscribe/', SubscribeView.as_view(), name='billing-subscribe'),
    path('create-order/', CreatePaymentOrderView.as_view(), name='billing-create-order'),
    path('verify-payment/', VerifyPaymentView.as_view(), name='billing-verify-payment'),
    path('renew/<uuid:organization_id>/', RenewSubscriptionView.as_view(), name='billing-renew'),
    path('usage/', UsageView.as_view(), name='billing-usage'),

    # Super-admin analytics
    path('admin/metrics/', BillingMetricsView.as_view(), name='billing-metrics'),
    path('admin/recent-payments/', RecentPaymentsView.as_view(), name='billing-recent-payments'),
    path('admin/upcoming-renewals/', UpcomingRenewalsView.as_view(), name='billing-upcoming-renewals'),
    path('admin/grace-list/', GraceListView.as_view(), name='billing-grace-list'),
    path('admin/expired-clients/', ExpiredClientsView.as_view(), name='billing-expired-clients'),

    # Razorpay server-to-server webhook (CSRF-exempt, signature-verified)
    path('webhook/razorpay/', RazorpayWebhookView.as_view(), name='razorpay-webhook'),
]
