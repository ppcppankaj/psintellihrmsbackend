"""
RBAC Hardening Test Suite — Section 11
=======================================

Mandatory test cases verifying:
  1. Org user cannot fetch other org employees
  2. Org user cannot see superusers
  3. Org admin cannot access superadmin endpoints
  4. Superadmin can switch org safely
  5. FK cross-tenant validation fails
  6. Header spoofing blocked
  7. Self-only endpoints reject foreign employee_id
  8. Subscription expired returns 402
"""

import uuid
from datetime import timedelta
from unittest.mock import patch, MagicMock

from django.test import TestCase, RequestFactory, override_settings
from django.utils import timezone
from rest_framework.test import APIRequestFactory, force_authenticate
from rest_framework import status

from apps.core.models import Organization, AuditLog
from apps.authentication.models import User
from apps.core.rbac_hardening import (
    TenantScopedQuerysetMixin,
    SuperuserLeakageGuardMixin,
    IsSuperAdmin,
    IsOrganizationAdmin,
    IsOrganizationUser,
    SelfOnlyMixin,
    TenantFKValidatorMixin,
    OrganizationRateThrottle,
    AuditLogger,
)


# ═══════════════════════════════════════════════════════════════════════════
# HELPERS
# ═══════════════════════════════════════════════════════════════════════════

class RBACTestBase(TestCase):
    """Base test class with shared fixtures for two organizations."""

    @classmethod
    def setUpTestData(cls):
        # ── Organization A ───────────────────────────────────────────────
        cls.org_a = Organization.objects.create(
            name='Org Alpha',
            email='admin@orgalpha.com',
            subscription_status='active',
            is_active=True,
        )
        # ── Organization B ───────────────────────────────────────────────
        cls.org_b = Organization.objects.create(
            name='Org Beta',
            email='admin@orgbeta.com',
            subscription_status='active',
            is_active=True,
        )

        # ── Superuser (global) ───────────────────────────────────────────
        cls.superuser = User.objects.create_superuser(
            email='superadmin@platform.com',
            password='super-secret-pw',
        )

        # ── Org A admin ──────────────────────────────────────────────────
        cls.org_a_admin = User.objects.create_user(
            email='admin@orgalpha.com',
            password='admin-pw',
            is_staff=True,
            is_org_admin=True,
            organization=cls.org_a,
        )
        # OrganizationUser auto-created by signal

        # ── Org A regular user ───────────────────────────────────────────
        cls.org_a_user = User.objects.create_user(
            email='employee@orgalpha.com',
            password='user-pw',
            organization=cls.org_a,
        )
        # OrganizationUser auto-created by signal

        # ── Org B admin ──────────────────────────────────────────────────
        cls.org_b_admin = User.objects.create_user(
            email='admin@orgbeta.com',
            password='admin-pw',
            is_staff=True,
            is_org_admin=True,
            organization=cls.org_b,
        )
        # OrganizationUser auto-created by signal

        # ── Org B regular user ───────────────────────────────────────────
        cls.org_b_user = User.objects.create_user(
            email='employee@orgbeta.com',
            password='user-pw',
            organization=cls.org_b,
        )
        # OrganizationUser auto-created by signal

    def _make_request(self, user, org=None, method='GET', path='/', data=None, headers=None):
        """Build a DRF request with org context."""
        factory = APIRequestFactory()
        method_fn = getattr(factory, method.lower())
        kwargs = {}
        if data:
            kwargs['data'] = data
            kwargs['format'] = 'json'
        if headers:
            kwargs.update(headers)
        request = method_fn(path, **kwargs)
        force_authenticate(request, user=user)
        request.organization = org
        request.user = user
        return request


# ═══════════════════════════════════════════════════════════════════════════
# TEST 1 — Org user cannot fetch other org employees
# ═══════════════════════════════════════════════════════════════════════════

