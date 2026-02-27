"""Recruitment Admin"""
from django.contrib import admin
from apps.core.admin_mixins import BranchAwareAdminMixin, OrganizationAwareAdminMixin
from .models import JobPosting, Candidate, JobApplication, Interview, OfferLetter


@admin.register(JobPosting)
class JobPostingAdmin(BranchAwareAdminMixin, admin.ModelAdmin):
    list_display = ['title', 'code', 'department', 'branch', 'status', 'positions', 'published_at']
    list_filter = ['status', 'employment_type', 'department', 'branch']
    search_fields = ['title', 'code']
    raw_id_fields = ['department', 'location', 'designation', 'branch', 'hiring_manager']


@admin.register(Candidate)
class CandidateAdmin(OrganizationAwareAdminMixin, admin.ModelAdmin):
    list_display = ['first_name', 'last_name', 'email', 'total_experience', 'source', 'created_at']
    list_filter = ['source', 'created_at']
    search_fields = ['first_name', 'last_name', 'email']


@admin.register(JobApplication)
class JobApplicationAdmin(OrganizationAwareAdminMixin, admin.ModelAdmin):
    list_display = ['candidate', 'job', 'stage', 'ai_score', 'created_at']
    list_filter = ['stage', 'job']
    search_fields = ['candidate__first_name', 'candidate__last_name', 'job__title']
    raw_id_fields = ['job', 'candidate']


@admin.register(Interview)
class InterviewAdmin(BranchAwareAdminMixin, admin.ModelAdmin):
    list_display = ['application', 'round_type', 'branch', 'scheduled_at', 'status', 'rating', 'recommendation']
    list_filter = ['round_type', 'status', 'mode', 'branch']
    raw_id_fields = ['application', 'branch']
    filter_horizontal = ['interviewers']


@admin.register(OfferLetter)
class OfferLetterAdmin(OrganizationAwareAdminMixin, admin.ModelAdmin):
    list_display = ['application', 'offered_ctc', 'joining_date', 'status', 'valid_until']
    list_filter = ['status']
    raw_id_fields = ['application', 'designation']
