"""
System Diagnostics Management Command
Validates all prerequisites for application startup
"""

import sys
from django.core.management.base import BaseCommand
from django.db import connection
from django.core.cache import cache
from django.contrib.auth import get_user_model

User = get_user_model()


class Command(BaseCommand):
    help = 'Run system diagnostics and validate prerequisites'
    
    def handle(self, *args, **options):
        """Run all diagnostic checks"""
        self.stdout.write("=" * 70)
        self.stdout.write(self.style.SUCCESS("SYSTEM DIAGNOSTICS"))
        self.stdout.write("=" * 70)
        self.stdout.write("")
        
        checks = [
            self._check_database,
            self._check_migrations,
            self._check_main_organization,
            self._check_superuser,
            self._check_redis,
        ]
        
        passed = 0
        failed = 0
        warnings = 0
        
        for check in checks:
            result = check()
            if result == 'pass':
                passed += 1
            elif result == 'fail':
                failed += 1
            else:
                warnings += 1
        
        # Summary
        self.stdout.write("")
        self.stdout.write("=" * 70)
        if failed == 0:
            self.stdout.write(
                self.style.SUCCESS(f"[OK] DIAGNOSTICS PASSED: {passed} checks passed, {warnings} warnings")
            )
        else:
            self.stdout.write(
                self.style.ERROR(f"[FAIL] DIAGNOSTICS FAILED: {failed} checks failed, {warnings} warnings")
            )
        self.stdout.write("=" * 70)
        self.stdout.write("")
        
        # Exit with error code if any checks failed
        if failed > 0:
            sys.exit(1)
    
    def _check_database(self):
        """Check database connectivity"""
        self.stdout.write("> Checking database connection...")
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1")
            self.stdout.write(self.style.SUCCESS("  [OK] Database connected"))
            return 'pass'
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"  [FAIL] Database connection failed: {e}"))
            return 'fail'
    
    def _check_migrations(self):
        """Check if all migrations are applied"""
        self.stdout.write("> Checking migrations...")
        try:
            from django.db.migrations.executor import MigrationExecutor
            executor = MigrationExecutor(connection)
            plan = executor.migration_plan(executor.loader.graph.leaf_nodes())
            
            if plan:
                self.stdout.write(
                    self.style.WARNING(f"  [WARN] {len(plan)} unapplied migrations found")
                )
                return 'warn'
            else:
                self.stdout.write(self.style.SUCCESS("  [OK] All migrations applied"))
                return 'pass'
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"  [FAIL] Migration check failed: {e}"))
            return 'fail'
    
    def _check_main_organization(self):
        """Check if at least one organization exists"""
        self.stdout.write("> Checking organizations...")
        try:
            from apps.core.models import Organization
            org = Organization.objects.first()
            
            if org:
                self.stdout.write(self.style.SUCCESS(f"  [OK] Organization exists: {org.name}"))
                return 'pass'
            else:
                self.stdout.write(self.style.ERROR("  [FAIL] No organization found! Run: python manage.py seed_data"))
                return 'fail'
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"  [FAIL] Organization check failed: {e}"))
            return 'fail'
    
    def _check_superuser(self):
        """Check if at least one superuser exists"""
        self.stdout.write("> Checking superuser...")
        try:
            superuser = User.objects.filter(is_superuser=True).first()
            
            if superuser:
                self.stdout.write(
                    self.style.SUCCESS(f"  [OK] Superuser exists: {superuser.email}")
                )
                return 'pass'
            else:
                self.stdout.write(
                    self.style.WARNING("  [WARN] No superuser found")
                )
                return 'warn'
        except Exception as e:
            self.stdout.write(self.style.WARNING(f"  [WARN] Superuser check failed: {e}"))
            return 'warn'
    
    def _check_redis(self):
        """Check Redis connectivity"""
        self.stdout.write("> Checking Redis...")
        try:
            cache.set('diagnostic_test', 'ok', 10)
            result = cache.get('diagnostic_test')
            
            if result == 'ok':
                self.stdout.write(self.style.SUCCESS("  [OK] Redis connected"))
                return 'pass'
            else:
                self.stdout.write(self.style.ERROR("  [FAIL] Redis test failed"))
                return 'fail'
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"  [FAIL] Redis connection failed: {e}"))
            return 'fail'
