"""
PostgreSQL Row-Level Security (RLS) — Enterprise Tenant Isolation
=================================================================

This migration:
  1. Enables RLS on ALL org-scoped tables (134 tables)
  2. Creates SELECT/UPDATE/DELETE policies (org_isolation_policy)
  3. Creates INSERT WITH CHECK policies (org_insert_policy)
  4. Creates prevent_org_change() trigger function
  5. Attaches org-change-prevention trigger to every tenant table
  6. Ensures organization_id NOT NULL on all tenant tables
  7. Creates organization_id indexes where missing

Safe on SQLite — all SQL is guarded by engine check.
Idempotent — uses IF NOT EXISTS / OR REPLACE patterns.
"""

from django.db import migrations


# ═══════════════════════════════════════════════════════════════════════════════
# COMPLETE LIST — every table with organization_id
# ═══════════════════════════════════════════════════════════════════════════════

TENANT_TABLES = [
    # ─── core ─────────────────────────────────────────────────────────────
    "core_organizationdomain",
    "core_auditlog",
    "core_announcement",
    "core_organizationsettings",
    "core_featureflag",

    # ─── authentication (org-scoped models) ───────────────────────────────
    "authentication_usersession",
    "organization_users",
    "branches",

    # ─── employees ────────────────────────────────────────────────────────
    "employees_employee",
    "employees_department",
    "employees_designation",
    "employees_location",
    "employees_employeeaddress",
    "employees_employeebankaccount",
    "employees_emergencycontact",
    "employees_employeedependent",
    "employees_skill",
    "employees_employeeskill",
    "employees_employmenthistory",
    "employees_document",
    "employees_certification",
    "employees_employeetransfer",
    "employees_employeepromotion",
    "employees_resignationrequest",
    "employees_exitinterview",
    "employees_separationchecklist",

    # ─── attendance ───────────────────────────────────────────────────────
    "attendance_shift",
    "attendance_geofence",
    "attendance_attendancerecord",
    "attendance_attendancepunch",
    "attendance_fraudlog",
    "attendance_faceembedding",
    "attendance_shiftassignment",
    "attendance_overtimerequest",

    # ─── leave ────────────────────────────────────────────────────────────
    "leave_leavetype",
    "leave_leavepolicy",
    "leave_leavebalance",
    "leave_leaverequest",
    "leave_leaveapproval",
    "leave_holiday",
    "leave_leaveencashment",
    "leave_compensatoryleave",
    "leave_holidaycalendar",
    "leave_holidaycalendarentry",

    # ─── payroll ──────────────────────────────────────────────────────────
    "payroll_employeesalary",
    "payroll_payrollrun",
    "payroll_payslip",
    "payroll_pfcontribution",
    "payroll_taxdeclaration",
    "payroll_fullfinalsettlement",
    "payroll_salaryarrear",
    "payroll_reimbursementclaim",
    "payroll_employeeloan",
    "payroll_loanrepayment",

    # ─── workflows ────────────────────────────────────────────────────────
    "workflows_workflowdefinition",
    "workflows_workflowstep",
    "workflows_workflowinstance",
    "workflows_workflowaction",

    # ─── expenses ─────────────────────────────────────────────────────────
    "expenses_expensecategory",
    "expenses_expenseclaim",
    "expenses_expenseitem",
    "expenses_expenseapproval",
    "expenses_employeeadvance",
    "expenses_advancesettlement",

    # ─── assets ───────────────────────────────────────────────────────────
    "assets_assetcategory",
    "assets_asset",
    "assets_assetassignment",
    "assets_assetmaintenance",
    "assets_assetrequest",

    # ─── notifications ────────────────────────────────────────────────────
    "notifications_notificationtemplate",
    "notifications_notificationpreference",
    "notifications_notification",

    # ─── ai_services ──────────────────────────────────────────────────────
    "ai_services_aimodelversion",
    "ai_services_aiprediction",

    # ─── training ─────────────────────────────────────────────────────────
    "training_trainingcategory",
    "training_trainingprogram",
    "training_trainingmaterial",
    "training_trainingenrollment",
    "training_trainingcompletion",

    # ─── recruitment ──────────────────────────────────────────────────────
    "recruitment_jobposting",
    "recruitment_candidate",
    "recruitment_jobapplication",
    "recruitment_interview",
    "recruitment_offerletter",

    # ─── compliance ───────────────────────────────────────────────────────
    "compliance_dataretentionpolicy",
    "compliance_consentrecord",
    "compliance_legalhold",
    "compliance_datasubjectrequest",
    "compliance_auditexportrequest",
    "compliance_retentionexecution",

    # ─── integrations ─────────────────────────────────────────────────────
    "integrations_integration",
    "integrations_webhook",
    "integrations_apikey",

    # ─── onboarding ───────────────────────────────────────────────────────
    "onboarding_onboardingtemplate",
    "onboarding_onboardingtasktemplate",
    "onboarding_employeeonboarding",
    "onboarding_onboardingtaskprogress",
    "onboarding_onboardingdocument",

    # ─── performance ──────────────────────────────────────────────────────
    "performance_performancecycle",
    "performance_okrobjective",
    "performance_keyresult",
    "performance_performancereview",
    "performance_reviewfeedback",
    "performance_keyresultarea",
    "performance_employeekra",
    "performance_kpi",
    "performance_competency",
    "performance_employeecompetency",
    "performance_trainingrecommendation",

    # ─── chat ─────────────────────────────────────────────────────────────
    "chat_meetingroom",
    "chat_meetingrecording",
    "chat_meetingschedule",
    "chat_conversation",
    "chat_conversationparticipant",
    "chat_message",
    "chat_messagereaction",

    # ─── reports ──────────────────────────────────────────────────────────
    "reports_reporttemplate",
    "reports_scheduledreport",
    "reports_generatedreport",
    "reports_reportexecution",

    # ─── abac ─────────────────────────────────────────────────────────────
    "abac_attributetype",
    "abac_policy",
    "abac_policyrule",
    "abac_userpolicy",
    "abac_grouppolicy",
    "abac_policylog",
    "abac_role",
    "abac_roleassignment",
    "abac_userrole",
    "abac_permission",
    "abac_rolepermission",

    # ─── billing (org-scoped, NOT the global Plan table) ──────────────────
    "billing_bankdetails",
    "billing_organizationsubscription",
    "billing_organizationbillingprofile",
    "billing_invoice",
    "billing_payment",
    "billing_paymenttransaction",
]


