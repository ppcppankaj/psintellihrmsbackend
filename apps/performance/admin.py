from django.contrib import admin
from apps.core.admin_mixins import OrganizationAwareAdminMixin
from .models import PerformanceCycle, OKRObjective, KeyResult, PerformanceReview, ReviewFeedback


@admin.register(PerformanceCycle)
class PerformanceCycleAdmin(OrganizationAwareAdminMixin, admin.ModelAdmin):
    list_display = ['name', 'year', 'start_date', 'end_date', 'status', 'is_active']
    list_filter = ['status', 'year', 'is_active']
    search_fields = ['name']


@admin.register(OKRObjective)
class OKRObjectiveAdmin(OrganizationAwareAdminMixin, admin.ModelAdmin):
    list_display = ['title', 'employee', 'cycle', 'weight', 'progress', 'status']
    list_filter = ['status', 'cycle']
    search_fields = ['title', 'employee__employee_id']
    raw_id_fields = ['employee', 'cycle']


@admin.register(KeyResult)
class KeyResultAdmin(OrganizationAwareAdminMixin, admin.ModelAdmin):
    list_display = ['title', 'objective', 'target_value', 'current_value', 'progress']
    search_fields = ['title', 'objective__title']
    raw_id_fields = ['objective']


@admin.register(PerformanceReview)
class PerformanceReviewAdmin(OrganizationAwareAdminMixin, admin.ModelAdmin):
    list_display = ['employee', 'cycle', 'self_rating', 'manager_rating', 'final_rating', 'status']
    list_filter = ['status', 'cycle']
    search_fields = ['employee__employee_id']
    raw_id_fields = ['employee', 'cycle']


@admin.register(ReviewFeedback)
class ReviewFeedbackAdmin(OrganizationAwareAdminMixin, admin.ModelAdmin):
    list_display = ['review', 'reviewer', 'relationship', 'rating', 'is_anonymous']
    list_filter = ['relationship', 'is_anonymous']
    raw_id_fields = ['review', 'reviewer']
