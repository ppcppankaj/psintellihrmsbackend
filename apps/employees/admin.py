"""
Employee Admin
"""

from django.contrib import admin
from apps.core.admin_mixins import OrganizationAwareAdminMixin, BranchAwareAdminMixin
from .models import (
    Employee, Department, Designation, Location,
    EmployeeAddress, EmployeeBankAccount, EmergencyContact,
    EmployeeDependent, Skill, EmployeeSkill,
    EmploymentHistory, Document, Certification,
    EmployeeTransfer, EmployeePromotion, ResignationRequest,
    ExitInterview, SeparationChecklist
)


@admin.register(EmployeeTransfer)
class EmployeeTransferAdmin(BranchAwareAdminMixin, admin.ModelAdmin):
    list_display = ['employee', 'transfer_type', 'effective_date', 'status']
    list_filter = ['status', 'transfer_type', 'effective_date']
    search_fields = ['employee__employee_id']
    raw_id_fields = ['employee', 'department', 'designation', 'location', 'to_department', 'to_location', 'to_manager']


# =====================
# INLINES (SAFE VIA PARENT)
# =====================

class EmployeeAddressInline(admin.TabularInline):
    model = EmployeeAddress
    extra = 0


class EmployeeBankAccountInline(admin.TabularInline):
    model = EmployeeBankAccount
    extra = 0


class EmergencyContactInline(admin.TabularInline):
    model = EmergencyContact
    extra = 0


class EmployeeDependentInline(admin.TabularInline):
    model = EmployeeDependent
    extra = 0


# =====================
# MAIN ADMINS
# =====================

@admin.register(Employee)
class EmployeeAdmin(BranchAwareAdminMixin, admin.ModelAdmin):
    list_display = [
        'employee_id', 'get_full_name', 'get_email', 'department',
        'designation', 'branch', 'employment_status', 'date_of_joining', 'is_active'
    ]
    list_filter = [
        'employment_status', 'employment_type',
        'department', 'designation', 'location', 'branch', 'is_active'
    ]
    search_fields = ['employee_id', 'user__email', 'user__first_name', 'user__last_name']
    raw_id_fields = [
        'user', 'department', 'designation',
        'location', 'branch', 'reporting_manager', 'hr_manager'
    ]
    ordering = ['employee_id']

    inlines = [
        EmployeeAddressInline,
        EmployeeBankAccountInline,
        EmergencyContactInline,
        EmployeeDependentInline
    ]

    fieldsets = (
        ('Basic Info', {'fields': ('user', 'employee_id')}),
        ('Personal', {'fields': ('date_of_birth', 'gender', 'marital_status', 'blood_group', 'nationality')}),
        ('Organization', {'fields': ('department', 'designation', 'location', 'branch', 'reporting_manager', 'hr_manager')}),
        ('Employment', {'fields': ('employment_type', 'employment_status', 'date_of_joining', 'confirmation_date', 'probation_end_date', 'notice_period_days', 'work_mode')}),
        ('Exit', {'fields': ('date_of_exit', 'exit_reason', 'last_working_date')}),
        ('Identity', {'fields': ('pan_number', 'aadhaar_number', 'passport_number', 'passport_expiry')}),
        ('Statutory', {'fields': ('uan_number', 'pf_number', 'esi_number')}),
        ('Profile', {'fields': ('bio', 'linkedin_url')}),
        ('Status', {'fields': ('is_active',)}),
    )

    def get_full_name(self, obj):
        return obj.user.full_name
    get_full_name.short_description = 'Name'

    def get_email(self, obj):
        return obj.user.email
    get_email.short_description = 'Email'


@admin.register(Department)
class DepartmentAdmin(BranchAwareAdminMixin, admin.ModelAdmin):
    list_display = ['name', 'code', 'parent', 'head', 'branch', 'cost_center', 'is_active']
    list_filter = ['is_active', 'parent', 'branch']
    search_fields = ['name', 'code']
    raw_id_fields = ['parent', 'head', 'branch']
    ordering = ['name']


@admin.register(Designation)
class DesignationAdmin(OrganizationAwareAdminMixin, admin.ModelAdmin):
    list_display = ['name', 'code', 'level', 'grade', 'job_family', 'is_active']
    list_filter = ['level', 'grade', 'job_family', 'is_active']
    search_fields = ['name', 'code']
    ordering = ['level', 'name']


