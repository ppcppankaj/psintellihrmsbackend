from django.test import TestCase
from apps.employees.models import Employee, Department, Designation
from apps.performance.models import PerformanceCycle, Competency, EmployeeCompetency, TrainingRecommendation
from apps.core.models import Organization

class PerformanceEnhancementTests(TestCase):
    def setUp(self):
        super().setUp()
        self.organization = Organization.objects.create(name="Test Org")
        self.dept = Department.objects.create(name="Engineering", organization=self.organization)
        self.desig = Designation.objects.create(name="Software Engineer", department=self.dept, organization=self.organization)
        self.employee = Employee.objects.create(
            employee_id="EMP001",
            first_name="Test",
            last_name="User",
            department=self.dept,
            designation=self.desig,
            organization=self.organization
        )
        self.cycle = PerformanceCycle.objects.create(
            name="Annual 2024",
            year=2024,
            start_date="2024-01-01",
            end_date="2024-12-31",
            organization=self.organization
        )
        self.competency = Competency.objects.create(
            name="Python Programming",
            code="PY01",
            category="technical",
            organization=self.organization
        )

    def test_training_recommendation_on_gap(self):
        """Test that a training recommendation is created when a gap exists."""
        assessment = EmployeeCompetency.objects.create(
            employee=self.employee,
            competency=self.competency,
            cycle=self.cycle,
            expected_level=4,
            final_level=2,
            organization=self.organization
        )
        assessment.calculate_gap()
        
        # Check if recommendation was created by signal
        recommendation = TrainingRecommendation.objects.filter(
            employee=self.employee,
            competency=self.competency,
            cycle=self.cycle
        ).first()
        
        self.assertIsNotNone(recommendation)
        self.assertEqual(recommendation.priority, 'high') # Gap is 2
        self.assertIn("Advanced Training", recommendation.suggested_training)

    def test_no_recommendation_on_no_gap(self):
        """Test that no training recommendation is created when there is no gap."""
        assessment = EmployeeCompetency.objects.create(
            employee=self.employee,
            competency=self.competency,
            cycle=self.cycle,
            expected_level=3,
            final_level=3,
            organization=self.organization
        )
        assessment.calculate_gap()
        
        recommendation = TrainingRecommendation.objects.filter(
            employee=self.employee,
            competency=self.competency,
            cycle=self.cycle
        ).exists()
        
        self.assertFalse(recommendation)
