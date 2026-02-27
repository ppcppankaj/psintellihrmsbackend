"""
Billing ViewSets – Enterprise SaaS Subscription Engine
"""
from datetime import timedelta
from decimal import Decimal

from django.conf import settings
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.db.models import Sum
from django.db.models.functions import Coalesce
from rest_framework import permissions, status, viewsets, filters
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView
from django_filters.rest_framework import DjangoFilterBackend

from .models import (
    BankDetails,
    Invoice,
    OrganizationBillingProfile,
    OrganizationSubscription,
    Payment,
    PaymentTransaction,
    Plan,
)
from .serializers import (
    BankDetailsSerializer,
    CreatePaymentOrderSerializer,
    InvoiceSerializer,
    OrganizationBillingProfileSerializer,
    OrganizationSubscriptionSerializer,
    PaymentSerializer,
    PlanSerializer,
    SubscribeSerializer,
    SubscriptionDashboardSerializer,
    VerifyPaymentSerializer,
)
from .services import (
    InvoiceService,
    PaymentService,
    RenewalService,
    SubscriptionEnforcer,
    SubscriptionService,
)
from .permissions import IsSuperUserOnly, IsSuperUserOrReadOnly, IsOrgAdmin, BillingTenantPermission
from .filters import (
    PlanFilter, OrganizationSubscriptionFilter, InvoiceFilter,
    PaymentFilter, OrganizationBillingProfileFilter, BankDetailsFilter,
)
from apps.core.permissions import IsSuperAdmin
from apps.core.models import Organization


# ======================================================================
# Helpers
# ======================================================================
def _get_request_organization(request):
    org = getattr(request, 'organization', None)
    if org:
        return org
    user = getattr(request, 'user', None)
    if user and hasattr(user, 'get_organization'):
        try:
            return user.get_organization()
        except Exception:
            return None
    return None


def _format_decimal(value):
    if value is None:
        return "0.00"
    return format(Decimal(value), '.2f')


# ======================================================================
# 1. Plans – Global, superuser CRUD, authenticated read
# ======================================================================
class PlanViewSet(viewsets.ModelViewSet):
    """
    Plans:
    - Superadmin: full CRUD
    - Authenticated users: read-only
    """
    queryset = Plan.objects.all()
    serializer_class = PlanSerializer
    permission_classes = [IsSuperUserOrReadOnly]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_class = PlanFilter
    search_fields = ['name', 'code']
    ordering_fields = ['name', 'monthly_price', 'annual_price', 'created_at']
    ordering = ['name']

    def get_queryset(self):
        if self.request.user.is_superuser:
            return Plan.objects.all()
        return Plan.objects.filter(is_active=True)


# ======================================================================
# 2. Organization Subscription
# ======================================================================
class OrganizationSubscriptionViewSet(viewsets.ModelViewSet):
    """Organization subscription management.
    - Superadmin: CRUD across all orgs
    - Org admin: read-only for own org
    """

    queryset = OrganizationSubscription.objects.select_related('plan', 'organization')
    serializer_class = OrganizationSubscriptionSerializer
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_class = OrganizationSubscriptionFilter
    ordering_fields = ['start_date', 'expiry_date', 'created_at']
    ordering = ['-start_date']

    def get_queryset(self):
        user = self.request.user
        if getattr(user, 'is_superuser', False):
            return self.queryset

        org = _get_request_organization(self.request)
        if org:
            return self.queryset.filter(organization=org)
        return self.queryset.none()

    def get_permissions(self):
        if self.action in ['create', 'update', 'partial_update', 'destroy']:
            return [IsSuperAdmin()]
        return [permissions.IsAuthenticated()]

    @action(detail=False, methods=['get'], url_path='current')
    def current(self, request):
        """Return the active subscription for the requesting organization."""
        org = _get_request_organization(request)
        if not org:
            raise ValidationError('Organization context required.')
        sub = SubscriptionService.get_active_subscription(org)
        if not sub:
            return Response({'detail': 'No active subscription.'}, status=status.HTTP_404_NOT_FOUND)
        return Response(OrganizationSubscriptionSerializer(sub).data)

    @action(detail=False, methods=['get'], url_path='dashboard')
    def dashboard(self, request):
        """Return subscription + usage summary for the frontend billing dashboard."""
        org = _get_request_organization(request)
        if not org:
            raise ValidationError('Organization context required.')
        serializer = SubscriptionDashboardSerializer(org)
        return Response(serializer.data)


