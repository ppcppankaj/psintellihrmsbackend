"""
Tests for Branch Permissions and Filtering
"""

import pytest
from django.test import TestCase, RequestFactory
from rest_framework.test import APITestCase, APIClient
from rest_framework import status

from apps.authentication.models import User
from apps.core.models import Organization
from apps.authentication.models_hierarchy import Branch, BranchUser, OrganizationUser
from apps.employees.models import Employee, Department
from apps.core.permissions_branch import (
    BranchPermission, BranchFilterBackend,
    OrganizationPermission, OrganizationFilterBackend,
    IsBranchAdmin, IsSelfOrBranchAdmin
)


class BranchPermissionTestCase(APITestCase):
    """Test BranchPermission class"""
    
    def setUp(self):
        """Set up test data"""
        # Create organizations
        self.org1 = Organization.objects.create(
            name="Org 1",
            code="ORG1",
            is_active=True
        )
        self.org2 = Organization.objects.create(
            name="Org 2",
            code="ORG2",
            is_active=True
        )
        
        # Create branches
        self.branch1 = Branch.objects.create(
            organization=self.org1,
            name="Branch 1",
            code="BR1",
            is_active=True
        )
        self.branch2 = Branch.objects.create(
            organization=self.org1,
            name="Branch 2",
            code="BR2",
            is_active=True
        )
        self.branch3 = Branch.objects.create(
            organization=self.org2,
            name="Branch 3",
            code="BR3",
            is_active=True
        )
        
        # Create users
        self.superuser = User.objects.create_superuser(
            username="superuser",
            email="super@test.com",
            password="test123"
        )
        
        self.org_admin = User.objects.create_user(
            username="org_admin",
            email="orgadmin@test.com",
            password="test123",
            is_org_admin=True
        )
        
        self.branch_user = User.objects.create_user(
            username="branch_user",
            email="branchuser@test.com",
            password="test123"
        )
        
        self.other_branch_user = User.objects.create_user(
            username="other_user",
            email="other@test.com",
            password="test123"
        )
        
        # Set up organization memberships
        OrganizationUser.objects.create(
            organization=self.org1,
            user=self.org_admin,
            is_active=True
        )
        OrganizationUser.objects.create(
            organization=self.org1,
            user=self.branch_user,
            is_active=True
        )
        OrganizationUser.objects.create(
            organization=self.org1,
            user=self.other_branch_user,
            is_active=True
        )
        
        # Set up branch memberships
        BranchUser.objects.create(
            branch=self.branch1,
            user=self.branch_user,
            is_active=True
        )
        BranchUser.objects.create(
            branch=self.branch2,
            user=self.other_branch_user,
            is_active=True
        )
        
        # Create employees
        self.dept1 = Department.objects.create(
            organization=self.org1,
            branch=self.branch1,
            name="Department 1",
            code="DEPT1",
            is_active=True
        )
        
        self.emp1 = Employee.objects.create(
            organization=self.org1,
            branch=self.branch1,
            user=self.branch_user,
            employee_id="EMP001",
            first_name="Branch",
            last_name="User",
            email="branchuser@test.com",
            department=self.dept1,
            is_active=True
        )
        
        self.emp2 = Employee.objects.create(
            organization=self.org1,
            branch=self.branch2,
            user=self.other_branch_user,
            employee_id="EMP002",
            first_name="Other",
            last_name="User",
            email="other@test.com",
            department=self.dept1,
            is_active=True
        )
        
        self.factory = RequestFactory()
        self.permission = BranchPermission()
    
    def test_superuser_has_permission(self):
        """Superuser should have access to all branches"""
        request = self.factory.get('/')
        request.user = self.superuser
        
        # Should have permission for any object
        self.assertTrue(self.permission.has_permission(request, None))
        self.assertTrue(self.permission.has_object_permission(request, None, self.emp1))
        self.assertTrue(self.permission.has_object_permission(request, None, self.emp2))
    
    def test_org_admin_has_permission(self):
        """Org admin should have access to all branches in their organization"""
        request = self.factory.get('/')
        request.user = self.org_admin
        
        # Should have permission for objects in their organization
        self.assertTrue(self.permission.has_permission(request, None))
        self.assertTrue(self.permission.has_object_permission(request, None, self.emp1))
        self.assertTrue(self.permission.has_object_permission(request, None, self.emp2))
    
    def test_branch_user_has_permission_own_branch(self):
        """Branch user should have access to their own branch"""
        request = self.factory.get('/')
        request.user = self.branch_user
        
        # Should have permission for objects in their branch
        self.assertTrue(self.permission.has_permission(request, None))
        self.assertTrue(self.permission.has_object_permission(request, None, self.emp1))
    
    def test_branch_user_no_permission_other_branch(self):
        """Branch user should NOT have access to other branches"""
        request = self.factory.get('/')
        request.user = self.branch_user
        
        # Should NOT have permission for objects in other branches
        self.assertFalse(self.permission.has_object_permission(request, None, self.emp2))
    
    def test_no_branch_assignment_denied(self):
        """User with no branch assignment should be denied"""
        no_branch_user = User.objects.create_user(
            username="no_branch",
            email="nobranch@test.com",
            password="test123"
        )
        
        request = self.factory.get('/')
        request.user = no_branch_user
        
        # Should be denied
        self.assertFalse(self.permission.has_permission(request, None))


