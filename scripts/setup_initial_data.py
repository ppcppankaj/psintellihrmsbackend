import os
import sys
import django
import uuid

# Add current directory to path
sys.path.append(os.getcwd())

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.base')
django.setup()

from apps.core.models import Organization
from apps.authentication.models import User
from apps.authentication.models_hierarchy import Branch
from django.core.management import call_command

def setup():
    print("Setting up initial data...")

    # 1. Create Organization
    org_name = "PSIntelli HR"
    org, created = Organization.objects.get_or_create(
        name=org_name,
        defaults={
            'email': 'admin@psintellihr.com',
            'is_active': True,
            'subscription_status': 'active'
        }
    )
    if created:
        print(f"Created organization: {org_name}")
    else:
        print(f"Organization already exists: {org_name}")

    # 2. Create Branch
    branch_name = "Main Branch"
    branch, created = Branch.objects.get_or_create(
        organization=org,
        name=branch_name,
        defaults={
            'code': 'MB-001',
            'is_active': True
        }
    )
    if created:
        print(f"Created branch: {branch_name}")
    else:
        print(f"Branch already exists: {branch_name}")

    # 3. Create Superuser
    email = "admin@psintellihr.com"
    if not User.objects.filter(email=email).exists():
        User.objects.create_superuser(
            email=email,
            password="adminpassword123",
            first_name="Admin",
            last_name="User",
            organization=org
        )
        print(f"Created superuser: {email}")
    else:
        print(f"Superuser already exists: {email}")

    # 4. Run Seeders
    print("Running seeders...")
    try:
        call_command('seed_permissions')
        print("Successfully seeded permissions.")
    except Exception as e:
        print(f"Error seeding permissions: {e}")

    try:
        call_command('seed_notification_templates')
        print("Successfully seeded notification templates.")
    except Exception as e:
        print(f"Error seeding notification templates: {e}")

    print("Initial setup complete!")

if __name__ == "__main__":
    setup()