# ======================================================================
# 3. Subscribe (plan upgrade / switch)
# ======================================================================
class SubscribeView(APIView):
    """POST /billing/subscribe/ – select a plan to upgrade/switch."""
    permission_classes = [permissions.IsAuthenticated, IsOrgAdmin]

    def post(self, request):
        serializer = SubscribeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        organization = _get_request_organization(request)
        if not organization:
            raise ValidationError('Organization context is required.')

        plan = get_object_or_404(Plan, id=serializer.validated_data['plan_id'], is_active=True)
        duration = serializer.validated_data.get('duration_days', 30)

        new_sub = SubscriptionService.change_plan(organization, plan, duration_days=duration)
        return Response(
            OrganizationSubscriptionSerializer(new_sub).data,
            status=status.HTTP_201_CREATED,
        )


# ======================================================================
# 4. Invoices
# ======================================================================
class InvoiceViewSet(viewsets.ModelViewSet):
    """
    Invoices:
    - Superadmin: full access
    - Tenants: read-only for own org
    """
    queryset = Invoice.objects.select_related('subscription', 'plan', 'organization')
    serializer_class = InvoiceSerializer
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_class = InvoiceFilter
    search_fields = ['invoice_number']
    ordering_fields = ['invoice_number', 'total_amount', 'paid_status', 'created_at']
    ordering = ['-created_at']

    def get_queryset(self):
        user = self.request.user
        if getattr(user, 'is_superuser', False):
            return Invoice.objects.all()
        org = _get_request_organization(self.request)
        if org:
            return Invoice.objects.filter(organization=org)
        return Invoice.objects.none()

    def get_permissions(self):
        if self.action in ['create', 'update', 'partial_update', 'destroy']:
            return [IsSuperAdmin()]
        return [permissions.IsAuthenticated()]

    @action(detail=True, methods=['get'])
    def download(self, request, pk=None):
        """Download the stored invoice PDF."""
        invoice = self.get_object()
        if not invoice.pdf_file:
            InvoiceService.generate_pdf(invoice)
        if not invoice.pdf_file:
            raise Http404('Invoice PDF not available')
        file_handle = invoice.pdf_file.open('rb')
        response = FileResponse(file_handle, content_type='application/pdf')
        response['Content-Disposition'] = f'attachment; filename="invoice_{invoice.invoice_number}.pdf"'
        return response

    @action(detail=True, methods=['post'])
    def mark_paid(self, request, pk=None):
        invoice = self.get_object()
        invoice.paid_status = Invoice.STATUS_PAID
        invoice.paid_at = timezone.now()
        invoice.save(update_fields=['paid_status', 'paid_at'])
        return Response({'success': True, 'data': InvoiceSerializer(invoice).data})

    @action(detail=True, methods=['post'])
    def mark_failed(self, request, pk=None):
        invoice = self.get_object()
        invoice.paid_status = Invoice.STATUS_PENDING
        invoice.save(update_fields=['paid_status'])
        return Response({'success': True, 'data': InvoiceSerializer(invoice).data})