class TestCrossTenantQuerysetIsolation(RBACTestBase):
    """S1: TenantScopedQuerysetMixin prevents cross-org data access."""

    def test_org_a_user_cannot_see_org_b_users(self):
        """Org A user must not see Org B users in queryset."""
        from apps.authentication.views import UserViewSet

        request = self._make_request(self.org_a_user, org=self.org_a)
        request.method = 'GET'

        view = UserViewSet()
        view.request = request
        view.action = 'list'
        view.kwargs = {}
        view.format_kwarg = None

        qs = view.get_queryset()
        user_emails = set(qs.values_list('email', flat=True))

        # Org A user should see Org A members only
        self.assertIn('admin@orgalpha.com', user_emails)
        # Should NOT see Org B members
        self.assertNotIn('admin@orgbeta.com', user_emails)
        self.assertNotIn('employee@orgbeta.com', user_emails)

    def test_org_b_user_cannot_see_org_a_users(self):
        """Mirror test: Org B cannot see Org A."""
        from apps.authentication.views import UserViewSet

        request = self._make_request(self.org_b_user, org=self.org_b)
        request.method = 'GET'

        view = UserViewSet()
        view.request = request
        view.action = 'list'
        view.kwargs = {}
        view.format_kwarg = None

        qs = view.get_queryset()
        user_emails = set(qs.values_list('email', flat=True))

        self.assertIn('admin@orgbeta.com', user_emails)
        self.assertNotIn('admin@orgalpha.com', user_emails)


# ═══════════════════════════════════════════════════════════════════════════
# TEST 2 — Org user cannot see superusers
# ═══════════════════════════════════════════════════════════════════════════

class TestSuperuserLeakage(RBACTestBase):
    """S2: Superusers must NEVER appear in org user lists."""

    def test_org_admin_cannot_see_superusers(self):
        """Org admin gets queryset with is_superuser=False filter."""
        from apps.authentication.views import UserViewSet

        request = self._make_request(self.org_a_admin, org=self.org_a)
        request.method = 'GET'

        view = UserViewSet()
        view.request = request
        view.action = 'list'
        view.kwargs = {}
        view.format_kwarg = None

        qs = view.get_queryset()
        superusers_visible = qs.filter(is_superuser=True).exists()
        self.assertFalse(
            superusers_visible,
            'Superusers MUST NOT appear in org admin user listings'
        )

    def test_org_user_cannot_see_superusers(self):
        """Regular org user also cannot see superusers."""
        from apps.authentication.views import UserViewSet

        request = self._make_request(self.org_a_user, org=self.org_a)
        request.method = 'GET'

        view = UserViewSet()
        view.request = request
        view.action = 'list'
        view.kwargs = {}
        view.format_kwarg = None

        qs = view.get_queryset()
        self.assertFalse(qs.filter(is_superuser=True).exists())

    def test_superuser_can_see_all_users(self):
        """Superuser can see everyone including other superusers."""
        from apps.authentication.views import UserViewSet

        request = self._make_request(self.superuser, org=None)
        request.method = 'GET'

        view = UserViewSet()
        view.request = request
        view.action = 'list'
        view.kwargs = {}
        view.format_kwarg = None

        qs = view.get_queryset()
        self.assertTrue(qs.filter(is_superuser=True).exists())


# ═══════════════════════════════════════════════════════════════════════════
# TEST 3 — Org admin cannot access superadmin-only resources
# ═══════════════════════════════════════════════════════════════════════════

