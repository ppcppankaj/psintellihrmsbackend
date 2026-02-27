"""
Management command to populate branch fields for existing records
Usage: python manage.py populate_branch_fields [--dry-run] [--organization ORG_ID]
"""

from django.core.management.base import BaseCommand
from django.db import transaction
from django.db.models import Count
from apps.core.models import Organization
from apps.authentication.models_hierarchy import Branch
from apps.employees.models import Employee, Department
from apps.attendance.models import Shift, GeoFence, AttendanceRecord, AttendancePunch
from apps.assets.models import Asset, AssetAssignment
from apps.leave.models import LeaveRequest, LeaveApproval, Holiday
from apps.payroll.models import PayrollRun
from apps.recruitment.models import JobPosting, Interview


class Command(BaseCommand):
    help = 'Populate branch fields for existing records that have null branch'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be done without making changes',
        )
        parser.add_argument(
            '--organization',
            type=str,
            help='Process specific organization ID only',
        )
        parser.add_argument(
            '--auto-assign',
            action='store_true',
            help='Automatically assign default branch for single-branch organizations',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        org_id = options.get('organization')
        auto_assign = options['auto_assign']

        self.stdout.write(self.style.WARNING('\n' + '='*80))
        self.stdout.write(self.style.WARNING('Branch Field Population Script'))
        self.stdout.write(self.style.WARNING('='*80 + '\n'))

        if dry_run:
            self.stdout.write(self.style.NOTICE('DRY RUN MODE - No changes will be made\n'))

        # Get organizations to process
        orgs = Organization.objects.all()
        if org_id:
            orgs = orgs.filter(id=org_id)
            if not orgs.exists():
                self.stdout.write(self.style.ERROR(f'Organization {org_id} not found'))
                return

        total_stats = {
            'employees': 0,
            'departments': 0,
            'shifts': 0,
            'geofences': 0,
            'attendance_records': 0,
            'attendance_punches': 0,
            'assets': 0,
            'asset_assignments': 0,
            'leave_requests': 0,
            'leave_approvals': 0,
            'holidays': 0,
            'payroll_runs': 0,
            'job_postings': 0,
            'interviews': 0,
        }

        for org in orgs:
            self.stdout.write(self.style.SUCCESS(f'\nProcessing Organization: {org.name} ({org.id})'))
            self.stdout.write('-' * 80)

            # Get branches for this organization
            branches = Branch.objects.filter(organization=org, is_active=True)
            branch_count = branches.count()

            self.stdout.write(f'Found {branch_count} active branch(es)')

            if branch_count == 0:
                self.stdout.write(self.style.WARNING(
                    f'  ⚠ No active branches found for {org.name}. Skipping.'
                ))
                continue

            default_branch = None
            if branch_count == 1 and auto_assign:
                default_branch = branches.first()
                self.stdout.write(self.style.SUCCESS(
                    f'  ✓ Single branch organization. Will use: {default_branch.name}'
                ))
            elif branch_count > 1:
                self.stdout.write(self.style.WARNING(
                    f'  ⚠ Multi-branch organization. Manual assignment recommended.'
                ))
                if not auto_assign:
                    self.stdout.write('  Use --auto-assign flag for automatic assignment to first branch')
                    continue
                else:
                    default_branch = branches.first()
                    self.stdout.write(self.style.NOTICE(
                        f'  ℹ Auto-assigning to first branch: {default_branch.name}'
                    ))

            if not default_branch:
                continue

            # Process each model
            stats = self._populate_employees(org, default_branch, dry_run)
            total_stats['employees'] += stats
            
            stats = self._populate_departments(org, default_branch, dry_run)
            total_stats['departments'] += stats
            
            stats = self._populate_shifts(org, default_branch, dry_run)
            total_stats['shifts'] += stats
            
            stats = self._populate_geofences(org, default_branch, dry_run)
            total_stats['geofences'] += stats
            
            stats = self._populate_attendance_records(org, default_branch, dry_run)
            total_stats['attendance_records'] += stats
            
            stats = self._populate_attendance_punches(org, default_branch, dry_run)
            total_stats['attendance_punches'] += stats
            
            stats = self._populate_assets(org, default_branch, dry_run)
            total_stats['assets'] += stats
            
            stats = self._populate_asset_assignments(org, default_branch, dry_run)
            total_stats['asset_assignments'] += stats
            
            stats = self._populate_leave_requests(org, default_branch, dry_run)
            total_stats['leave_requests'] += stats
            
            stats = self._populate_leave_approvals(org, default_branch, dry_run)
            total_stats['leave_approvals'] += stats
            
            stats = self._populate_holidays(org, default_branch, dry_run)
            total_stats['holidays'] += stats
            
            stats = self._populate_payroll_runs(org, default_branch, dry_run)
            total_stats['payroll_runs'] += stats
            
            stats = self._populate_job_postings(org, default_branch, dry_run)
            total_stats['job_postings'] += stats
            
            stats = self._populate_interviews(org, default_branch, dry_run)
            total_stats['interviews'] += stats

        # Print summary
        self.stdout.write('\n' + '='*80)
        self.stdout.write(self.style.SUCCESS('SUMMARY'))
        self.stdout.write('='*80)
        
        for model_name, count in total_stats.items():
            if count > 0:
                label = f'  {model_name.replace("_", " ").title()}'
                self.stdout.write(f'{label:<40}: {count:>6} records updated')
        
        if dry_run:
            self.stdout.write('\n' + self.style.NOTICE('DRY RUN COMPLETE - No actual changes made'))
        else:
            self.stdout.write('\n' + self.style.SUCCESS('MIGRATION COMPLETE'))

    def _populate_employees(self, org, branch, dry_run):
        """Populate branch for employees"""
        records = Employee.objects.filter(
            branch__isnull=True,
            is_active=True
        )
        count = records.count()
        
        if count > 0:
            self.stdout.write(f'  Employees: {count} records')
            if not dry_run:
                records.update(branch=branch)
        
        return count

    def _populate_departments(self, org, branch, dry_run):
        """Populate branch for departments"""
        records = Department.objects.filter(
            branch__isnull=True,
            is_active=True
        )
        count = records.count()
        
        if count > 0:
            self.stdout.write(f'  Departments: {count} records')
            if not dry_run:
                records.update(branch=branch)
        
        return count

    def _populate_shifts(self, org, branch, dry_run):
        """Populate branch for shifts"""
        records = Shift.objects.filter(
            branch__isnull=True,
            is_active=True
        )
        count = records.count()
        
        if count > 0:
            self.stdout.write(f'  Shifts: {count} records')
            if not dry_run:
                records.update(branch=branch)
        
        return count

    def _populate_geofences(self, org, branch, dry_run):
        """Populate branch for geofences"""
        records = GeoFence.objects.filter(
            branch__isnull=True,
            is_active=True
        )
        count = records.count()
        
        if count > 0:
            self.stdout.write(f'  Geo-fences: {count} records')
            if not dry_run:
                records.update(branch=branch)
        
        return count

    def _populate_attendance_records(self, org, branch, dry_run):
        """Populate branch for attendance records"""
        records = AttendanceRecord.objects.filter(
            branch__isnull=True
        )
        count = records.count()
        
        if count > 0:
            self.stdout.write(f'  Attendance Records: {count} records')
            if not dry_run:
                records.update(branch=branch)
        
        return count

    def _populate_attendance_punches(self, org, branch, dry_run):
        """Populate branch for attendance punches"""
        records = AttendancePunch.objects.filter(
            branch__isnull=True
        )
        count = records.count()
        
        if count > 0:
            self.stdout.write(f'  Attendance Punches: {count} records')
            if not dry_run:
                records.update(branch=branch)
        
        return count

    def _populate_assets(self, org, branch, dry_run):
        """Populate branch for assets"""
        records = Asset.objects.filter(
            branch__isnull=True
        )
        count = records.count()
        
        if count > 0:
            self.stdout.write(f'  Assets: {count} records')
            if not dry_run:
                records.update(branch=branch)
        
        return count

    def _populate_asset_assignments(self, org, branch, dry_run):
        """Populate branch for asset assignments"""
        records = AssetAssignment.objects.filter(
            branch__isnull=True
        )
        count = records.count()
        
        if count > 0:
            self.stdout.write(f'  Asset Assignments: {count} records')
            if not dry_run:
                records.update(branch=branch)
        
        return count

    def _populate_leave_requests(self, org, branch, dry_run):
        """Populate branch for leave requests"""
        records = LeaveRequest.objects.filter(
            branch__isnull=True
        )
        count = records.count()
        
        if count > 0:
            self.stdout.write(f'  Leave Requests: {count} records')
            if not dry_run:
                records.update(branch=branch)
        
        return count

    def _populate_leave_approvals(self, org, branch, dry_run):
        """Populate branch for leave approvals"""
        records = LeaveApproval.objects.filter(
            branch__isnull=True
        )
        count = records.count()
        
        if count > 0:
            self.stdout.write(f'  Leave Approvals: {count} records')
            if not dry_run:
                records.update(branch=branch)
        
        return count

    def _populate_holidays(self, org, branch, dry_run):
        """Populate branch for holidays"""
        records = Holiday.objects.filter(
            branch__isnull=True
        )
        count = records.count()
        
        if count > 0:
            self.stdout.write(f'  Holidays: {count} records')
            if not dry_run:
                records.update(branch=branch)
        
        return count

    def _populate_payroll_runs(self, org, branch, dry_run):
        """Populate branch for payroll runs"""
        records = PayrollRun.objects.filter(
            branch__isnull=True
        )
        count = records.count()
        
        if count > 0:
            self.stdout.write(f'  Payroll Runs: {count} records')
            if not dry_run:
                records.update(branch=branch)
        
        return count

    def _populate_job_postings(self, org, branch, dry_run):
        """Populate branch for job postings"""
        records = JobPosting.objects.filter(
            branch__isnull=True
        )
        count = records.count()
        
        if count > 0:
            self.stdout.write(f'  Job Postings: {count} records')
            if not dry_run:
                records.update(branch=branch)
        
        return count

    def _populate_interviews(self, org, branch, dry_run):
        """Populate branch for interviews"""
        records = Interview.objects.filter(
            branch__isnull=True
        )
        count = records.count()
        
        if count > 0:
            self.stdout.write(f'  Interviews: {count} records')
            if not dry_run:
                records.update(branch=branch)
        
        return count
