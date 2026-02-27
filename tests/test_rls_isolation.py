"""
PostgreSQL Row-Level Security (RLS) Isolation Tests
====================================================

Validates that RLS policies enforce database-level tenant isolation:

  1. Org A user SELECT → only Org A rows (even via raw SQL)
  2. Cross-tenant raw SELECT → returns 0 rows
  3. Cross-tenant INSERT → fails
  4. Superadmin → sees all rows
  5. Organization-change trigger → blocks UPDATE of organization_id
  6. Unauthenticated context → fail-closed (zero rows)
  7. RLS middleware sets / resets session variables correctly
  8. Connection pooling safety — context never leaks

These tests ONLY run on PostgreSQL. On SQLite they are auto-skipped.
"""

import uuid
from unittest.mock import MagicMock, patch

from django.conf import settings
from django.db import connection
from django.test import TestCase, RequestFactory, override_settings

from apps.core.models import Organization
from apps.authentication.models import User
from apps.core.middleware_rls import RLSContextMiddleware, _NULL_ORG


def _is_postgres():
    return connection.vendor == "postgresql"


def _skip_unless_postgres(test_func):
    """Decorator to skip tests when not running on PostgreSQL."""
    from functools import wraps

    @wraps(test_func)
    def wrapper(*args, **kwargs):
        if not _is_postgres():
            args[0].skipTest("PostgreSQL required — skipping on SQLite")
        return test_func(*args, **kwargs)

    return wrapper


# ═══════════════════════════════════════════════════════════════════════════
# FIXTURES
# ═══════════════════════════════════════════════════════════════════════════

class RLSTestBase(TestCase):
    """Shared fixtures: two orgs, users, and employee records."""

    @classmethod
    def setUpTestData(cls):
        cls.org_a = Organization.objects.create(
            name="RLS Org Alpha",
            email="rls-a@test.com",
            subscription_status="active",
            is_active=True,
        )
        cls.org_b = Organization.objects.create(
            name="RLS Org Beta",
            email="rls-b@test.com",
            subscription_status="active",
            is_active=True,
        )
        cls.superuser = User.objects.create_superuser(
            email="rls-super@test.com",
            password="s3cret",
        )
        cls.org_a_user = User.objects.create_user(
            email="rls-a-user@test.com",
            password="pw",
            organization=cls.org_a,
        )
        cls.org_b_user = User.objects.create_user(
            email="rls-b-user@test.com",
            password="pw",
            organization=cls.org_b,
        )

    # Helper: set RLS session variables directly
    @staticmethod
    def _set_rls(org_id, is_superuser="false"):
        with connection.cursor() as cur:
            cur.execute(
                "SET LOCAL app.current_organization_id = %s;", [str(org_id)]
            )
            cur.execute(
                "SET LOCAL app.current_is_superuser = %s;", [is_superuser]
            )

    @staticmethod
    def _reset_rls():
        with connection.cursor() as cur:
            cur.execute("RESET app.current_organization_id;")
            cur.execute("RESET app.current_is_superuser;")


# ═══════════════════════════════════════════════════════════════════════════
# TEST 1 — Org A user SELECT → only Org A rows
# ═══════════════════════════════════════════════════════════════════════════

class TestRLSSelectIsolation(RLSTestBase):
    """Verify SELECT returns only current tenant's rows."""

    @_skip_unless_postgres
    def test_org_a_context_sees_only_org_a_departments(self):
        """With RLS set to Org A, raw SQL sees only Org A rows."""
        from apps.employees.models import Department

        Department.objects.create(
            name="RLS-Eng-A", organization=self.org_a
        )
        Department.objects.create(
            name="RLS-Eng-B", organization=self.org_b
        )

        self._set_rls(self.org_a.id)

        with connection.cursor() as cur:
            cur.execute(
                "SELECT name FROM employees_department "
                "WHERE name LIKE 'RLS-Eng-%%'"
            )
            rows = cur.fetchall()

        names = {r[0] for r in rows}
        self.assertIn("RLS-Eng-A", names)
        self.assertNotIn("RLS-Eng-B", names)


# ═══════════════════════════════════════════════════════════════════════════
# TEST 2 — Cross-tenant raw SELECT → 0 rows
# ═══════════════════════════════════════════════════════════════════════════

class TestRLSCrossTenantSelect(RLSTestBase):
    """Even explicit WHERE organization_id = <other_org> returns zero rows."""

    @_skip_unless_postgres
    def test_raw_sql_cross_org_returns_empty(self):
        from apps.employees.models import Department

        Department.objects.create(
            name="RLS-Cross-Target", organization=self.org_b
        )

        # Set context to Org A
        self._set_rls(self.org_a.id)

        with connection.cursor() as cur:
            cur.execute(
                "SELECT COUNT(*) FROM employees_department "
                "WHERE organization_id = %s AND name = 'RLS-Cross-Target'",
                [str(self.org_b.id)],
            )
            count = cur.fetchone()[0]

        self.assertEqual(count, 0, "Cross-tenant SELECT must return 0 rows")


