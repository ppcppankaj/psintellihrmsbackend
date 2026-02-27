"""
Seed Permissions - Auto-create standard permissions for all HRMS modules
Run with: python manage.py seed_permissions
"""

from django.core.management.base import BaseCommand
from apps.abac.models import Permission, Role, RolePermission
# Legacy RBAC models - update to use ABAC policies instead


# Define all modules and their standard actions
MODULES = {
    'employees': ['view', 'create', 'update', 'delete', 'export'],
    'attendance': ['view', 'create', 'update', 'delete', 'approve'],
    'leave': ['view', 'create', 'update', 'delete', 'approve'],
    'payroll': ['view', 'create', 'update', 'delete', 'approve', 'export'],
    'performance': ['view', 'create', 'update', 'delete', 'approve', 'review'],
    'recruitment': ['view', 'create', 'update', 'delete', 'interview'],
    'workflows': ['view', 'create', 'update', 'delete', 'approve'],
    'reports': ['view', 'export'],
    'billing': ['view', 'create', 'update', 'delete'],
    'settings': ['view', 'update'],
    'rbac': ['view', 'create', 'update', 'delete'],
    'assets': ['view', 'create', 'update', 'delete', 'assign', 'export'],
    'expenses': ['view', 'create', 'update', 'delete', 'approve', 'pay'],
    'onboarding': ['view', 'create', 'update', 'delete', 'approve'],
    'compliance': ['view', 'create', 'update', 'delete', 'audit'],
    'tenants': ['view', 'create', 'update', 'delete', 'configure'],
    'notifications': ['view', 'send', 'configure'],
    'ai_services': ['view', 'use', 'configure'],
    'integrations': ['view', 'configure', 'sync'],
    'core': ['view', 'configure'],
    'abac': ['view', 'create', 'update', 'delete'],
}

# Human-readable action names
ACTION_NAMES = {
    'view': 'View',
    'create': 'Create',
    'update': 'Update',
    'delete': 'Delete',
    'approve': 'Approve',
    'export': 'Export',
    'import': 'Import',
    'review': 'Review',
    'interview': 'Interview',
    'assign': 'Assign',
    'pay': 'Pay',
    'audit': 'Audit',
    'configure': 'Configure',
    'send': 'Send',
    'use': 'Use',
    'sync': 'Sync',
}

# Default roles and their permissions
DEFAULT_ROLES = {
    'super_admin': '*',  # All permissions
    'hr_admin': [
        'employees.*', 'attendance.*', 'leave.*', 'payroll.*', 'performance.*', 
        'recruitment.*', 'workflows.*', 'reports.*', 'assets.*', 'expenses.*',
        'onboarding.*', 'compliance.*', 'notifications.view', 'notifications.send',
        'settings.*', 'abac.*'
    ],
    'hr_manager': [
        'employees.view', 'employees.update', 'attendance.*', 'leave.*', 
        'performance.view', 'performance.review', 'reports.view', 'assets.view',
        'onboarding.view', 'onboarding.approve', 'expenses.view', 'expenses.approve'
    ],
    'manager': [
        'employees.view', 'attendance.view', 'attendance.approve', 'leave.view', 
        'leave.approve', 'performance.view', 'performance.create', 'performance.review',
        'expenses.view', 'expenses.create', 'expenses.approve', 'assets.view'
    ],
    'employee': [
        'employees.view', 'attendance.view', 'attendance.create', 'leave.view', 
        'leave.create', 'performance.view', 'expenses.view', 'expenses.create',
        'assets.view'
    ],
    'payroll_manager': [
        'employees.view', 'payroll.*', 'reports.*', 'expenses.view', 'expenses.pay'
    ],
    'recruiter': [
        'recruitment.*', 'employees.view', 'onboarding.*'
    ],
}


class Command(BaseCommand):
    help = 'Seed standard permissions and default roles'

    def handle(self, *args, **options):
        self.stdout.write('Seeding permissions...')
        
        permissions_created = 0
        
        # Create permissions for each module
        for module, actions in MODULES.items():
            for action in actions:
                code = f"{module}.{action}"
                name = f"{module.replace('_', ' ').title()} - {ACTION_NAMES.get(action, action.title())}"
                
                perm, created = Permission.objects.get_or_create(
                    code=code,
                    defaults={
                        'name': name,
                        'module': module,
                        'action': action,
                        'permission_type': 'module',
                        'description': f"Allows {action} access to {module}",
                    }
                )
                
                if created:
                    permissions_created += 1
                    self.stdout.write(f"  Created: {code}")
        
        self.stdout.write(self.style.SUCCESS(f'Created {permissions_created} permissions'))
        
        # Create default roles
        self.stdout.write('\nSeeding default roles...')
        roles_created = 0
        
        role_levels = {
            'super_admin': 0,
            'hr_admin': 1,
            'hr_manager': 2,
            'payroll_manager': 2,
            'manager': 3,
            'recruiter': 3,
            'employee': 4,
        }
        
        for role_code, perms in DEFAULT_ROLES.items():
            role, created = Role.objects.get_or_create(
                code=role_code,
                is_system_role=True,
                defaults={
                    'name': role_code.replace('_', ' ').title(),
                    'is_tenant_role': False,
                    'level': role_levels.get(role_code, 5),
                    'description': f"System role: {role_code.replace('_', ' ').title()}",
                }
            )
            
            if created:
                roles_created += 1
                self.stdout.write(f"  Created role: {role_code}")
            
            # Assign permissions to role
            if perms == '*':
                # All permissions
                all_perms = Permission.objects.all()
                for perm in all_perms:
                    RolePermission.objects.get_or_create(role=role, permission=perm)
            else:
                for perm_pattern in perms:
                    if perm_pattern.endswith('.*'):
                        # Wildcard - all permissions for module
                        module = perm_pattern.replace('.*', '')
                        module_perms = Permission.objects.filter(module=module)
                        for perm in module_perms:
                            RolePermission.objects.get_or_create(role=role, permission=perm)
                    else:
                        # Specific permission
                        try:
                            perm = Permission.objects.get(code=perm_pattern)
                            RolePermission.objects.get_or_create(role=role, permission=perm)
                        except Permission.DoesNotExist:
                            pass
        
        self.stdout.write(self.style.SUCCESS(f'Created {roles_created} roles'))
        self.stdout.write(self.style.SUCCESS('\nDone! RBAC seeding complete.'))