class TestRoleTierPermissions(RBACTestBase):
    """S3: Role-tier permission classes enforce access levels."""

    def test_is_super_admin_rejects_org_admin(self):
        perm = IsSuperAdmin()
        request = self._make_request(self.org_a_admin, org=self.org_a)
        self.assertFalse(perm.has_permission(request, None))

    def test_is_super_admin_accepts_superuser(self):
        perm = IsSuperAdmin()
        request = self._make_request(self.superuser)
        self.assertTrue(perm.has_permission(request, None))

    def test_is_org_admin_accepts_org_admin(self):
        perm = IsOrganizationAdmin()
        request = self._make_request(self.org_a_admin, org=self.org_a)
        self.assertTrue(perm.has_permission(request, None))

    def test_is_org_admin_rejects_regular_user(self):
        perm = IsOrganizationAdmin()
        request = self._make_request(self.org_a_user, org=self.org_a)
        self.assertFalse(perm.has_permission(request, None))

    def test_is_org_user_rejects_superuser(self):
        perm = IsOrganizationUser()
        request = self._make_request(self.superuser)
        self.assertFalse(perm.has_permission(request, None))

    def test_is_org_user_rejects_org_admin(self):
        perm = IsOrganizationUser()
        request = self._make_request(self.org_a_admin, org=self.org_a)
        self.assertFalse(perm.has_permission(request, None))

    def test_is_org_user_accepts_regular_user(self):
        perm = IsOrganizationUser()
        request = self._make_request(self.org_a_user, org=self.org_a)
        self.assertTrue(perm.has_permission(request, None))


# ═══════════════════════════════════════════════════════════════════════════
# TEST 4 — Superadmin can switch org safely
# ═══════════════════════════════════════════════════════════════════════════

class TestSuperadminOrgSwitch(RBACTestBase):
    """S4/S6: Superadmin can switch org via header without cross-tenant leak."""

    def test_superuser_sees_org_a_when_context_is_org_a(self):
        """Superuser with org_a context should see org_a users."""
        from apps.authentication.views import UserViewSet

        request = self._make_request(self.superuser, org=self.org_a)
        request.method = 'GET'

        view = UserViewSet()
        view.request = request
        view.action = 'list'
        view.kwargs = {}
        view.format_kwarg = None

        qs = view.get_queryset()
        emails = set(qs.values_list('email', flat=True))
        self.assertIn('admin@orgalpha.com', emails)

    def test_superuser_sees_org_b_when_context_is_org_b(self):
        """Superuser can safely switch to org_b."""
        from apps.authentication.views import UserViewSet

        request = self._make_request(self.superuser, org=self.org_b)
        request.method = 'GET'

        view = UserViewSet()
        view.request = request
        view.action = 'list'
        view.kwargs = {}
        view.format_kwarg = None

        qs = view.get_queryset()
        emails = set(qs.values_list('email', flat=True))
        self.assertIn('admin@orgbeta.com', emails)

    def test_superuser_without_org_sees_all(self):
        """Superuser without org context sees all users."""
        from apps.authentication.views import UserViewSet

        request = self._make_request(self.superuser, org=None)
        request.method = 'GET'

        view = UserViewSet()
        view.request = request
        view.action = 'list'
        view.kwargs = {}
        view.format_kwarg = None

        qs = view.get_queryset()
        self.assertGreaterEqual(qs.count(), 4)


# ═══════════════════════════════════════════════════════════════════════════
# TEST 5 — FK cross-tenant validation fails
# ═══════════════════════════════════════════════════════════════════════════

class TestFKCrossTenantValidation(RBACTestBase):
    """S5: TenantFKValidatorMixin blocks cross-org FK references."""

    def test_cross_org_fk_raises_validation_error(self):
        """FK pointing to another org's object must be rejected."""
        from rest_framework import serializers as drf_serializers

        # Create a mock FK object belonging to org B
        class FakeOrgEntity:
            organization_id = None

            def __init__(self, org_id):
                self.organization_id = org_id

        class TestSerializer(TenantFKValidatorMixin, drf_serializers.Serializer):
            department = drf_serializers.CharField(required=False)

            class Meta:
                model = None

            tenant_fk_fields = ['department']

            def validate(self, attrs):
                return super().validate(attrs)

        request = self._make_request(self.org_a_user, org=self.org_a)

        # Simulate a department from org B
        foreign_dept = FakeOrgEntity(self.org_b.id)

        serializer = TestSerializer(
            data={'department': 'test'},
            context={'request': request}
        )
        serializer.is_valid()

        # Manually inject the foreign FK into validated_data
        serializer._validated_data['department'] = foreign_dept

        from rest_framework.exceptions import ValidationError
        with self.assertRaises(ValidationError):
            serializer.validate(serializer._validated_data)

    def test_same_org_fk_passes(self):
        """FK pointing to same org must pass."""
        from rest_framework import serializers as drf_serializers

        class FakeOrgEntity:
            def __init__(self, org_id):
                self.organization_id = org_id

        class TestSerializer(TenantFKValidatorMixin, drf_serializers.Serializer):
            department = drf_serializers.CharField(required=False)

            class Meta:
                model = None

            tenant_fk_fields = ['department']

        request = self._make_request(self.org_a_user, org=self.org_a)

        same_org_dept = FakeOrgEntity(self.org_a.id)

        serializer = TestSerializer(
            data={'department': 'test'},
            context={'request': request}
        )
        serializer.is_valid()
        serializer._validated_data['department'] = same_org_dept

        # Should NOT raise
        result = serializer.validate(serializer._validated_data)
        self.assertIn('department', result)


