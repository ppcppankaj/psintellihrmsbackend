"""Expense URL Configuration"""

from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    ExpenseCategoryViewSet, ExpenseClaimViewSet,
    ExpenseItemViewSet, EmployeeAdvanceViewSet
)

router = DefaultRouter()
router.register(r'categories', ExpenseCategoryViewSet, basename='expense-category')
router.register(r'claims', ExpenseClaimViewSet, basename='expense-claim')
router.register(r'items', ExpenseItemViewSet, basename='expense-item')
router.register(r'advances', EmployeeAdvanceViewSet, basename='employee-advance')

urlpatterns = [
    path('', include(router.urls)),
]