# ======================================================================
# 5. Payments
# ======================================================================
class PaymentViewSet(viewsets.ModelViewSet):
    queryset = Payment.objects.none()
    serializer_class = PaymentSerializer
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_class = PaymentFilter
    ordering_fields = ['amount', 'status', 'created_at']
    ordering = ['-created_at']

    def get_queryset(self):
        user = self.request.user
        if getattr(user, 'is_superuser', False):
            return Payment.objects.all()
        org = _get_request_organization(self.request)
        if org:
            return Payment.objects.filter(organization=org)
        return Payment.objects.none()

    def get_permissions(self):
        if self.action in ['create', 'update', 'partial_update', 'destroy']:
            return [IsSuperAdmin()]
        return [permissions.IsAuthenticated()]

    @action(detail=True, methods=['post'])
    def mark_success(self, request, pk=None):
        payment = self.get_object()
        payment.status = 'success'
        payment.save(update_fields=['status'])
        return Response({'success': True, 'data': PaymentSerializer(payment).data})

    @action(detail=True, methods=['post'])
    def mark_failed(self, request, pk=None):
        payment = self.get_object()
        payment.status = 'failed'
        payment.save(update_fields=['status'])
        return Response({'success': True, 'data': PaymentSerializer(payment).data})


# ======================================================================
# 6. Bank Details
# ======================================================================
class BankDetailsViewSet(viewsets.ModelViewSet):
    queryset = BankDetails.objects.none()
    serializer_class = BankDetailsSerializer

    def get_queryset(self):
        # Superusers can see all active bank details
        if getattr(self.request.user, 'is_superuser', False):
            return BankDetails.objects.filter(is_active=True)
        # Org-scoped: only show bank details for the user's organization
        org = _get_request_organization(self.request)
        if org:
            return BankDetails.objects.filter(is_active=True, organization=org)
        # FAIL-CLOSED: no org → no data
        return BankDetails.objects.none()

    def get_permissions(self):
        if self.action in ['create', 'update', 'partial_update', 'destroy']:
            return [IsSuperAdmin()]
        return [permissions.IsAuthenticated()]

    def perform_create(self, serializer):
        organization = _get_request_organization(self.request)
        if not organization:
            raise ValidationError('Organization context is required.')
        serializer.save(organization=organization)


# ======================================================================
# 7. Billing Profile
# ======================================================================
class OrganizationBillingProfileViewSet(viewsets.ModelViewSet):
    serializer_class = OrganizationBillingProfileSerializer
    queryset = OrganizationBillingProfile.objects.select_related('organization')
    permission_classes = [permissions.IsAuthenticated, BillingTenantPermission]
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_class = OrganizationBillingProfileFilter
    ordering = ['-created_at']

    def get_queryset(self):
        if getattr(self.request.user, 'is_superuser', False):
            return self.queryset
        org = _get_request_organization(self.request)
        if org:
            return self.queryset.filter(organization=org)
        return self.queryset.none()

    def perform_create(self, serializer):
        organization = _get_request_organization(self.request)
        if not organization:
            raise ValidationError('Organization context is required.')
        serializer.save(organization=organization)

    def perform_update(self, serializer):
        organization = _get_request_organization(self.request)
        if not organization:
            raise ValidationError('Organization context is required.')
        serializer.save(organization=organization)


# ======================================================================
# 8. Razorpay – Create Order
# ======================================================================
class CreatePaymentOrderView(APIView):
    """POST /billing/create-order/ – creates a Razorpay order."""
    permission_classes = [permissions.IsAuthenticated, BillingTenantPermission]

    def post(self, request):
        serializer = CreatePaymentOrderSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        organization = _get_request_organization(request)
        if not organization:
            raise ValidationError('Organization context is required.')

        plan = get_object_or_404(Plan, id=serializer.validated_data['plan_id'], is_active=True)

        transaction, order = PaymentService.create_order(
            organization=organization, plan=plan
        )

        return Response(
            {
                'success': True,
                'data': {
                    'order_id': order.get('id'),
                    'amount': order.get('amount'),
                    'currency': order.get('currency', 'INR'),
                    'key_id': getattr(settings, 'RAZORPAY_KEY_ID', ''),
                    'transaction_id': str(transaction.id),
                    'plan_name': plan.name,
                },
            },
            status=status.HTTP_201_CREATED,
        )