# ═══════════════════════════════════════════════════════════════════════════
# TEST 6 — Header spoofing blocked
# ═══════════════════════════════════════════════════════════════════════════

class TestHeaderSpoofingProtection(RBACTestBase):
    """S6: Non-superusers cannot spoof X-Organization-ID."""

    @patch('apps.core.middleware_organization.is_management_command', return_value=False)
    def test_non_superuser_spoofed_header_returns_403(self, _mock_cmd):
        """Org A user sending X-Organization-ID of Org B must be blocked."""
        from apps.core.middleware_organization import OrganizationMiddleware

        factory = RequestFactory()
        request = factory.get(
            '/api/v1/employees/',
            HTTP_X_ORGANIZATION_ID=str(self.org_b.id),
        )
        request.user = self.org_a_user
        request.domain_organization = None

        middleware = OrganizationMiddleware(get_response=lambda r: None)
        response = middleware.process_request(request)

        self.assertIsNotNone(response, 'Middleware must block spoofed header')
        self.assertEqual(response.status_code, 403)

    @patch('apps.core.middleware_organization.is_management_command', return_value=False)
    def test_superuser_header_switch_allowed(self, _mock_cmd):
        """Superuser CAN use X-Organization-ID to switch orgs."""
        from apps.core.middleware_organization import OrganizationMiddleware

        factory = RequestFactory()
        request = factory.get(
            '/api/v1/employees/',
            HTTP_X_ORGANIZATION_ID=str(self.org_b.id),
        )
        # Superuser with NO organization (global admin)
        self.superuser.organization = None
        request.user = self.superuser
        request.domain_organization = None

        middleware = OrganizationMiddleware(get_response=lambda r: None)
        response = middleware.process_request(request)

        # Should NOT block — superuser can switch
        if response is not None:
            self.assertNotEqual(response.status_code, 403)

    @patch('apps.core.middleware_organization.is_management_command', return_value=False)
    def test_matching_header_org_passes(self, _mock_cmd):
        """User sending their own org ID in header should pass."""
        from apps.core.middleware_organization import OrganizationMiddleware

        factory = RequestFactory()
        request = factory.get(
            '/api/v1/employees/',
            HTTP_X_ORGANIZATION_ID=str(self.org_a.id),
        )
        request.user = self.org_a_user
        request.domain_organization = None

        middleware = OrganizationMiddleware(get_response=lambda r: None)
        response = middleware.process_request(request)

        # Matching header should not trigger spoofing alert
        if response is not None:
            self.assertNotEqual(response.status_code, 403)


# ═══════════════════════════════════════════════════════════════════════════
# TEST 7 — Self-only endpoints reject foreign employee_id
# ═══════════════════════════════════════════════════════════════════════════