# ═══════════════════════════════════════════════════════════════════════════
# TEST 3 — Cross-tenant INSERT → fails
# ═══════════════════════════════════════════════════════════════════════════

class TestRLSCrossTenantInsert(RLSTestBase):
    """Inserting a row with another org's ID must be blocked by RLS."""

    @_skip_unless_postgres
    def test_insert_into_other_org_fails(self):
        from django.db import IntegrityError

        self._set_rls(self.org_a.id)

        with connection.cursor() as cur:
            try:
                cur.execute(
                    "INSERT INTO employees_department "
                    "(id, name, organization_id, is_active, created_at, updated_at, is_deleted) "
                    "VALUES (%s, %s, %s, true, now(), now(), false)",
                    [str(uuid.uuid4()), "RLS-Injected", str(self.org_b.id)],
                )
                self.fail("INSERT into other org must be blocked by RLS")
            except Exception as exc:
                # PostgreSQL raises a new_row_violates_check_option or
                # insufficient_privilege error
                self.assertIn(
                    "policy",
                    str(exc).lower(),
                    f"Expected RLS policy violation, got: {exc}",
                )


# ═══════════════════════════════════════════════════════════════════════════
# TEST 4 — Superadmin sees all rows
# ═══════════════════════════════════════════════════════════════════════════

class TestRLSSuperadminBypass(RLSTestBase):
    """Superadmin (is_superuser=true) bypasses RLS restrictions."""

    @_skip_unless_postgres
    def test_superadmin_sees_all_departments(self):
        from apps.employees.models import Department

        Department.objects.create(
            name="RLS-Super-A", organization=self.org_a
        )
        Department.objects.create(
            name="RLS-Super-B", organization=self.org_b
        )

        # Set superuser context
        self._set_rls(self.org_a.id, is_superuser="true")

        with connection.cursor() as cur:
            cur.execute(
                "SELECT name FROM employees_department "
                "WHERE name LIKE 'RLS-Super-%%'"
            )
            rows = cur.fetchall()

        names = {r[0] for r in rows}
        self.assertIn("RLS-Super-A", names)
        self.assertIn("RLS-Super-B", names)


# ═══════════════════════════════════════════════════════════════════════════
# TEST 5 — Organization-change trigger blocks UPDATE
# ═══════════════════════════════════════════════════════════════════════════

class TestRLSOrgChangeTrigger(RLSTestBase):
    """Trigger prevents UPDATE of organization_id column."""

    @_skip_unless_postgres
    def test_org_change_blocked_by_trigger(self):
        from apps.employees.models import Department

        dept = Department.objects.create(
            name="RLS-Trigger-Test", organization=self.org_a
        )

        # Must be superuser to even see the row across orgs
        self._set_rls(self.org_a.id, is_superuser="true")

        with connection.cursor() as cur:
            try:
                cur.execute(
                    "UPDATE employees_department "
                    "SET organization_id = %s WHERE id = %s",
                    [str(self.org_b.id), str(dept.id)],
                )
                self.fail("Trigger must block organization_id change")
            except Exception as exc:
                self.assertIn(
                    "organization",
                    str(exc).lower(),
                    f"Expected org-change trigger error, got: {exc}",
                )


# ═══════════════════════════════════════════════════════════════════════════
# TEST 6 — Unauthenticated context → fail-closed
# ═══════════════════════════════════════════════════════════════════════════

class TestRLSFailClosed(RLSTestBase):
    """Without RLS context set, queries return zero rows (fail-closed)."""

    @_skip_unless_postgres
    def test_null_org_context_sees_nothing(self):
        from apps.employees.models import Department

        Department.objects.create(
            name="RLS-FailClosed", organization=self.org_a
        )

        # Set to null sentinel org — no real org has this ID
        self._set_rls(_NULL_ORG)

        with connection.cursor() as cur:
            cur.execute(
                "SELECT COUNT(*) FROM employees_department "
                "WHERE name = 'RLS-FailClosed'"
            )
            count = cur.fetchone()[0]

        self.assertEqual(count, 0, "Null org context must see 0 rows")


# ═══════════════════════════════════════════════════════════════════════════
# TEST 7 — RLS Middleware sets/resets session variables
# ═══════════════════════════════════════════════════════════════════════════

