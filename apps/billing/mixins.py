"""Mixins for enforcing plan-level access and subscription limits."""
from django.core.exceptions import PermissionDenied as DjangoPermissionDenied, ValidationError
from rest_framework import exceptions

from .services import SubscriptionEnforcer, SubscriptionLimitExceeded, SubscriptionService


class PlanFeatureRequiredMixin:
    """
    DRF mixin – attach to any ViewSet whose module is gated behind a plan
    feature flag.

    Usage::

        class PayrollViewSet(PlanFeatureRequiredMixin, ModelViewSet):
            required_plan_feature = 'payroll_enabled'
    """

    required_plan_feature = None

    def initial(self, request, *args, **kwargs):  # pylint: disable=arguments-differ
        super().initial(request, *args, **kwargs)
        if not self.required_plan_feature:
            return

        organization = getattr(request, 'organization', None)
        if not organization and hasattr(request.user, 'get_organization'):
            organization = request.user.get_organization()

        if not organization:
            return

        try:
            SubscriptionEnforcer.check_feature_flag(
                organization, self.required_plan_feature,
            )
        except SubscriptionLimitExceeded as exc:
            raise exceptions.PermissionDenied(detail=str(exc)) from exc
        except DjangoPermissionDenied as exc:
            raise exceptions.PermissionDenied(detail=str(exc)) from exc
        except ValidationError as exc:
            raise exceptions.PermissionDenied(detail=str(exc)) from exc


class SubscriptionRequiredMixin:
    """
    DRF mixin – ensures an active (non-expired) subscription exists before
    allowing the request through.

    Usage::

        class EmployeeViewSet(SubscriptionRequiredMixin, ModelViewSet):
            ...
    """

    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)

        organization = getattr(request, 'organization', None)
        if not organization and hasattr(request.user, 'get_organization'):
            organization = request.user.get_organization()

        if not organization:
            return

        subscription = SubscriptionService.get_active_subscription(organization)
        if not subscription:
            raise exceptions.PermissionDenied(
                detail='No active subscription. Please subscribe to continue.',
            )