@admin.register(Location)
class LocationAdmin(OrganizationAwareAdminMixin, admin.ModelAdmin):
    list_display = ['name', 'code', 'city', 'state', 'country', 'is_headquarters', 'is_active']
    list_filter = ['country', 'state', 'is_headquarters', 'is_active']
    search_fields = ['name', 'code', 'city']
    ordering = ['name']


@admin.register(Skill)
class SkillAdmin(OrganizationAwareAdminMixin, admin.ModelAdmin):
    list_display = ['name', 'category', 'is_active']
    list_filter = ['category', 'is_active']
    search_fields = ['name', 'category']
    ordering = ['category', 'name']


@admin.register(EmployeeSkill)
class EmployeeSkillAdmin(OrganizationAwareAdminMixin, admin.ModelAdmin):
    list_display = ['employee', 'skill', 'proficiency', 'years_of_experience', 'is_verified']
    list_filter = ['proficiency', 'is_verified', 'is_primary']
    search_fields = ['employee__employee_id', 'skill__name']
    raw_id_fields = ['employee', 'skill', 'verified_by']


@admin.register(EmploymentHistory)
class EmploymentHistoryAdmin(OrganizationAwareAdminMixin, admin.ModelAdmin):
    list_display = ['employee', 'change_type', 'effective_date', 'created_at']
    list_filter = ['change_type', 'effective_date']
    search_fields = ['employee__employee_id']
    raw_id_fields = [
        'employee', 'previous_department', 'new_department',
        'previous_designation', 'new_designation'
    ]
    ordering = ['-effective_date']

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(Document)
class DocumentAdmin(OrganizationAwareAdminMixin, admin.ModelAdmin):
    list_display = ['employee', 'document_type', 'name', 'is_verified', 'is_confidential', 'created_at']
    list_filter = ['document_type', 'is_verified', 'is_confidential']
    search_fields = ['employee__employee_id', 'name']
    raw_id_fields = ['employee', 'verified_by']
    ordering = ['-created_at']


@admin.register(Certification)
class CertificationAdmin(OrganizationAwareAdminMixin, admin.ModelAdmin):
    list_display = ['employee', 'name', 'issuing_organization', 'issue_date', 'expiry_date', 'is_verified']
    list_filter = ['is_verified', 'issuing_organization']
    search_fields = ['employee__employee_id', 'name', 'issuing_organization']
    raw_id_fields = ['employee', 'verified_by']
    ordering = ['-issue_date']


@admin.register(EmployeePromotion)
class EmployeePromotionAdmin(BranchAwareAdminMixin, admin.ModelAdmin):
    list_display = ['employee', 'from_designation', 'to_designation', 'effective_date', 'status']
    list_filter = ['status', 'effective_date']
    search_fields = ['employee__employee_id']
    raw_id_fields = ['employee', 'from_designation', 'to_designation', 'recommended_by', 'approved_by']
    ordering = ['-effective_date']


@admin.register(ResignationRequest)
class ResignationRequestAdmin(BranchAwareAdminMixin, admin.ModelAdmin):
    list_display = ['employee', 'resignation_date', 'requested_last_working_date', 'status', 'primary_reason']
    list_filter = ['status', 'primary_reason', 'exit_checklist_complete', 'fnf_processed']
    search_fields = ['employee__employee_id', 'new_employer']
    raw_id_fields = ['employee', 'accepted_by']
    ordering = ['-resignation_date']


@admin.register(ExitInterview)
class ExitInterviewAdmin(BranchAwareAdminMixin, admin.ModelAdmin):
    list_display = ['employee', 'interview_date', 'interviewer', 'is_completed', 'is_confidential']
    list_filter = ['is_completed', 'is_confidential']
    search_fields = ['employee__employee_id', 'interviewer__employee_id']
    raw_id_fields = ['employee', 'interviewer', 'resignation']
    ordering = ['-interview_date']


@admin.register(SeparationChecklist)
class SeparationChecklistAdmin(BranchAwareAdminMixin, admin.ModelAdmin):
    list_display = ['resignation', 'task_name', 'assigned_to_department', 'assigned_to', 'is_completed', 'order']
    list_filter = ['assigned_to_department', 'is_completed']
    search_fields = ['resignation__employee__employee_id', 'task_name']
    raw_id_fields = ['resignation', 'assigned_to', 'completed_by']
    ordering = ['resignation', 'order']