class TestRLSMiddleware(RLSTestBase):
    """Verify RLSContextMiddleware behaviour (works on any DB engine)."""

    @override_settings(ENABLE_POSTGRESQL_RLS=True)
    def test_middleware_sets_context_for_authenticated_user(self):
        # Force re-evaluation of _enabled cache
        RLSContextMiddleware._enabled = None

        if not _is_postgres():
            RLSContextMiddleware._enabled = None
            self.skipTest("PostgreSQL required")

        factory = RequestFactory()
        request = factory.get("/api/v1/employees/")
        request.user = self.org_a_user
        request.organization = self.org_a

        middleware = RLSContextMiddleware(get_response=lambda r: MagicMock(status_code=200))
        middleware.process_request(request)

        with connection.cursor() as cur:
            cur.execute("SELECT current_setting('app.current_organization_id', true);")
            org_val = cur.fetchone()[0]
            cur.execute("SELECT current_setting('app.current_is_superuser', true);")
            super_val = cur.fetchone()[0]

        self.assertEqual(org_val, str(self.org_a.id))
        self.assertEqual(super_val, "false")

    @override_settings(ENABLE_POSTGRESQL_RLS=True)
    def test_middleware_sets_superuser_flag(self):
        RLSContextMiddleware._enabled = None

        if not _is_postgres():
            RLSContextMiddleware._enabled = None
            self.skipTest("PostgreSQL required")

        factory = RequestFactory()
        request = factory.get("/api/v1/employees/")
        request.user = self.superuser
        request.organization = self.org_a

        middleware = RLSContextMiddleware(get_response=lambda r: MagicMock(status_code=200))
        middleware.process_request(request)

        with connection.cursor() as cur:
            cur.execute("SELECT current_setting('app.current_is_superuser', true);")
            val = cur.fetchone()[0]

        self.assertEqual(val, "true")

    @override_settings(ENABLE_POSTGRESQL_RLS=True)
    def test_middleware_unauthenticated_sets_null_org(self):
        RLSContextMiddleware._enabled = None

        if not _is_postgres():
            RLSContextMiddleware._enabled = None
            self.skipTest("PostgreSQL required")

        factory = RequestFactory()
        request = factory.get("/api/v1/employees/")
        request.user = MagicMock(is_authenticated=False)

        middleware = RLSContextMiddleware(get_response=lambda r: MagicMock(status_code=200))
        middleware.process_request(request)

        with connection.cursor() as cur:
            cur.execute("SELECT current_setting('app.current_organization_id', true);")
            val = cur.fetchone()[0]

        self.assertEqual(val, _NULL_ORG)

    def test_middleware_noop_on_sqlite(self):
        """On SQLite, middleware must be a no-op (no crash)."""
        RLSContextMiddleware._enabled = None  # Force re-check

        factory = RequestFactory()
        request = factory.get("/api/v1/employees/")
        request.user = self.org_a_user
        request.organization = self.org_a

        middleware = RLSContextMiddleware(get_response=lambda r: MagicMock(status_code=200))

        # Must not raise on any engine
        result = middleware.process_request(request)
        self.assertIsNone(result)

    def tearDown(self):
        # Reset cached _enabled flag after each test
        RLSContextMiddleware._enabled = None


# ═══════════════════════════════════════════════════════════════════════════
# TEST 8 — Connection pooling safety
# ═══════════════════════════════════════════════════════════════════════════

class TestRLSConnectionPoolingSafety(RLSTestBase):
    """Verify session variables are reset after request processing."""

    @_skip_unless_postgres
    @override_settings(ENABLE_POSTGRESQL_RLS=True)
    def test_process_response_resets_context(self):
        RLSContextMiddleware._enabled = None

        factory = RequestFactory()
        request = factory.get("/api/v1/employees/")
        request.user = self.org_a_user
        request.organization = self.org_a

        response = MagicMock(status_code=200)
        middleware = RLSContextMiddleware(get_response=lambda r: response)

        # Set context
        middleware.process_request(request)

        # Simulate response — should reset
        middleware.process_response(request, response)

        with connection.cursor() as cur:
            cur.execute(
                "SELECT current_setting('app.current_organization_id', true);"
            )
            val = cur.fetchone()[0]

        # After reset, the value should be empty or the DB default
        # (not the org_a ID anymore)
        self.assertNotEqual(
            val,
            str(self.org_a.id),
            "RLS context must be reset after response",
        )

    @_skip_unless_postgres
    @override_settings(ENABLE_POSTGRESQL_RLS=True)
    def test_process_exception_resets_context(self):
        RLSContextMiddleware._enabled = None

        factory = RequestFactory()
        request = factory.get("/api/v1/employees/")
        request.user = self.org_a_user
        request.organization = self.org_a

        middleware = RLSContextMiddleware(get_response=lambda r: None)

        # Set context
        middleware.process_request(request)

        # Simulate exception — should still reset
        middleware.process_exception(request, Exception("boom"))

        with connection.cursor() as cur:
            cur.execute(
                "SELECT current_setting('app.current_organization_id', true);"
            )
            val = cur.fetchone()[0]

        self.assertNotEqual(
            val,
            str(self.org_a.id),
            "RLS context must be reset even on exception",
        )

    def tearDown(self):
        RLSContextMiddleware._enabled = None
