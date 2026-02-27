"""
Comprehensive test suite for branch isolation and multi-tenancy
Tests cross-organization access prevention and security boundaries
"""

from django.test import TestCase, Client
from django.urls import reverse
from rest_framework.test import APITestCase, APIClient
from rest_framework import status
import uuid

from apps.authentication.models import User
from apps.core.models import Organization
from apps.authentication.models_hierarchy import Branch, BranchUser, OrganizationUser
from apps.employees.models import Employee, Department, Designation


class BranchIsolationTests(APITestCase):
    """Test branch-level data isolation"""
    
    def setUp(self):
        """Set up test organizations, branches, and users"""
        # Create two organizations
        self.org1 = Organization.objects.create(
            name="Organization 1",
            code="ORG1",
            is_active=True
        )
        self.org2 = Organization.objects.create(
            name="Organization 2",
            code="ORG2",
            is_active=True
        )
        
        # Create branches
        self.branch1a = Branch.objects.create(
            organization=self.org1,
            name="Branch 1A",
            code="BR1A",
            is_active=True
        )
        self.branch1b = Branch.objects.create(
            organization=self.org1,
            name="Branch 1B",
            code="BR1B",
            is_active=True
        )
        self.branch2a = Branch.objects.create(
            organization=self.org2,
            name="Branch 2A",
            code="BR2A",
            is_active=True
        )
        
        # Create departments
        self.dept1 = Department.objects.create(
            organization=self.org1,
            name="Department 1",
            code="DEPT1"
        )
        self.dept2 = Department.objects.create(
            organization=self.org2,
            name="Department 2",
            code="DEPT2"
        )
        
        # Create designations
        self.desig1 = Designation.objects.create(
            organization=self.org1,
            name="Manager",
            code="MGR"
        )
        self.desig2 = Designation.objects.create(
            organization=self.org2,
            name="Engineer",
            code="ENG"
        )
        
        # Create users
        self.user1 = User.objects.create_user(
            username="user1@org1.com",
            email="user1@org1.com",
            password="testpass123",
            first_name="User",
            last_name="One"
        )
        
        self.user2 = User.objects.create_user(
            username="user2@org2.com",
            email="user2@org2.com",
            password="testpass123",
            first_name="User",
            last_name="Two"
        )
        
        # Assign users to organizations
        OrganizationUser.objects.create(
            user=self.user1,
            organization=self.org1,
            is_active=True
        )
        OrganizationUser.objects.create(
            user=self.user2,
            organization=self.org2,
            is_active=True
        )
        
        # Assign users to branches
        BranchUser.objects.create(
            user=self.user1,
            branch=self.branch1a,
            is_primary=True,
            is_active=True
        )
        BranchUser.objects.create(
            user=self.user2,
            branch=self.branch2a,
            is_primary=True,
            is_active=True
        )
        
        # Create employees in different branches
        self.emp1 = Employee.objects.create(
            branch=self.branch1a,
            organization=self.org1,
            department=self.dept1,
            designation=self.desig1,
            employee_id="EMP001",
            first_name="John",
            last_name="Doe",
            email="john@org1.com",
            personal_email="john.personal@example.com",
            phone="+919876543210",
            date_of_birth="1990-01-01",
            gender="male",
            blood_group="O+",
            marital_status="single",
            employment_type="permanent",
            employment_status="active",
            date_of_joining="2025-01-01"
        )
        
        self.emp2 = Employee.objects.create(
            branch=self.branch2a,
            organization=self.org2,
            department=self.dept2,
            designation=self.desig2,
            employee_id="EMP002",
            first_name="Jane",
            last_name="Smith",
            email="jane@org2.com",
            personal_email="jane.personal@example.com",
            phone="+919876543211",
            date_of_birth="1991-01-01",
            gender="female",
            blood_group="A+",
            marital_status="single",
            employment_type="permanent",
            employment_status="active",
            date_of_joining="2025-01-01"
        )
        
        self.client = APIClient()
    
    def test_cross_org_access_denied(self):
        """User from Org 1 cannot access Org 2 employee data"""
        self.client.force_authenticate(user=self.user1)
        
        response = self.client.get(f'/api/v1/employees/{self.emp2.id}/')
        
        # Should return 404 (not 403) to prevent enumeration
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
    
    def test_same_org_access_allowed(self):
        """User can access data from their own organization"""
        self.client.force_authenticate(user=self.user1)
        
        response = self.client.get(f'/api/v1/employees/{self.emp1.id}/')
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['employee_id'], 'EMP001')
    
    def test_list_employees_filtered_by_branch(self):
        """Employee list API only returns accessible branch data"""
        self.client.force_authenticate(user=self.user1)
        
        response = self.client.get('/api/v1/employees/')
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        # Should only see emp1, not emp2
        employee_ids = [e['id'] for e in response.data['results']]
        self.assertIn(str(self.emp1.id), employee_ids)
        self.assertNotIn(str(self.emp2.id), employee_ids)
    
    def test_branch_switching_within_org(self):
        """User can switch between assigned branches in same org"""
        # Assign user1 to branch1b as well
        BranchUser.objects.create(
            user=self.user1,
            branch=self.branch1b,
            is_active=True
        )
        
        self.client.force_authenticate(user=self.user1)
        
        # Switch to branch1b
        response = self.client.post('/api/v1/auth/branches/switch-branch/', {
            'branch_id': str(self.branch1b.id)
        })
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['current_branch']['id'], str(self.branch1b.id))
    
    def test_branch_switching_cross_org_denied(self):
        """User cannot switch to branch in different organization"""
        self.client.force_authenticate(user=self.user1)
        
        # Try to switch to branch2a (different org)
        response = self.client.post('/api/v1/auth/branches/switch-branch/', {
            'branch_id': str(self.branch2a.id)
        })
        
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
    
    def test_create_employee_in_accessible_branch(self):
        """User can create employee in accessible branch"""
        self.client.force_authenticate(user=self.user1)
        
        data = {
            'employee_id': 'EMP003',
            'first_name': 'Test',
            'last_name': 'Employee',
            'email': 'test@org1.com',
            'personal_email': 'test.personal@example.com',
            'phone': '+919876543212',
            'date_of_birth': '1992-01-01',
            'gender': 'male',
            'branch': str(self.branch1a.id),
            'department': str(self.dept1.id),
            'designation': str(self.desig1.id),
            'employment_type': 'permanent',
            'employment_status': 'active',
            'date_of_joining': '2026-01-01'
        }
        
        response = self.client.post('/api/v1/employees/', data, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
    
    def test_create_employee_in_other_org_branch_denied(self):
        """User cannot create employee in another org's branch"""
        self.client.force_authenticate(user=self.user1)
        
        data = {
            'employee_id': 'EMP004',
            'first_name': 'Test',
            'last_name': 'Employee',
            'email': 'test@org2.com',
            'personal_email': 'test.personal@example.com',
            'phone': '+919876543213',
            'date_of_birth': '1992-01-01',
            'gender': 'male',
            'branch': str(self.branch2a.id),  # Different org branch
            'department': str(self.dept2.id),
            'designation': str(self.desig2.id),
            'employment_type': 'permanent',
            'employment_status': 'active',
            'date_of_joining': '2026-01-01'
        }
        
        response = self.client.post('/api/v1/employees/', data, format='json')
        
        # Should fail validation
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
    
    def test_superuser_sees_all_data(self):
        """Superuser can access data from all organizations"""
        superuser = User.objects.create_superuser(
            username="admin@example.com",
            email="admin@example.com",
            password="admin123"
        )
        
        self.client.force_authenticate(user=superuser)
        
        response = self.client.get('/api/v1/employees/')
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        # Should see both emp1 and emp2
        employee_ids = [e['id'] for e in response.data['results']]
        self.assertIn(str(self.emp1.id), employee_ids)
        self.assertIn(str(self.emp2.id), employee_ids)
    
    def test_org_admin_sees_all_branches_in_org(self):
        """Organization admin can see all branches in their org"""
        # Make user1 an org admin
        org_user = OrganizationUser.objects.get(user=self.user1)
        org_user.is_org_admin = True
        org_user.save()
        
        # Create employee in branch1b
        emp3 = Employee.objects.create(
            branch=self.branch1b,
            organization=self.org1,
            department=self.dept1,
            designation=self.desig1,
            employee_id="EMP005",
            first_name="Test",
            last_name="Branch1B",
            email="test@branch1b.com",
            personal_email="test.personal@example.com",
            phone="+919876543214",
            date_of_birth="1993-01-01",
            gender="male",
            employment_type="permanent",
            employment_status="active",
            date_of_joining="2025-01-01"
        )
        
        self.client.force_authenticate(user=self.user1)
        
        response = self.client.get('/api/v1/employees/')
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        # Should see employees from both branch1a and branch1b
        employee_ids = [e['id'] for e in response.data['results']]
        self.assertIn(str(self.emp1.id), employee_ids)
        self.assertIn(str(emp3.id), employee_ids)
        # But not from org2
        self.assertNotIn(str(self.emp2.id), employee_ids)


class QuerySetIsolationTests(TestCase):
    """Test custom manager and queryset filtering"""
    
    def setUp(self):
        """Set up test data"""
        self.org1 = Organization.objects.create(name="Org 1", code="O1")
        self.org2 = Organization.objects.create(name="Org 2", code="O2")
        
        self.branch1 = Branch.objects.create(
            organization=self.org1, name="Branch 1", code="B1"
        )
        self.branch2 = Branch.objects.create(
            organization=self.org2, name="Branch 2", code="B2"
        )
        
        self.dept1 = Department.objects.create(
            organization=self.org1, name="Dept 1", code="D1"
        )
        self.dept2 = Department.objects.create(
            organization=self.org2, name="Dept 2", code="D2"
        )
        
        self.desig1 = Designation.objects.create(
            organization=self.org1, name="Desig 1", code="DG1"
        )
        
        self.emp1 = Employee.objects.create(
            branch=self.branch1,
            organization=self.org1,
            department=self.dept1,
            designation=self.desig1,
            employee_id="E1",
            first_name="Emp",
            last_name="One",
            email="emp1@test.com",
            personal_email="emp1.personal@example.com",
            phone="+919876543210",
            date_of_birth="1990-01-01",
            gender="male",
            employment_type="permanent",
            employment_status="active",
            date_of_joining="2025-01-01"
        )
    
    def test_for_organization_filter(self):
        """Test organization-scoped filtering"""
        employees = Employee.objects.for_organization(self.org1)
        self.assertEqual(employees.count(), 1)
        self.assertEqual(employees.first().id, self.emp1.id)
        
        employees = Employee.objects.for_organization(self.org2)
        self.assertEqual(employees.count(), 0)
    
    def test_for_branch_filter(self):
        """Test branch-scoped filtering"""
        employees = Employee.objects.for_branch(self.branch1)
        self.assertEqual(employees.count(), 1)
        
        employees = Employee.objects.for_branch(self.branch2)
        self.assertEqual(employees.count(), 0)


class SessionInvalidationTests(APITestCase):
    """Test session invalidation on role/branch changes"""
    
    def setUp(self):
        """Set up test data"""
        self.org = Organization.objects.create(name="Test Org", code="TO")
        self.branch = Branch.objects.create(
            organization=self.org, name="Test Branch", code="TB"
        )
        
        self.user = User.objects.create_user(
            username="test@example.com",
            email="test@example.com",
            password="testpass123"
        )
        
        OrganizationUser.objects.create(
            user=self.user,
            organization=self.org,
            is_active=True
        )
        
        BranchUser.objects.create(
            user=self.user,
            branch=self.branch,
            is_primary=True,
            is_active=True
        )
        
        self.client = APIClient()
    
    def test_branch_removal_clears_session(self):
        """Test that removing branch access clears session"""
        self.client.force_authenticate(user=self.user)
        
        # Switch to branch
        response = self.client.post('/api/v1/auth/branches/switch-branch/', {
            'branch_id': str(self.branch.id)
        })
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        # Remove branch access
        BranchUser.objects.filter(user=self.user, branch=self.branch).delete()
        
        # Next request should clear branch from session
        response = self.client.get('/api/v1/auth/branches/current-branch/')
        # Should indicate no branch access
        self.assertIn(response.status_code, [status.HTTP_404_NOT_FOUND, status.HTTP_403_FORBIDDEN])


# Run tests
if __name__ == '__main__':
    import django
    django.setup()
    from django.test.utils import get_runner
    from django.conf import settings
    
    TestRunner = get_runner(settings)
    test_runner = TestRunner()
    failures = test_runner.run_tests(["apps.core.tests.test_branch_isolation"])
