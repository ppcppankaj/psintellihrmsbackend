"""
Seed Notification Templates - Auto-create standard notification templates
Run with: python manage.py seed_notification_templates
"""

from django.core.management.base import BaseCommand
from apps.notifications.models import NotificationTemplate
from apps.core.models import Organization
from apps.core.context import set_current_organization

TEMPLATES = [
    {
        'code': 'auth.welcome',
        'name': 'Welcome to IntelliHR',
        'subject': 'Welcome to IntelliHR - Your Account is Ready',
        'body': 'Dear {{ first_name }},\n\nWelcome to IntelliHR! Your account has been created successfully.\n\nUsername: {{ email }}\n\nPlease log in to complete your profile.\n\nBest regards,\nHR Team',
        'channel': 'email',
        'variables': ['first_name', 'email']
    },
    {
        'code': 'auth.reset_password',
        'name': 'Password Reset',
        'subject': 'Password Reset Request',
        'body': 'Hello {{ first_name }},\n\nWe received a request to reset your password. Click the link below to set a new password:\n\n{{ reset_link }}\n\nIf you did not request this, please ignore this email.\n\nRegards,\nIntelliHR Security',
        'channel': 'email',
        'variables': ['first_name', 'reset_link']
    },
    {
        'code': 'leave.applied',
        'name': 'Leave Applied',
        'subject': 'Leave Application Received',
        'body': 'Dear {{ manager_name }},\n\n{{ employee_name }} has applied for leave from {{ start_date }} to {{ end_date }}.\n\nReason: {{ reason }}\n\nPlease review and take action.\n\nRegards,\nHR System',
        'channel': 'email',
        'variables': ['manager_name', 'employee_name', 'start_date', 'end_date', 'reason']
    },
    {
        'code': 'leave.approved',
        'name': 'Leave Approved',
        'subject': 'Leave Request Approved',
        'body': 'Dear {{ employee_name }},\n\nYour leave request from {{ start_date }} to {{ end_date }} has been approved by {{ manager_name }}.\n\nRegards,\nHR Team',
        'channel': 'email',
        'variables': ['employee_name', 'start_date', 'end_date', 'manager_name']
    },
    {
        'code': 'leave.rejected',
        'name': 'Leave Rejected',
        'subject': 'Leave Request Rejected',
        'body': 'Dear {{ employee_name }},\n\nYour leave request from {{ start_date }} to {{ end_date }} has been rejected by {{ manager_name }}.\n\nReason: {{ rejection_reason }}\n\nRegards,\nHR Team',
        'channel': 'email',
        'variables': ['employee_name', 'start_date', 'end_date', 'manager_name', 'rejection_reason']
    },
    {
        'code': 'attendance.checkin',
        'name': 'Check-in Confirmed',
        'subject': 'Daily Check-in Confirmed',
        'body': 'Hi {{ first_name }},\n\nYou have successfully checked in at {{ time }} on {{ date }}.\n\nLocation: {{ location }}\n\nHave a great day!',
        'channel': 'email',
        'variables': ['first_name', 'time', 'date', 'location']
    },
    {
        'code': 'attendance.regularization',
        'name': 'Attendance Regularization',
        'subject': 'Regularization Request Received',
        'body': 'Dear {{ manager_name }},\n\n{{ employee_name }} has requested attendance regularization for {{ date }}.\n\nReason: {{ reason }}\n\nPlease review.\n\nRegards,\nHR System',
        'channel': 'email',
        'variables': ['manager_name', 'employee_name', 'date', 'reason']
    },
    {
        'code': 'payroll.payslip',
        'name': 'Payslip Generated',
        'subject': 'Payslip for {{ month_year }}',
        'body': 'Dear {{ employee_name }},\n\nYour payslip for {{ month_year }} has been generated and is available for download.\n\nNet Pay: {{ net_pay }}\n\nRegards,\nPayroll Team',
        'channel': 'email',
        'variables': ['employee_name', 'month_year', 'net_pay']
    },
    {
        'code': 'assets.assigned',
        'name': 'Asset Assigned',
        'subject': 'New Asset Assigned',
        'body': 'Dear {{ employee_name }},\n\nThe following asset has been assigned to you:\n\nAsset: {{ asset_name }}\nSerial No: {{ serial_number }}\nGiven On: {{ assigned_date }}\n\nPlease acknowledge receipt in the portal.\n\nRegards,\nIT Team',
        'channel': 'email',
        'variables': ['employee_name', 'asset_name', 'serial_number', 'assigned_date']
    },
    {
        'code': 'recruitment.interview',
        'name': 'Interview Scheduled',
        'subject': 'Interview Invitation - {{ role_name }}',
        'body': 'Dear {{ candidate_name }},\n\nWe are pleased to invite you for an interview for the {{ role_name }} position.\n\nDate: {{ date }}\nTime: {{ time }}\nMode: {{ mode }}\nLink/Address: {{ link_address }}\n\nPlease confirm your availability.\n\nRegards,\nRecruitment Team',
        'channel': 'email',
        'variables': ['candidate_name', 'role_name', 'date', 'time', 'mode', 'link_address']
    },
    {
        'code': 'recruitment.offer',
        'name': 'Offer Letter Released',
        'subject': 'Job Offer - {{ role_name }}',
        'body': 'Dear {{ candidate_name }},\n\nCongratulations! We are delighted to offer you the position of {{ role_name }} at IntelliHR.\n\nPlease find your offer letter attached.\n\nWe look forward to having you onboard.\n\nRegards,\nHR Team',
        'channel': 'email',
        'variables': ['candidate_name', 'role_name']
    }
]

class Command(BaseCommand):
    help = 'Seed standard notification templates for all active organizations'

    def handle(self, *args, **options):
        orgs = Organization.objects.filter(is_active=True)
        if not orgs.exists():
            self.stdout.write(self.style.WARNING('No active organizations found. Seed organizations first.'))
            return

        for org in orgs:
            self.stdout.write(f'Seeding templates for organization: {org.name}')
            set_current_organization(org)
            
            created_count = 0
            updated_count = 0
            
            for tmpl in TEMPLATES:
                obj, created = NotificationTemplate.objects.update_or_create(
                    code=tmpl['code'],
                    organization=org,
                    defaults={
                        'name': tmpl['name'],
                        'subject': tmpl['subject'],
                        'body': tmpl['body'],
                        'channel': tmpl['channel'],
                        'variables': tmpl['variables']
                    }
                )
                
                if created:
                    created_count += 1
                else:
                    updated_count += 1
                    
            self.stdout.write(self.style.SUCCESS(f'  Done! Created {created_count}, Updated {updated_count} templates.'))
        
        # Reset context
        set_current_organization(None)
