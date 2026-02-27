"""
Employee URLs
"""

from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    EmployeeViewSet, DepartmentViewSet, DesignationViewSet,
    LocationViewSet, SkillViewSet, 
    EmployeeTransferViewSet, EmployeePromotionViewSet, ResignationRequestViewSet,
    ExitInterviewViewSet, SeparationChecklistViewSet,
    EmployeeAddressViewSet, EmployeeBankAccountViewSet, 
    EmergencyContactViewSet, EmployeeDependentViewSet,
    EmployeeDocumentViewSet, EmploymentHistoryViewSet, CertificationViewSet
)

router = DefaultRouter()
router.register('departments', DepartmentViewSet, basename='department')
router.register('designations', DesignationViewSet, basename='designation')
router.register('locations', LocationViewSet, basename='location')
router.register('skills', SkillViewSet, basename='skill')
router.register('certifications', CertificationViewSet, basename='certification')
router.register('documents', EmployeeDocumentViewSet, basename='document')
router.register('employment-history', EmploymentHistoryViewSet, basename='employment-history')
router.register('transfers', EmployeeTransferViewSet, basename='transfer')
router.register('promotions', EmployeePromotionViewSet, basename='promotion')
router.register('resignations', ResignationRequestViewSet, basename='resignation')
router.register('exit-interviews', ExitInterviewViewSet, basename='exit-interview')
router.register('separation-checklists', SeparationChecklistViewSet, basename='separation-checklist')

router.register('addresses', EmployeeAddressViewSet, basename='address')
router.register('bank-accounts', EmployeeBankAccountViewSet, basename='bank-account')
router.register('emergency-contacts', EmergencyContactViewSet, basename='emergency-contact')
router.register('dependents', EmployeeDependentViewSet, basename='dependent')

router.register('', EmployeeViewSet, basename='employee')

urlpatterns = [
    path('', include(router.urls)),
]
