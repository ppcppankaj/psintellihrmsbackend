#!/usr/bin/env python
"""
RLS Certification Audit
========================
Verifies PostgreSQL Row-Level Security is correctly configured:

  1. All tenant tables have RLS ENABLED
  2. All tenant tables have FORCE RLS
  3. org_isolation_policy exists (SELECT/UPDATE/DELETE)
  4. org_insert_policy exists (INSERT)
  5. prevent_org_change trigger exists on every table
  6. organization_id column is NOT NULL
  7. organization_id index exists

Usage:
    python manage.py shell < scripts/rls_audit.py
    # Or:
    python scripts/rls_audit.py   (if DJANGO_SETTINGS_MODULE is set)

Exit codes:
    0 = All checks pass
    1 = One or more failures detected
"""

import os
import sys
import django

# ── Bootstrap Django ──────────────────────────────────────────────────────────
if not os.environ.get("DJANGO_SETTINGS_MODULE"):
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.production")

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

django.setup()

from django.db import connection


# ── Tenant tables — must match migration 0006 ────────────────────────────────
# Import from migration to stay in sync
try:
    from apps.core.migrations.rls_policies_tables import TENANT_TABLES
except ImportError:
    # Fallback: read from the migration file itself
    TENANT_TABLES = None

if not TENANT_TABLES:
    # Hard-coded fallback — keep in sync with 0006_rls_policies.py
    from importlib import import_module
    try:
        m = import_module("apps.core.migrations.0006_rls_policies")
        TENANT_TABLES = m.TENANT_TABLES
    except (ImportError, AttributeError):
        print("ERROR: Cannot import TENANT_TABLES from migration.")
        print("Please update this script or set TENANT_TABLES manually.")
        sys.exit(2)


def is_postgres():
    return connection.vendor == "postgresql"


def run_audit():
    if not is_postgres():
        print("=" * 72)
        print("  RLS AUDIT — SKIPPED (not PostgreSQL)")
        print("  Current database engine:", connection.vendor)
        print("=" * 72)
        return True

    print("=" * 72)
    print("  RLS CERTIFICATION AUDIT")
    print("  Tables to verify:", len(TENANT_TABLES))
    print("=" * 72)

    failures = []
    warnings = []
    passed = 0

    with connection.cursor() as cursor:
        for table in TENANT_TABLES:
            table_issues = []

            # --- Check table exists ---
            cursor.execute("""
                SELECT EXISTS (
                    SELECT 1 FROM information_schema.tables
                    WHERE table_schema = 'public' AND table_name = %s
                )
            """, [table])
            exists = cursor.fetchone()[0]
            if not exists:
                warnings.append(f"  WARN: Table '{table}' does not exist (may be renamed or dropped)")
                continue

            # --- 1. RLS Enabled ---
            cursor.execute("""
                SELECT relrowsecurity FROM pg_class
                WHERE relname = %s AND relnamespace = 'public'::regnamespace
            """, [table])
            row = cursor.fetchone()
            if not row or not row[0]:
                table_issues.append("RLS not ENABLED")

            # --- 2. FORCE RLS ---
            cursor.execute("""
                SELECT relforcerowsecurity FROM pg_class
                WHERE relname = %s AND relnamespace = 'public'::regnamespace
            """, [table])
            row = cursor.fetchone()
            if not row or not row[0]:
                table_issues.append("FORCE RLS not set")

            # --- 3. org_isolation_policy ---
            cursor.execute("""
                SELECT polname FROM pg_policy
                WHERE polrelid = %s::regclass
                  AND polname = 'org_isolation_policy'
            """, [table])
            if not cursor.fetchone():
                table_issues.append("Missing org_isolation_policy")

            # --- 4. org_insert_policy ---
            cursor.execute("""
                SELECT polname FROM pg_policy
                WHERE polrelid = %s::regclass
                  AND polname = 'org_insert_policy'
            """, [table])
            if not cursor.fetchone():
                table_issues.append("Missing org_insert_policy")

            # --- 5. prevent_org_change trigger ---
            cursor.execute("""
                SELECT tgname FROM pg_trigger
                WHERE tgrelid = %s::regclass
                  AND (tgname LIKE 'no_org_update_%%' OR tgname LIKE 'trg_prevent_org_change%%')
                  AND NOT tgisinternal
            """, [table])
            if not cursor.fetchone():
                table_issues.append("Missing prevent_org_change trigger")

            # --- 6. organization_id NOT NULL ---
            cursor.execute("""
                SELECT is_nullable FROM information_schema.columns
                WHERE table_schema = 'public'
                  AND table_name = %s
                  AND column_name = 'organization_id'
            """, [table])
            row = cursor.fetchone()
            if not row:
                table_issues.append("organization_id column missing")
            elif row[0] == "YES":
                table_issues.append("organization_id allows NULL")

            # --- 7. organization_id index ---
            cursor.execute("""
                SELECT indexname FROM pg_indexes
                WHERE tablename = %s
                  AND indexdef LIKE '%%organization_id%%'
            """, [table])
            if not cursor.fetchone():
                table_issues.append("No index on organization_id")

            if table_issues:
                failures.append((table, table_issues))
            else:
                passed += 1

    # ── Report ───────────────────────────────────────────────────────────
    print()
    if warnings:
        print("WARNINGS:")
        for w in warnings:
            print(w)
        print()

    if failures:
        print("FAILURES:")
        for table, issues in failures:
            print(f"  ✗ {table}")
            for issue in issues:
                print(f"      - {issue}")
        print()

    total = passed + len(failures)
    print("-" * 72)
    print(f"  PASSED:   {passed}/{total}")
    print(f"  FAILED:   {len(failures)}/{total}")
    print(f"  WARNINGS: {len(warnings)}")
    print("-" * 72)

    if failures:
        print("  VERDICT: ✗ FAIL — RLS configuration incomplete")
        return False
    else:
        print("  VERDICT: ✓ PASS — All RLS checks passed")
        return True


if __name__ == "__main__":
    success = run_audit()
    sys.exit(0 if success else 1)