class BranchFilterBackendTestCase(TestCase):
    """Test BranchFilterBackend queryset filtering"""
    
    def setUp(self):
        """Set up test data"""
        # Create organization and branches
        self.org = Organization.objects.create(
            name="Test Org",
            code="TESTORG",
            is_active=True
        )
        
        self.branch1 = Branch.objects.create(
            organization=self.org,
            name="Branch 1",
            code="BR1",
            is_active=True
        )
        self.branch2 = Branch.objects.create(
            organization=self.org,
            name="Branch 2",
            code="BR2",
            is_active=True
        )
        
        # Create users
        self.user1 = User.objects.create_user(
            username="user1",
            email="user1@test.com",
            password="test123"
        )
        self.user2 = User.objects.create_user(
            username="user2",
            email="user2@test.com",
            password="test123"
        )
        
        # Set up organization and branch memberships
        OrganizationUser.objects.create(
            organization=self.org,
            user=self.user1,
            is_active=True
        )
        OrganizationUser.objects.create(
            organization=self.org,
            user=self.user2,
            is_active=True
        )
        
        BranchUser.objects.create(
            branch=self.branch1,
            user=self.user1,
            is_active=True
        )
        BranchUser.objects.create(
            branch=self.branch2,
            user=self.user2,
            is_active=True
        )
        
        # Create departments
        self.dept1 = Department.objects.create(
            organization=self.org,
            branch=self.branch1,
            name="Department 1",
            code="DEPT1",
            is_active=True
        )
        self.dept2 = Department.objects.create(
            organization=self.org,
            branch=self.branch2,
            name="Department 2",
            code="DEPT2",
            is_active=True
        )
        
        self.factory = RequestFactory()
        self.filter_backend = BranchFilterBackend()
    
    def test_superuser_sees_all(self):
        """Superuser should see all departments"""
        superuser = User.objects.create_superuser(
            username="superuser",
            email="super@test.com",
            password="test123"
        )
        
        request = self.factory.get('/')
        request.user = superuser
        
        queryset = Department.objects.all()
        filtered = self.filter_backend.filter_queryset(request, queryset, None)
        
        self.assertEqual(filtered.count(), 2)
    
    def test_branch_user_sees_own_branch(self):
        """Branch user should see only their branch"""
        request = self.factory.get('/')
        request.user = self.user1
        
        queryset = Department.objects.all()
        filtered = self.filter_backend.filter_queryset(request, queryset, None)
        
        self.assertEqual(filtered.count(), 1)
        self.assertEqual(filtered.first(), self.dept1)