# ======================================================================
# 9. Razorpay – Verify Payment
# ======================================================================
class VerifyPaymentView(APIView):
    """POST /billing/verify-payment/ – verifies Razorpay signature & activates subscription."""
    permission_classes = [permissions.IsAuthenticated, BillingTenantPermission]

    def post(self, request):
        serializer = VerifyPaymentSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        organization = _get_request_organization(request)
        if not organization:
            raise ValidationError('Organization context is required.')

        transaction, subscription, invoice = PaymentService.verify_and_activate(
            organization=organization,
            razorpay_order_id=serializer.validated_data['razorpay_order_id'],
            razorpay_payment_id=serializer.validated_data['razorpay_payment_id'],
            razorpay_signature=serializer.validated_data['razorpay_signature'],
        )

        return Response(
            {
                'success': True,
                'message': 'Payment verified and subscription activated.',
                'data': {
                    'subscription_id': str(subscription.id),
                    'plan': subscription.plan.name,
                    'starts_on': subscription.start_date,
                    'expires_on': subscription.expiry_date,
                    'is_trial': subscription.is_trial,
                    'status': 'active',
                    'transaction_id': str(transaction.id),
                    'invoice_id': str(invoice.id) if invoice else None,
                    'invoice_number': invoice.invoice_number if invoice else None,
                    'invoice_total': str(invoice.total_amount) if invoice else None,
                },
            },
        )


# ======================================================================
# 10. Renewal
# ======================================================================
class RenewSubscriptionView(APIView):
    """GET /billing/renew/<org_id>/ – renewal metadata."""
    permission_classes = [permissions.IsAuthenticated, BillingTenantPermission]

    def get(self, request, organization_id):
        organization = get_object_or_404(Organization, id=organization_id)
        request_org = _get_request_organization(request)
        if not request.user.is_superuser:
            if not request_org or request_org.id != organization.id:
                raise ValidationError('You are not authorized to renew this organization.')

        subscription = (
            OrganizationSubscription.objects.select_related('plan')
            .filter(organization=organization)
            .order_by('-start_date')
            .first()
        )

        renewal_link = RenewalService.build_renewal_url(organization)
        subscription_payload = None
        if subscription:
            subscription_payload = {
                'plan_name': subscription.plan.name if subscription.plan_id else None,
                'expiry_date': subscription.expiry_date,
                'trial_end_date': subscription.trial_end_date,
                'is_trial': subscription.is_trial,
                'grace_expires_on': subscription.grace_expires_on,
                'is_in_grace_period': subscription.is_in_grace_period,
                'status': OrganizationSubscriptionSerializer(subscription).data.get('status'),
            }

        return Response({
            'success': True,
            'data': {
                'organization': {
                    'id': str(organization.id),
                    'name': organization.name,
                    'subscription_status': organization.subscription_status,
                },
                'subscription': subscription_payload,
                'renewal_link': renewal_link,
            },
        })


# ======================================================================
# 11. Usage / plan enforcement status
# ======================================================================
class UsageView(APIView):
    """GET /billing/usage/ – plan usage for the current organization."""
    permission_classes = [permissions.IsAuthenticated, BillingTenantPermission]

    def get(self, request):
        organization = _get_request_organization(request)
        if not organization:
            raise ValidationError('Organization context required.')
        try:
            usage = SubscriptionEnforcer.usage_summary(organization)
        except Exception as exc:
            raise ValidationError(str(exc)) from exc
        return Response({'success': True, 'data': usage})


# ======================================================================
# 12. Super-admin analytics
# ======================================================================
class SuperAdminBillingAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated, IsSuperAdmin]