class TestSelfOnlyEndpoints(RBACTestBase):
    """S4: SelfOnlyMixin rejects foreign employee_id in request body."""

    def test_foreign_employee_id_raises_permission_denied(self):
        """Submitting another employee's ID must be rejected."""
        from rest_framework import viewsets as drf_viewsets
        from rest_framework.exceptions import PermissionDenied

        class FakeView(SelfOnlyMixin, drf_viewsets.GenericViewSet):
            pass

        request = self._make_request(
            self.org_a_user,
            org=self.org_a,
            method='POST',
            data={'employee_id': str(uuid.uuid4())},  # Random foreign ID
        )

        view = FakeView()
        view.request = request

        with self.assertRaises(PermissionDenied):
            view.enforce_self_only(request, data={'employee_id': str(uuid.uuid4())})

    def test_own_employee_id_accepted(self):
        """Submitting own employee_id (when employee exists) should pass."""
        # This test requires an employee record — skip if not available
        from apps.employees.models import Employee

        employee = Employee.objects.filter(user=self.org_a_user).first()
        if not employee:
            # Create minimal employee for test
            employee = Employee.objects.create(
                user=self.org_a_user,
                organization=self.org_a,
                employee_id='EMP-TEST-SELF',
                date_of_joining=timezone.now().date(),
            )

        from rest_framework import viewsets as drf_viewsets

        class FakeView(SelfOnlyMixin, drf_viewsets.GenericViewSet):
            pass

        request = self._make_request(
            self.org_a_user,
            org=self.org_a,
            method='POST',
            data={'employee_id': str(employee.id)},
        )

        view = FakeView()
        view.request = request

        # Should NOT raise
        result = view.enforce_self_only(request, data={'employee_id': str(employee.id)})
        self.assertEqual(result.id, employee.id)


# ═══════════════════════════════════════════════════════════════════════════
# TEST 8 — Subscription expired returns 402
# ═══════════════════════════════════════════════════════════════════════════

class TestSubscriptionGuard(RBACTestBase):
    """S8: SubscriptionMiddleware returns 402 for expired subscriptions."""

    def test_expired_subscription_returns_402(self):
        """When no active subscription exists, middleware returns 402."""
        from apps.billing.middleware import SubscriptionMiddleware

        factory = RequestFactory()
        request = factory.get('/api/v1/employees/')
        request.user = self.org_a_user
        request.organization = self.org_a
        request._subscription_grace_warning = False

        middleware = SubscriptionMiddleware(get_response=lambda r: None)

        # Mock SubscriptionService to return None (no active subscription)
        with patch('apps.billing.middleware.SubscriptionService') as mock_svc:
            mock_svc.get_active_subscription.return_value = None
            response = middleware.process_request(request)

        self.assertIsNotNone(response)
        self.assertEqual(response.status_code, 402)

    def test_active_subscription_passes(self):
        """Active subscription allows request through."""
        from apps.billing.middleware import SubscriptionMiddleware

        factory = RequestFactory()
        request = factory.get('/api/v1/employees/')
        request.user = self.org_a_user
        request.organization = self.org_a
        request._subscription_grace_warning = False

        middleware = SubscriptionMiddleware(get_response=lambda r: None)

        mock_plan = MagicMock()
        mock_sub = MagicMock()
        mock_sub.is_trial = False
        mock_sub.plan = mock_plan

        with patch('apps.billing.middleware.SubscriptionService') as mock_svc, \
             patch('apps.billing.middleware.RenewalService') as mock_renewal:
            mock_svc.get_active_subscription.return_value = mock_sub
            mock_renewal.has_grace_passed.return_value = False
            mock_renewal.is_within_grace.return_value = False
            response = middleware.process_request(request)

        self.assertIsNone(response)

    def test_disabled_feature_returns_403(self):
        """Request to a disabled module returns 403."""
        from apps.billing.middleware import SubscriptionMiddleware

        factory = RequestFactory()
        request = factory.get('/api/v1/payroll/')
        request.user = self.org_a_user
        request.organization = self.org_a
        request._subscription_grace_warning = False

        middleware = SubscriptionMiddleware(get_response=lambda r: None)

        mock_plan = MagicMock()
        mock_plan.payroll_enabled = False

        mock_sub = MagicMock()
        mock_sub.is_trial = False
        mock_sub.plan = mock_plan

        with patch('apps.billing.middleware.SubscriptionService') as mock_svc, \
             patch('apps.billing.middleware.RenewalService') as mock_renewal:
            mock_svc.get_active_subscription.return_value = mock_sub
            mock_renewal.has_grace_passed.return_value = False
            mock_renewal.is_within_grace.return_value = False
            response = middleware.process_request(request)

        self.assertIsNotNone(response)
        self.assertEqual(response.status_code, 403)

    def test_superuser_bypasses_subscription_check(self):
        """Superusers should always bypass subscription middleware."""
        from apps.billing.middleware import SubscriptionMiddleware

        factory = RequestFactory()
        request = factory.get('/api/v1/employees/')
        request.user = self.superuser
        request.organization = self.org_a
        request._subscription_grace_warning = False

        middleware = SubscriptionMiddleware(get_response=lambda r: None)
        response = middleware.process_request(request)

        # Superuser is skipped entirely
        self.assertIsNone(response)


