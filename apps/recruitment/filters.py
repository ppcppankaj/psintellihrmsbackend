"""Recruitment app filters."""
import django_filters
from .models import (
    JobPosting, Candidate, JobApplication, Interview, OfferLetter,
)


class JobPostingFilter(django_filters.FilterSet):
    title = django_filters.CharFilter(lookup_expr='icontains')
    department = django_filters.UUIDFilter()
    location = django_filters.UUIDFilter()
    designation = django_filters.UUIDFilter()
    branch = django_filters.UUIDFilter()
    employment_type = django_filters.ChoiceFilter(choices=[
        ('full_time', 'Full Time'), ('part_time', 'Part Time'),
        ('contract', 'Contract'), ('intern', 'Intern'),
    ])
    status = django_filters.ChoiceFilter(choices=[
        ('draft', 'Draft'), ('open', 'Open'),
        ('on_hold', 'On Hold'), ('closed', 'Closed'),
    ])
    is_active = django_filters.BooleanFilter()
    closing_date_from = django_filters.DateFilter(field_name='closing_date', lookup_expr='gte')
    closing_date_to = django_filters.DateFilter(field_name='closing_date', lookup_expr='lte')

    class Meta:
        model = JobPosting
        fields = ['department', 'location', 'designation', 'branch', 'employment_type', 'status']


class CandidateFilter(django_filters.FilterSet):
    name = django_filters.CharFilter(lookup_expr='icontains')
    email = django_filters.CharFilter(lookup_expr='icontains')
    source = django_filters.CharFilter()
    referred_by = django_filters.UUIDFilter()

    class Meta:
        model = Candidate
        fields = ['source', 'referred_by']


class JobApplicationFilter(django_filters.FilterSet):
    job = django_filters.UUIDFilter()
    candidate = django_filters.UUIDFilter()
    stage = django_filters.ChoiceFilter(choices=[
        ('new', 'New'), ('screening', 'Screening'), ('interview', 'Interview'),
        ('technical', 'Technical'), ('hr', 'HR'), ('offer', 'Offer'),
        ('hired', 'Hired'), ('rejected', 'Rejected'), ('withdrawn', 'Withdrawn'),
    ])

    class Meta:
        model = JobApplication
        fields = ['job', 'candidate', 'stage']


class InterviewFilter(django_filters.FilterSet):
    application = django_filters.UUIDFilter()
    branch = django_filters.UUIDFilter()
    round_type = django_filters.CharFilter()
    mode = django_filters.CharFilter()
    status = django_filters.ChoiceFilter(choices=[
        ('scheduled', 'Scheduled'), ('completed', 'Completed'),
        ('cancelled', 'Cancelled'), ('rescheduled', 'Rescheduled'),
    ])
    recommendation = django_filters.CharFilter()
    scheduled_after = django_filters.DateTimeFilter(field_name='scheduled_at', lookup_expr='gte')
    scheduled_before = django_filters.DateTimeFilter(field_name='scheduled_at', lookup_expr='lte')

    class Meta:
        model = Interview
        fields = ['application', 'branch', 'round_type', 'status', 'recommendation']


class OfferLetterFilter(django_filters.FilterSet):
    application = django_filters.UUIDFilter()
    designation = django_filters.UUIDFilter()
    status = django_filters.ChoiceFilter(choices=[
        ('pending', 'Pending'), ('sent', 'Sent'), ('accepted', 'Accepted'),
        ('rejected', 'Rejected'), ('expired', 'Expired'),
    ])
    joining_date_from = django_filters.DateFilter(field_name='joining_date', lookup_expr='gte')

    class Meta:
        model = OfferLetter
        fields = ['application', 'designation', 'status']
