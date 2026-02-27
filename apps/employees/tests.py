from django.utils import timezone
from rest_framework import status
from rest_framework_simplejwt.tokens import RefreshToken
from django.test import TestCase
from apps.core.models import Organization
from apps.core.context import set_current_organization
from django.contrib.auth import get_user_model

from apps.employees.models import (
    Employee, Department, Designation, Location,
    ResignationRequest, ExitInterview, EmployeeTransfer, EmployeePromotion
)

User = get_user_model()

class TransitionAPITests(TestCase):
    """
    Tests for Employee Transitions
    """
    
    def setUp(self):
        super().setUp()
        self.organization = Organization.objects.create(name='Test Org', slug='test')
        set_current_organization(self.organization)
        
        # Setup data in tenant context
        # Create a user and employee
        self.user = User.objects.create_user(email='emp@test.com', password='password123', is_active=True)
        
        # Create core entities
        self.dept = Department.objects.create(name='Engineering')
        self.desig = Designation.objects.create(name='Senior Engineer')
        self.loc = Location.objects.create(name='New York')
        
        self.employee = Employee.objects.create(
            user=self.user,
            employee_id='EMP001',
            first_name='John',
            last_name='Doe',
            department=self.dept,
            designation=self.desig,
            location=self.loc,
            joining_date=timezone.now().date()
        )
        
        # Create HR user for approvals
        self.hr_user = User.objects.create_user(email='hr@test.com', password='password123', is_active=True)
        self.hr_employee = Employee.objects.create(
            user=self.hr_user,
            employee_id='HR001',
            first_name='Jane',
            last_name='Smith'
        )
        
        # Tokens
        self.emp_token = str(RefreshToken.for_user(self.user).access_token)
        self.hr_token = str(RefreshToken.for_user(self.hr_user).access_token)
        
        # Common headers
        self.headers = {
            'HTTP_AUTHORIZATION': f'Bearer {self.emp_token}',
            'X-Organization-ID': str(self.organization.id)
        }
        self.hr_headers = {
            'HTTP_AUTHORIZATION': f'Bearer {self.hr_token}',
            'X-Organization-ID': str(self.organization.id)
        }

    def test_resignation_lifecycle(self):
        # 1. Create Resignation
        data = {
            "resignation_date": str(timezone.now().date()),
            "requested_last_working_date": str((timezone.now() + timezone.timedelta(days=30)).date()),
            "primary_reason": "better_opportunity",
            "detailed_reason": "I found a better job."
        }
        
        response = self.client.post('/api/v1/employees/resignations/', data=data, content_type='application/json', **self.headers)
        self.assertEqual(response.status_code, 201)
        resignation_id = response.json()['id']
        
        # 2. Submit Resignation
        response = self.client.post(f'/api/v1/employees/resignations/{resignation_id}/submit/', **self.headers)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['status'], 'submitted')
        
        # 3. Accept Resignation (as HR)
        accept_data = {
            "action": "accept",
            "approved_last_working_date": str((timezone.now() + timezone.timedelta(days=30)).date())
        }
        response = self.client.post(f'/api/v1/employees/resignations/{resignation_id}/accept/', data=accept_data, content_type='application/json', **self.hr_headers)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['status'], 'accepted')

    def test_exit_interview_submission(self):
        # Pre-requisite: Accepted Resignation
        resignation = ResignationRequest.objects.create(
            employee=self.employee,
            resignation_date=timezone.now().date(),
            requested_last_working_date=(timezone.now() + timezone.timedelta(days=30)).date(),
            primary_reason='better_opportunity',
            status='accepted',
            notice_period_days=30
        )
        
        # Submit Exit Interview
        interview_data = {
            "resignation": resignation.id,
            "interview_date": str(timezone.now().date()),
            "job_satisfaction": 4,
            "work_life_balance": 5,
            "management_support": 3,
            "growth_opportunities": 2,
            "compensation_satisfaction": 4,
            "work_environment": 5,
            "team_collaboration": 5,
            "reason_for_leaving": "Better pay elsewhere",
            "liked_most": "The team",
            "improvements_suggested": "More growth opportunities",
            "would_recommend": True,
            "would_return": True
        }
        
        response = self.client.post('/api/v1/employees/exit-interviews/', data=interview_data, content_type='application/json', **self.headers)
        self.assertEqual(response.status_code, 201, response.data)
        self.assertTrue(response.json()['is_completed'])