# ═══════════════════════════════════════════════════════════════════════════
# BONUS — Audit Logger Tests
# ═══════════════════════════════════════════════════════════════════════════

class TestAuditLogger(RBACTestBase):
    """S10: AuditLogger writes entries to AuditLog model."""

    def test_log_creates_audit_entry(self):
        """AuditLogger.log() should create an AuditLog record."""
        initial_count = AuditLog.objects.count()

        AuditLogger.log(
            action='test_action',
            actor=self.org_a_admin,
            organization=self.org_a,
            entity_type='TestEntity',
            entity_id='test-123',
            metadata={'key': 'value'},
        )

        self.assertEqual(AuditLog.objects.count(), initial_count + 1)
        entry = AuditLog.objects.latest('timestamp')
        self.assertEqual(entry.action, 'test_action')
        self.assertEqual(entry.resource_type, 'TestEntity')
        self.assertEqual(entry.resource_id, 'test-123')
        self.assertEqual(entry.user, self.org_a_admin)

    def test_log_role_change_creates_entry(self):
        """Convenience method log_role_change records properly."""
        AuditLogger.log_role_change(
            actor=self.superuser,
            target_user=self.org_a_user,
            old_roles=['EMPLOYEE'],
            new_roles=['ORG_ADMIN'],
        )

        entry = AuditLog.objects.latest('timestamp')
        self.assertEqual(entry.action, 'role_change')
        self.assertEqual(entry.resource_type, 'User')
        self.assertIn('old_roles', entry.new_values)


# ═══════════════════════════════════════════════════════════════════════════
# BONUS — Rate Throttle Tests
# ═══════════════════════════════════════════════════════════════════════════

@override_settings(REST_FRAMEWORK={
    'DEFAULT_THROTTLE_RATES': {'org': '1000/hour'},
})
class TestOrganizationRateThrottle(RBACTestBase):
    """S9: Per-tenant rate throttle keying."""

    def test_superuser_gets_no_throttle(self):
        """Superusers should have None cache key (no throttle)."""
        throttle = OrganizationRateThrottle()
        request = self._make_request(self.superuser, org=self.org_a)
        key = throttle.get_cache_key(request, None)
        self.assertIsNone(key)

    def test_org_user_gets_org_scoped_key(self):
        """Org users share a cache key scoped to their org."""
        throttle = OrganizationRateThrottle()
        request = self._make_request(self.org_a_user, org=self.org_a)
        key = throttle.get_cache_key(request, None)
        self.assertIn(str(self.org_a.id), key)

    def test_different_orgs_get_different_keys(self):
        """Two different orgs must not share a throttle bucket."""
        throttle = OrganizationRateThrottle()

        req_a = self._make_request(self.org_a_user, org=self.org_a)
        req_b = self._make_request(self.org_b_user, org=self.org_b)

        key_a = throttle.get_cache_key(req_a, None)
        key_b = throttle.get_cache_key(req_b, None)

        self.assertNotEqual(key_a, key_b)
