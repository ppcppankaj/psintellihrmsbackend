from django.test import TestCase
from apps.core.models import Organization
    def setUp(self):
        super().setUp()
        self.organization = Organization.objects.create(name="Test Org")
        
        # Setup salary components
        self.basic = SalaryComponent.objects.create(
            name="Basic", code="BASIC", component_type="earning", organization=self.organization
        )
        
        # Setup compensation
        self.comp = EmployeeCompensation.objects.create(
            employee=self.employee,
            effective_from="2024-01-01",
            annual_ctc=1200000,
            monthly_gross=100000,
            organization=self.organization
        )
        CompensationComponent.objects.create(
            compensation=self.comp,
            component=self.basic,
            monthly_amount=50000,
            annual_amount=600000,
            organization=self.organization
        )
        
        self.payroll_run = PayrollRun.objects.create(
            name="January 2024",
            month=1,
            year=2024,
            pay_date="2024-01-31",
            organization=self.organization
        )
        
        self.leave_type = LeaveType.objects.create(
            name="Privilege Leave", code="PL", encashment_allowed=True, organization=self.organization
        )

    def test_payroll_encashment_integration(self):
        """Test that approved leave encashment is added to the payslip."""
        # Create approved encashment
        encashment = LeaveEncashment.objects.create(
            employee=self.employee,
            leave_type=self.leave_type,
            year=2024,
            days_requested=5,
            days_approved=5,
            per_day_amount=2000,
            total_amount=10000,
            status=LeaveEncashment.STATUS_APPROVED,
            organization=self.organization
        )
        
        # Process payroll
        PayrollCalculationService.calculate_payslip(self.employee, self.payroll_run)
        
        # Refresh from DB
        payslip = Payslip.objects.get(employee=self.employee, payroll_run=self.payroll_run)
        encashment.refresh_from_db()
        
        # Verify
        self.assertEqual(float(payslip.leave_encashment), 10000.0)
        self.assertGreater(float(payslip.gross_salary), 50000.0) # Basic (50k) + Encashment (10k)
        
        # Verify encashment record is updated
        self.assertEqual(encashment.status, LeaveEncashment.STATUS_PROCESSED)
        self.assertEqual(encashment.paid_in_payroll, self.payroll_run)
