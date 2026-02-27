"""Middleware enforcing subscription access rules and feature flags"""
from django.http import JsonResponse
from django.utils import timezone
from django.utils.deprecation import MiddlewareMixin

from .services import RenewalService, SubscriptionService

EXEMPT_PATH_PREFIXES = (
    '/admin',
    '/api/v1/auth',
    '/api/v1/health',
    '/api/v1/readiness',
    '/api/v1/billing',     # billing endpoints must remain accessible
    '/api/admin/billing',
    '/api/schema',
    '/api/docs',
    '/api/redoc',
    '/static',
    '/media',
)

# Map URL path segments to plan feature flags
FEATURE_PATH_MAP = {
    '/api/v1/payroll': 'payroll_enabled',
    '/api/v1/attendance': 'attendance_enabled',
    '/api/v1/recruitment': 'recruitment_enabled',
    '/api/v1/workflows': 'workflow_enabled',
    '/api/v1/timesheets': 'timesheet_enabled',
}


class SubscriptionMiddleware(MiddlewareMixin):
    """Block tenant requests when subscription or trial has expired."""

    def process_request(self, request):
        if self._should_skip(request):
            return None

        organization = getattr(request, 'organization', None)
        if not organization:
            return None

        subscription = SubscriptionService.get_active_subscription(organization)
        if not subscription:
            return self._payment_required('No active subscription for organization')

        request._subscription_grace_warning = False

        if RenewalService.has_grace_passed(subscription):
            subscription.deactivate(reason='grace_period_ended')
            return self._payment_required(
                'Subscription expired after the grace window. Renew to continue.'
            )

        if RenewalService.is_within_grace(subscription):
            RenewalService.mark_org_past_due(subscription)
            request._subscription_grace_warning = True
            return None

        RenewalService.mark_org_active(subscription)

        if subscription.is_trial and subscription.trial_end_date:
            if timezone.now().date() > subscription.trial_end_date:
                subscription.deactivate()
                return self._payment_required(
                    'Trial period has ended. Please activate a paid subscription.'
                )

        # Feature gate: block disabled modules
        feature_flag = self._match_feature(request.path)
        if feature_flag:
            plan = subscription.plan
            if plan and not getattr(plan, feature_flag, True):
                return JsonResponse(
                    {
                        'error': 'This feature is not available on your current plan.',
                        'code': 'FEATURE_DISABLED',
                        'feature': feature_flag,
                    },
                    status=403,
                )

        return None

    @staticmethod
    def _should_skip(request):
        if not getattr(request, 'user', None) or not request.user.is_authenticated:
            return True
        if getattr(request.user, 'is_superuser', False):
            return True
        if request.method == 'OPTIONS':
            return True
        for prefix in EXEMPT_PATH_PREFIXES:
            if request.path.startswith(prefix):
                return True
        return False

    @staticmethod
    def _match_feature(path):
        for prefix, flag in FEATURE_PATH_MAP.items():
            if path.startswith(prefix):
                return flag
        return None

    @staticmethod
    def _payment_required(message):
        return JsonResponse(
            {'error': message, 'code': 'PAYMENT_REQUIRED'},
            status=402,
        )

    def process_response(self, request, response):
        if getattr(request, '_subscription_grace_warning', False):
            response['X-Subscription-Grace'] = 'true'
        return response
