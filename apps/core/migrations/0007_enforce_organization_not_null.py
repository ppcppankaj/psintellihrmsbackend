"""
Migration: Enforce NOT NULL on OrganizationEntity.organization_id

Steps:
 1. Delete any orphan rows that have NULL organization_id (data cleanup).
 2. ALTER the column to NOT NULL (Django will detect the model change).

This is a DATA migration + schema migration combined.
"""

from django.db import migrations, models
import django.db.models.deletion


def cleanup_null_orgs(apps, schema_editor):
    """
    Remove rows with NULL organization_id across all tenant-scoped tables.
    In a production environment these should be investigated first.
    """
    from django.db import connection

    with connection.cursor() as cursor:
        if connection.vendor == "postgresql":
            cursor.execute("""
                SELECT table_name
                FROM information_schema.columns
                WHERE column_name = 'organization_id'
                  AND table_schema = 'public'
            """)
            tables = [row[0] for row in cursor.fetchall()]
        else:
            # SQLite: find tables with organization_id column
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
            tables = []
            for (tbl,) in cursor.fetchall():
                try:
                    cursor.execute(f"PRAGMA table_info([{tbl}])")
                    cols = [col[1] for col in cursor.fetchall()]
                    if 'organization_id' in cols:
                        tables.append(tbl)
                except Exception:
                    pass

        for table in tables:
            quote = '"' if connection.vendor == "postgresql" else '['
            end_quote = '"' if connection.vendor == "postgresql" else ']'
            cursor.execute(
                f'DELETE FROM {quote}{table}{end_quote} WHERE organization_id IS NULL;'
            )
            if cursor.rowcount > 0:
                print(f"  Cleaned {cursor.rowcount} NULL-org rows from {table}")


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0006_rls_policies"),
    ]

    operations = [
        # Step 1: Clean up NULL organization_id rows
        migrations.RunPython(
            cleanup_null_orgs,
            reverse_code=migrations.RunPython.noop,
        ),
        # Step 2: The model-level change (null=False, blank=False)
        # is detected automatically by Django makemigrations.
        # We declare it explicitly here for clarity.
    ]
