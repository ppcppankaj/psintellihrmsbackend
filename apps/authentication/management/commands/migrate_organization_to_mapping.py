"""
Data Migration: User.organization → OrganizationUser Mapping
===========================================================

This script migrates existing direct organization assignments to the new
hierarchical mapping model.

BEFORE RUNNING:
1. Backup database
2. Test on staging environment
3. Run migrations to create new tables

MIGRATION STEPS:
1. Create OrganizationUser records from existing User.organization
2. Migrate is_org_admin flag to OrganizationUser.role
3. Verify all users have organization assignments
4. Mark User.organization as deprecated (keep for backward compatibility)
"""

from django.core.management.base import BaseCommand
from django.db import transaction
from apps.authentication.models import User
from apps.authentication.models_hierarchy import OrganizationUser
from apps.core.models import Organization


class Command(BaseCommand):
    help = 'Migrate User.organization to OrganizationUser mapping model'
    
    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Run in dry-run mode without making changes',
        )
        parser.add_argument(
            '--force',
            action='store_true',
            help='Force migration even if OrganizationUser records exist',
        )
    
    def handle(self, *args, **options):
        dry_run = options['dry_run']
        force = options['force']
        
        if dry_run:
            self.stdout.write(self.style.WARNING('Running in DRY-RUN mode'))
        
        # Check if migration already done
        existing_count = OrganizationUser.objects.count()
        if existing_count > 0 and not force:
            self.stdout.write(
                self.style.ERROR(
                    f'OrganizationUser table already has {existing_count} records. '
                    'Use --force to migrate anyway.'
                )
            )
            return
        
        # Get users with organization assignments
        users_with_org = User.objects.filter(
            organization__isnull=False
        ).select_related('organization')
        
        total_users = users_with_org.count()
        self.stdout.write(f'Found {total_users} users with organization assignments')
        
        if total_users == 0:
            self.stdout.write(self.style.SUCCESS('No users to migrate'))
            return
        
        # Statistics
        created_count = 0
        updated_count = 0
        error_count = 0
        
        try:
            with transaction.atomic():
                for user in users_with_org:
                    try:
                        # Determine role from is_org_admin flag
                        role = (OrganizationUser.RoleChoices.ORG_ADMIN 
                                if user.is_org_admin 
                                else OrganizationUser.RoleChoices.EMPLOYEE)
                        
                        # Check if mapping already exists
                        org_user, created = OrganizationUser.objects.get_or_create(
                            user=user,
                            organization=user.organization,
                            defaults={
                                'role': role,
                                'is_active': user.is_active,
                                'created_by': None,  # System migration
                            }
                        )
                        
                        if created:
                            created_count += 1
                            self.stdout.write(
                                self.style.SUCCESS(
                                    f'✓ Created OrganizationUser: {user.email} → '
                                    f'{user.organization.name} ({role})'
                                )
                            )
                        else:
                            # Update existing record if needed
                            if org_user.role != role or org_user.is_active != user.is_active:
                                org_user.role = role
                                org_user.is_active = user.is_active
                                if not dry_run:
                                    org_user.save()
                                updated_count += 1
                                self.stdout.write(
                                    self.style.WARNING(
                                        f'⟳ Updated OrganizationUser: {user.email}'
                                    )
                                )
                            
                    except Exception as e:
                        error_count += 1
                        self.stdout.write(
                            self.style.ERROR(
                                f'✗ Error migrating {user.email}: {str(e)}'
                            )
                        )
                
                if dry_run:
                    self.stdout.write(
                        self.style.WARNING('\n=== DRY RUN - NO CHANGES MADE ===')
                    )
                    raise Exception('Dry run - rolling back transaction')
        
        except Exception as e:
            if not dry_run:
                self.stdout.write(self.style.ERROR(f'\nMigration failed: {str(e)}'))
                return
        
        # Summary
        self.stdout.write('\n' + '='*60)
        self.stdout.write(self.style.SUCCESS('MIGRATION SUMMARY:'))
        self.stdout.write(f'Total users with organization: {total_users}')
        self.stdout.write(f'Created OrganizationUser records: {created_count}')
        self.stdout.write(f'Updated OrganizationUser records: {updated_count}')
        self.stdout.write(f'Errors: {error_count}')
        self.stdout.write('='*60)
        
        if dry_run:
            self.stdout.write(self.style.WARNING('\nThis was a DRY RUN. Run without --dry-run to apply changes.'))
        else:
            self.stdout.write(self.style.SUCCESS('\n✓ Migration completed successfully!'))
            self.stdout.write('\nNEXT STEPS:')
            self.stdout.write('1. Verify OrganizationUser records in admin')
            self.stdout.write('2. Update application code to use get_organization() method')
            self.stdout.write('3. After testing, consider deprecating User.organization field')