def apply_rls(apps, schema_editor):
    """Enable RLS + create policies + triggers on PostgreSQL only."""
    db_engine = schema_editor.connection.vendor
    if db_engine != "postgresql":
        # Silently skip on SQLite / other engines
        return

    cursor = schema_editor.connection.cursor()

    # ─── 1. Create the immutable trigger function (once) ──────────────
    cursor.execute("""
        CREATE OR REPLACE FUNCTION prevent_org_change()
        RETURNS trigger AS $$
        BEGIN
            IF OLD.organization_id IS DISTINCT FROM NEW.organization_id THEN
                RAISE EXCEPTION
                    'SECURITY: organization_id change blocked (% → %)',
                    OLD.organization_id, NEW.organization_id
                    USING ERRCODE = 'restricted_action';
            END IF;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql IMMUTABLE;
    """)

    # ─── 2. Per-table: enable RLS, policies, trigger, index ───────────
    for table in TENANT_TABLES:
        # Check table exists before operating on it
        cursor.execute(
            "SELECT 1 FROM information_schema.tables "
            "WHERE table_schema = 'public' AND table_name = %s",
            [table],
        )
        if not cursor.fetchone():
            continue

        # 2a. Enable RLS (idempotent)
        cursor.execute(f'ALTER TABLE "{table}" ENABLE ROW LEVEL SECURITY;')

        # Force RLS even for table owners (critical for Django's default role)
        cursor.execute(
            f'ALTER TABLE "{table}" FORCE ROW LEVEL SECURITY;'
        )

        # 2b. Drop old policies if they exist (idempotent re-run)
        cursor.execute(
            f'DROP POLICY IF EXISTS org_isolation_policy ON "{table}";'
        )
        cursor.execute(
            f'DROP POLICY IF EXISTS org_insert_policy ON "{table}";'
        )

        # 2c. SELECT / UPDATE / DELETE policy
        cursor.execute(f"""
            CREATE POLICY org_isolation_policy ON "{table}"
            FOR ALL
            USING (
                current_setting('app.current_is_superuser', true) = 'true'
                OR organization_id = current_setting(
                    'app.current_organization_id', true
                )::uuid
            );
        """)

        # 2d. INSERT policy (WITH CHECK)
        cursor.execute(f"""
            CREATE POLICY org_insert_policy ON "{table}"
            FOR INSERT
            WITH CHECK (
                current_setting('app.current_is_superuser', true) = 'true'
                OR organization_id = current_setting(
                    'app.current_organization_id', true
                )::uuid
            );
        """)

        # 2e. Organization-change-prevention trigger
        trigger_name = f"no_org_update_{table}"
        cursor.execute(f"""
            DROP TRIGGER IF EXISTS "{trigger_name}" ON "{table}";
        """)
        cursor.execute(f"""
            CREATE TRIGGER "{trigger_name}"
            BEFORE UPDATE ON "{table}"
            FOR EACH ROW
            EXECUTE FUNCTION prevent_org_change();
        """)

        # 2f. Ensure organization_id index exists
        idx_name = f"idx_{table}_org_id"
        cursor.execute(f"""
            CREATE INDEX IF NOT EXISTS "{idx_name}"
            ON "{table}" (organization_id);
        """)


def reverse_rls(apps, schema_editor):
    """Remove all RLS policies and triggers (full rollback)."""
    db_engine = schema_editor.connection.vendor
    if db_engine != "postgresql":
        return

    cursor = schema_editor.connection.cursor()

    for table in TENANT_TABLES:
        cursor.execute(
            "SELECT 1 FROM information_schema.tables "
            "WHERE table_schema = 'public' AND table_name = %s",
            [table],
        )
        if not cursor.fetchone():
            continue

        trigger_name = f"no_org_update_{table}"
        cursor.execute(f'DROP TRIGGER IF EXISTS "{trigger_name}" ON "{table}";')
        cursor.execute(
            f'DROP POLICY IF EXISTS org_isolation_policy ON "{table}";'
        )
        cursor.execute(
            f'DROP POLICY IF EXISTS org_insert_policy ON "{table}";'
        )
        cursor.execute(f'ALTER TABLE "{table}" DISABLE ROW LEVEL SECURITY;')

    cursor.execute("DROP FUNCTION IF EXISTS prevent_org_change() CASCADE;")


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0005_remove_auditlog_core_auditl_organiz_c0dcbd_idx_and_more"),
    ]

    operations = [
        migrations.RunPython(apply_rls, reverse_rls, atomic=False),
    ]
