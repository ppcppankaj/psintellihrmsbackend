"""
Payroll URLs
"""

from django.urls import path, include
from rest_framework.routers import DefaultRouter

from .views import (
    EmployeeCompensationViewSet, PayrollRunViewSet, PayslipViewSet,
    TaxDeclarationViewSet, ReimbursementClaimViewSet,
    SalaryRevisionViewSet, LoanViewSet
)

router = DefaultRouter()
router.register(r'compensations', EmployeeCompensationViewSet, basename='employee-compensations')
router.register(r'runs', PayrollRunViewSet)
router.register(r'payslips', PayslipViewSet)
router.register(r'tax-declarations', TaxDeclarationViewSet)
router.register(r'reimbursements', ReimbursementClaimViewSet)
router.register(r'salary-revisions', SalaryRevisionViewSet, basename='salary-revisions')
router.register(r'loans', LoanViewSet)

urlpatterns = [
    path('', include(router.urls)),
]