class BillingMetricsView(SuperAdminBillingAPIView):
    """Aggregated billing stats for the superadmin dashboard."""

    def get(self, request):
        today = timezone.now().date()
        three_day_window = today + timedelta(days=3)

        active_subscriptions_qs = (
            OrganizationSubscription.all_objects
            .select_related('plan', 'organization')
            .filter(is_active=True)
        )
        active_subscriptions = list(active_subscriptions_qs)

        trial_org_ids = {s.organization_id for s in active_subscriptions if s.is_trial}
        paid_org_ids = {s.organization_id for s in active_subscriptions if not s.is_trial}
        expiring_org_ids = {
            s.organization_id for s in active_subscriptions
            if s.expiry_date and today <= s.expiry_date <= three_day_window
        }
        grace_org_ids = {s.organization_id for s in active_subscriptions if s.is_in_grace_period}

        mrr_total = Decimal('0.00')
        for s in active_subscriptions:
            if s.is_trial or not s.plan or s.plan.monthly_price is None:
                continue
            mrr_total += s.plan.monthly_price

        expired_org_count = (
            OrganizationSubscription.all_objects
            .filter(is_active=False, expiry_date__lt=today)
            .values('organization_id').distinct().count()
        )

        total_revenue = (
            Payment.all_objects.filter(status='success')
            .aggregate(total=Coalesce(Sum('amount'), Decimal('0')))
            .get('total') or Decimal('0')
        )

        return Response({
            'total_organizations': Organization.objects.count(),
            'trial_organizations': len(trial_org_ids),
            'paid_organizations': len(paid_org_ids),
            'expiring_in_3_days': len(expiring_org_ids),
            'in_grace_period': len(grace_org_ids),
            'expired_organizations': expired_org_count,
            'monthly_recurring_revenue': _format_decimal(mrr_total),
            'total_revenue': _format_decimal(total_revenue),
        })


class RecentPaymentsView(SuperAdminBillingAPIView):
    def get(self, request):
        payments = (
            Payment.all_objects
            .select_related('organization', 'invoice__plan')
            .order_by('-created_at')[:10]
        )
        payload = []
        for p in payments:
            plan_name = None
            if getattr(p, 'invoice', None) and p.invoice.plan_id:
                plan_name = p.invoice.plan.name
            payload.append({
                'organization_name': p.organization.name if p.organization_id else None,
                'plan_name': plan_name,
                'amount': _format_decimal(p.amount),
                'payment_date': p.created_at,
                'status': p.status,
            })
        return Response({'results': payload})


class UpcomingRenewalsView(SuperAdminBillingAPIView):
    def get(self, request):
        today = timezone.now().date()
        horizon = today + timedelta(days=7)
        renewals = (
            OrganizationSubscription.all_objects
            .select_related('organization', 'plan')
            .filter(is_active=True, expiry_date__isnull=False,
                    expiry_date__gte=today, expiry_date__lte=horizon)
            .order_by('expiry_date')
        )
        data = []
        for s in renewals:
            data.append({
                'organization_name': s.organization.name if s.organization_id else None,
                'plan_name': s.plan.name if s.plan_id else None,
                'expiry_date': s.expiry_date,
                'days_remaining': (s.expiry_date - today).days if s.expiry_date else None,
            })
        return Response({'results': data})


class GraceListView(SuperAdminBillingAPIView):
    def get(self, request):
        grace_candidates = (
            OrganizationSubscription.all_objects
            .select_related('organization', 'plan')
            .filter(is_active=True)
        )
        data = []
        for s in grace_candidates:
            if not s.is_in_grace_period:
                continue
            data.append({
                'organization_name': s.organization.name if s.organization_id else None,
                'plan_name': s.plan.name if s.plan_id else None,
                'grace_end_date': s.grace_expires_on,
            })
        return Response({'results': data})


class ExpiredClientsView(SuperAdminBillingAPIView):
    def get(self, request):
        today = timezone.now().date()
        expired = (
            OrganizationSubscription.all_objects
            .select_related('organization', 'plan')
            .filter(is_active=False, expiry_date__lt=today)
            .order_by('-expiry_date')
        )
        data, seen = [], set()
        for s in expired:
            if s.organization_id in seen:
                continue
            seen.add(s.organization_id)
            data.append({
                'organization_name': s.organization.name if s.organization_id else None,
                'last_plan': s.plan.name if s.plan_id else None,
                'expired_on': s.expiry_date,
            })
        return Response({'results': data})
