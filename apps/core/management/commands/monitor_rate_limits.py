"""
Management command: Monitor rate limit usage per tenant
"""

from django.core.management.base import BaseCommand
from django.db import connections
from apps.core.models import Organization
from django.core.cache import cache
import time


class Command(BaseCommand):
    help = 'Monitor rate limit usage across all tenants'

    def add_arguments(self, parser):
        parser.add_argument(
            '--tenant',
            type=str,
            help='Monitor specific organization',
        )
        parser.add_argument(
            '--high-usage',
            action='store_true',
            help='Only show organizations approaching limits',
        )
        parser.add_argument(
            '--watch',
            action='store_true',
            help='Continuous monitoring (refresh every 5 seconds)',
        )

    def handle(self, *args, **options):
        organization_slug = options.get('tenant')
        high_usage_only = options.get('high_usage', False)
        watch_mode = options.get('watch', False)

        try:
                self._report_organization(organization_slug, high_usage_only)
        except KeyboardInterrupt:
            self.stdout.write(self.style.WARNING('\nMonitoring stopped'))

    def _report_mode(self, organization_slug, high_usage_only):
        """One-time report of rate limit usage."""
        self.stdout.write(self.style.SUCCESS('=== Rate Limit Usage Report ===\n'))

        if organization_slug:
            self._report_organization(organization_slug, high_usage_only)
        else:
            self._report_all_organizations(high_usage_only)

    def _watch_mode(self, organization_slug, high_usage_only):
        """Continuous monitoring."""
        self.stdout.write(self.style.SUCCESS('=== Rate Limit Monitoring (LIVE) ==='))
        self.stdout.write('(Press Ctrl+C to stop)\n')

        while True:
            # Clear screen
            self.stdout.write('\033[2J\033[H')  # ANSI clear

            self.stdout.write(self.style.SUCCESS(f'[{time.strftime("%H:%M:%S")}] Rate Limit Usage'))
            self.stdout.write('=' * 80)

            if organization_slug:
                self._report_organization(organization_slug, high_usage_only)
            else:
                self._report_all_organizations(high_usage_only)

            time.sleep(5)

    def _report_all_organizations(self, high_usage_only=False):
        """Report all organizations."""
        orgs = Organization.objects.all()

        if not orgs.exists():
            self.stdout.write(self.style.WARNING('No organizations found'))
            return

        # Header
        self.stdout.write(
            f'{"Organization":<25} {"Minute":<15} {"Hour":<15} {"Status":<20}'
        )
        self.stdout.write('-' * 80)

        for org in orgs:
            stats = get_rate_limit_stats(org.slug)
            
            if high_usage_only and stats['percentage_minute'] < 80:
                continue

            self._print_organization_stats(org.slug, stats)

    def _report_organization(self, organization_slug, high_usage_only):
        """Report single organization."""
        try:
            org = Organization.objects.get(slug=organization_slug)
        except Organization.DoesNotExist:
            self.stdout.write(
                self.style.ERROR(f'Organization "{organization_slug}" not found')
            )
            return

        stats = get_rate_limit_stats(organization_slug)

        self.stdout.write(f'\nOrganization: {org.name} ({organization_slug})')
        self.stdout.write('-' * 50)
        self.stdout.write(
            f'Requests this minute: {stats["requests_this_minute"]}'
            f'/{stats["limit_per_minute"]} '
            f'({stats["percentage_minute"]:.1f}%)'
        )
        self.stdout.write(
            f'Requests this hour:   {stats["requests_this_hour"]}'
            f'/{stats["limit_per_hour"]} '
            f'({stats["percentage_hour"]:.1f}%)'
        )

        if stats['approaching_limit']:
            self.stdout.write(
                self.style.WARNING('⚠️  Approaching rate limit!')
            )
        else:
            self.stdout.write(
                self.style.SUCCESS('✓ Within normal limits')
            )

    def _print_organization_stats(self, organization_slug, stats):
        """Print single organization stats in table row."""
        minute_status = f"{stats['requests_this_minute']}/{stats['limit_per_minute']}"
        hour_status = f"{stats['requests_this_hour']}/{stats['limit_per_hour']}"

        # Determine status color
        if stats['percentage_minute'] > 90:
            status_text = self.style.ERROR(f"🔴 {stats['percentage_minute']:.0f}%")
        elif stats['percentage_minute'] > 75:
            status_text = self.style.WARNING(f"🟡 {stats['percentage_minute']:.0f}%")
        else:
            status_text = self.style.SUCCESS(f"🟢 {stats['percentage_minute']:.0f}%")

        self.stdout.write(
            f'{organization_slug:<25} {minute_status:<15} {hour_status:<15} {status_text}'
        )