class BranchAPIIntegrationTestCase(APITestCase):
    """Integration tests for Branch-aware API endpoints"""
    
    def setUp(self):
        """Set up test data"""
        # Create organization and branches
        self.org = Organization.objects.create(
            name="Test Org",
            code="TESTORG",
            is_active=True
        )
        
        self.branch1 = Branch.objects.create(
            organization=self.org,
            name="Branch 1",
            code="BR1",
            is_active=True
        )
        self.branch2 = Branch.objects.create(
            organization=self.org,
            name="Branch 2",
            code="BR2",
            is_active=True
        )
        
        # Create users
        self.user1 = User.objects.create_user(
            username="user1",
            email="user1@test.com",
            password="test123"
        )
        self.user2 = User.objects.create_user(
            username="user2",
            email="user2@test.com",
            password="test123"
        )
        
        # Set up memberships
        OrganizationUser.objects.create(
            organization=self.org,
            user=self.user1,
            is_active=True
        )
        OrganizationUser.objects.create(
            organization=self.org,
            user=self.user2,
            is_active=True
        )
        
        BranchUser.objects.create(
            branch=self.branch1,
            user=self.user1,
            is_active=True
        )
        BranchUser.objects.create(
            branch=self.branch2,
            user=self.user2,
            is_active=True
        )
        
        # Create departments
        self.dept1 = Department.objects.create(
            organization=self.org,
            branch=self.branch1,
            name="Department 1",
            code="DEPT1",
            is_active=True
        )
        self.dept2 = Department.objects.create(
            organization=self.org,
            branch=self.branch2,
            name="Department 2",
            code="DEPT2",
            is_active=True
        )
        
        # Create employees
        self.emp1 = Employee.objects.create(
            organization=self.org,
            branch=self.branch1,
            user=self.user1,
            employee_id="EMP001",
            first_name="User",
            last_name="One",
            email="user1@test.com",
            department=self.dept1,
            is_active=True
        )
        self.emp2 = Employee.objects.create(
            organization=self.org,
            branch=self.branch2,
            user=self.user2,
            employee_id="EMP002",
            first_name="User",
            last_name="Two",
            email="user2@test.com",
            department=self.dept2,
            is_active=True
        )
        
        self.client = APIClient()
    
    def test_employee_list_filtered_by_branch(self):
        """Employee list should be filtered by user's branch"""
        self.client.force_authenticate(user=self.user1)
        
        response = self.client.get('/api/v1/employees/')
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        # User1 should only see employees in branch1
        self.assertEqual(len(response.data.get('results', [])), 1)
    
    def test_cannot_access_other_branch_employee(self):
        """User should not be able to access employees from other branches"""
        self.client.force_authenticate(user=self.user1)
        
        # Try to access emp2 which is in branch2
        response = self.client.get(f'/api/v1/employees/{self.emp2.id}/')
        
        # Should be denied (403 or 404)
        self.assertIn(response.status_code, [status.HTTP_403_FORBIDDEN, status.HTTP_404_NOT_FOUND])
    
    def test_superuser_sees_all_branches(self):
        """Superuser should see employees from all branches"""
        superuser = User.objects.create_superuser(
            username="superuser",
            email="super@test.com",
            password="test123"
        )
        
        self.client.force_authenticate(user=superuser)
        
        response = self.client.get('/api/v1/employees/')
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        # Superuser should see all employees
        self.assertEqual(len(response.data.get('results', [])), 2)


@pytest.mark.django_db
class TestBranchSelectorAPI:
    """Tests for Branch Selector API"""
    
    def test_my_branches_endpoint(self, api_client, branch_user_with_access):
        """Test getting user's accessible branches"""
        user, branches = branch_user_with_access
        api_client.force_authenticate(user=user)
        
        response = api_client.get('/api/v1/auth/branches/my-branches/')
        
        assert response.status_code == 200
        assert 'branches' in response.data
        assert 'current_branch' in response.data
        assert len(response.data['branches']) > 0
    
    def test_switch_branch_success(self, api_client, branch_user_with_access):
        """Test successfully switching branches"""
        user, branches = branch_user_with_access
        api_client.force_authenticate(user=user)
        
        target_branch = branches[0]
        
        response = api_client.post('/api/v1/auth/branches/switch-branch/', {
            'branch_id': str(target_branch.id)
        })
        
        assert response.status_code == 200
        assert response.data['success'] is True
        assert response.data['branch']['id'] == str(target_branch.id)
    
    def test_switch_branch_unauthorized(self, api_client, branch_user_with_access):
        """Test switching to unauthorized branch fails"""
        user, branches = branch_user_with_access
        api_client.force_authenticate(user=user)
        
        # Create a branch user doesn't have access to
        other_org = Organization.objects.create(name="Other Org", code="OTHER")
        other_branch = Branch.objects.create(
            organization=other_org,
            name="Unauthorized Branch",
            code="UNAUTH"
        )
        
        response = api_client.post('/api/v1/auth/branches/switch-branch/', {
            'branch_id': str(other_branch.id)
        })
        
        assert response.status_code == 403
        assert 'error' in response.data


# Pytest fixtures
@pytest.fixture
def branch_user_with_access(db):
    """Create a user with access to multiple branches"""
    from apps.core.models import Organization
    from apps.authentication.models_hierarchy import Branch, BranchUser, OrganizationUser
    from apps.authentication.models import User
    
    org = Organization.objects.create(name="Test Org", code="TEST", is_active=True)
    
    branch1 = Branch.objects.create(
        organization=org,
        name="Branch 1",
        code="BR1",
        is_active=True
    )
    branch2 = Branch.objects.create(
        organization=org,
        name="Branch 2",
        code="BR2",
        is_active=True
    )
    
    user = User.objects.create_user(
        username="testuser",
        email="test@test.com",
        password="test123"
    )
    
    OrganizationUser.objects.create(organization=org, user=user, is_active=True)
    BranchUser.objects.create(branch=branch1, user=user, is_active=True)
    BranchUser.objects.create(branch=branch2, user=user, is_active=True)
    
    return user, [branch1, branch2]
