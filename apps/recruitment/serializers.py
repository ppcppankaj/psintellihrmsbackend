from rest_framework import serializers
from .models import JobPosting, Candidate, JobApplication, Interview, OfferLetter
from apps.employees.serializers import (
    DepartmentSerializer,
    LocationSerializer,
    DesignationSerializer,
    EmployeeListSerializer
)

class JobPostingSerializer(serializers.ModelSerializer):
    department_details = DepartmentSerializer(source='department', read_only=True)
    location_details = LocationSerializer(source='location', read_only=True)
    designation_details = DesignationSerializer(source='designation', read_only=True)

    class Meta:
        model = JobPosting
        fields = [
            'id',
            'title',
            'department',
            'department_details',
            'location',
            'location_details',
            'designation',
            'designation_details',
            'status',
            'positions',
            'description',
            'created_at',
            'updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']



class CandidateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Candidate
        fields = [
            'id',
            'first_name',
            'last_name',
            'email',
            'phone',
            'resume',
            'created_at',
        ]
        read_only_fields = ['id', 'created_at']


class JobApplicationSerializer(serializers.ModelSerializer):
    job_details = JobPostingSerializer(source='job', read_only=True)
    candidate_details = CandidateSerializer(source='candidate', read_only=True)

    class Meta:
        model = JobApplication
        fields = [
            'id',
            'job',
            'job_details',
            'candidate',
            'candidate_details',
            'stage',          # ✅ EXISTS
            'created_at',     # ✅ EXISTS
            'updated_at',     # ✅ EXISTS
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']


class InterviewSerializer(serializers.ModelSerializer):
    interviewers_details = EmployeeListSerializer(source='interviewers', many=True, read_only=True)

    class Meta:
        model = Interview
        fields = [
            'id',
            'application',
            'round_type',
            'scheduled_at',
            'status',
            'interviewers',
            'interviewers_details',
            'created_at',
        ]
        read_only_fields = ['id', 'created_at']


class OfferLetterSerializer(serializers.ModelSerializer):
    class Meta:
        model = OfferLetter
        fields = [
            'id',
            'application',
            'offered_ctc',
            'joining_date',
            'status',
            'valid_until',
            'accepted_at',
            'created_at',
        ]
        read_only_fields = ['id', 'created_at']
