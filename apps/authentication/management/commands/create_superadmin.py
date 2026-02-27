"""
Management command to create a superadmin user
"""

from django.core.management.base import BaseCommand
from apps.authentication.models import User


class Command(BaseCommand):
    help = 'Create a superadmin user'

    def add_arguments(self, parser):
        parser.add_argument('--email', type=str, default='admin@intellihr.com', help='Admin email')
        parser.add_argument('--password', type=str, default='Admin@123', help='Admin password')
        parser.add_argument('--first-name', type=str, default='Super', help='First name')
        parser.add_argument('--last-name', type=str, default='Admin', help='Last name')

    def handle(self, *args, **options):
        email = options['email']
        password = options['password']
        first_name = options['first_name']
        last_name = options['last_name']

        # Check if user already exists
        if User.objects.filter(email=email).exists():
            self.stdout.write(self.style.WARNING(f'User with email {email} already exists.'))
            user = User.objects.get(email=email)
            if not user.is_superuser:
                user.is_superuser = True
                user.is_staff = True
                user.is_verified = True
                user.save()
                self.stdout.write(self.style.SUCCESS(f'Updated {email} to superadmin.'))
            else:
                self.stdout.write(self.style.SUCCESS(f'{email} is already a superadmin.'))
            return

        # Create superuser
        user = User.objects.create_superuser(
            email=email,
            password=password,
            first_name=first_name,
            last_name=last_name,
            employee_id='ADMIN001',
        )

        self.stdout.write(self.style.SUCCESS(f'Successfully created superadmin: {email}'))
        self.stdout.write(self.style.SUCCESS(f'Password: {password}'))
        self.stdout.write(self.style.WARNING('Please change the password after first login!'))
