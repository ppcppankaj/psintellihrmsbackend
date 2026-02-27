"""
Recruitment ViewSets

Provides API endpoints for recruitment management including:
- Job Postings (branch-filtered)
- Candidates (organization-level, but linked to applications)
- Job Applications (branch-filtered via job posting)
- Interviews (branch-filtered)
- Offer Letters (branch-filtered via application/job)
"""

from django.db import transaction
from django.db.models import Count, Q
from django.utils import timezone
from rest_framework import viewsets, filters, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django_filters.rest_framework import DjangoFilterBackend

from apps.core.permissions_branch import BranchFilterBackend, BranchPermission
from apps.core.tenant_guards import OrganizationViewSetMixin
from .permissions import RecruitmentTenantPermission

from .models import JobPosting, Candidate, JobApplication, Interview, OfferLetter
from .serializers import (
    JobPostingSerializer, CandidateSerializer, JobApplicationSerializer,
    InterviewSerializer, OfferLetterSerializer
)
from .filters import JobPostingFilter, CandidateFilter, JobApplicationFilter, InterviewFilter, OfferLetterFilter


class BranchFilterMixin:
    """Mixin providing branch filtering capabilities for recruitment ViewSets."""
    
    def get_branch_ids(self):
        """Get list of branch IDs the current user can access."""
        if self.request.user.is_superuser:
            return None  # Superuser can access all
        from apps.authentication.models_hierarchy import BranchUser
        return list(BranchUser.objects.filter(
            user=self.request.user,
            is_active=True
        ).values_list('branch_id', flat=True))


class JobPostingViewSet(OrganizationViewSetMixin, BranchFilterMixin, viewsets.ModelViewSet):
    """
    ViewSet for job postings.
    Filtered by user's accessible branches.
    """
    queryset = JobPosting.objects.none()
    serializer_class = JobPostingSerializer
    permission_classes = [IsAuthenticated, RecruitmentTenantPermission, BranchPermission]
    filter_backends = [BranchFilterBackend, DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_class = JobPostingFilter
    search_fields = ['title', 'description']
    
    def get_queryset(self):
        queryset = super().get_queryset()
        branch_ids = self.get_branch_ids()
        if branch_ids is None:
            return queryset
        if not branch_ids:
            return queryset.none()
        # Filter by department's branch
        return queryset.filter(department__branch_id__in=branch_ids)

    @action(detail=True, methods=['post'])
    def publish(self, request, pk=None):
        """Publish a job posting (set status to 'open' and record published_at)."""
        job = self.get_object()
        if job.status == 'open':
            return Response({'error': 'Job is already published'}, status=status.HTTP_400_BAD_REQUEST)
        job.status = 'open'
        job.published_at = timezone.now()
        job.save(update_fields=['status', 'published_at', 'updated_at'])
        return Response({'status': 'published', 'published_at': job.published_at})

    @action(detail=True, methods=['post'])
    def unpublish(self, request, pk=None):
        """Unpublish a job posting (set status to 'draft')."""
        job = self.get_object()
        if job.status == 'draft':
            return Response({'error': 'Job is already unpublished'}, status=status.HTTP_400_BAD_REQUEST)
        job.status = 'draft'
        job.save(update_fields=['status', 'updated_at'])
        return Response({'status': 'unpublished'})

    @action(detail=True, methods=['post'])
    def clone(self, request, pk=None):
        """Clone a job posting to create a new draft."""
        original = self.get_object()
        cloned = JobPosting.objects.create(
            organization=original.organization,
            title=f"{original.title} (Copy)",
            code=f"{original.code}-COPY",
            department=original.department,
            location=original.location,
            designation=original.designation,
            branch=original.branch,
            description=original.description,
            requirements=original.requirements,
            responsibilities=original.responsibilities,
            employment_type=original.employment_type,
            experience_min=original.experience_min,
            experience_max=original.experience_max,
            salary_min=original.salary_min,
            salary_max=original.salary_max,
            positions=original.positions,
            status='draft',
            closing_date=original.closing_date,
            hiring_manager=original.hiring_manager,
            created_by=request.user,
        )
        serializer = self.get_serializer(cloned)
        return Response(serializer.data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['get'])
    def funnel_stats(self, request, pk=None):
        """Get hiring funnel statistics for a job posting."""
        job = self.get_object()
        applications = job.applications.all()
        
        stage_counts = applications.values('stage').annotate(count=Count('id'))
        stages_dict = {item['stage']: item['count'] for item in stage_counts}
        
        total = applications.count()
        hired = stages_dict.get('hired', 0)
        rejected = stages_dict.get('rejected', 0)
        withdrawn = stages_dict.get('withdrawn', 0)
        active = total - hired - rejected - withdrawn
        
        return Response({
            'total_applications': total,
            'active_applications': active,
            'hired': hired,
            'rejected': rejected,
            'withdrawn': withdrawn,
            'stages': {
                'new': stages_dict.get('new', 0),
                'screening': stages_dict.get('screening', 0),
                'interview': stages_dict.get('interview', 0),
                'technical': stages_dict.get('technical', 0),
                'hr': stages_dict.get('hr', 0),
                'offer': stages_dict.get('offer', 0),
                'hired': hired,
                'rejected': rejected,
                'withdrawn': withdrawn,
            },
            'conversion_rate': round((hired / total * 100), 2) if total > 0 else 0,
        })


class CandidateViewSet(OrganizationViewSetMixin, BranchFilterMixin, viewsets.ModelViewSet):
    """
    ViewSet for candidates.
    Candidates are filtered based on their applications to jobs in user's branches.
    """
    queryset = Candidate.objects.none()
    serializer_class = CandidateSerializer
    permission_classes = [IsAuthenticated, RecruitmentTenantPermission, BranchPermission]
    filter_backends = [BranchFilterBackend, DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_class = CandidateFilter
    search_fields = ['first_name', 'last_name', 'email']
    
    def get_queryset(self):
        queryset = super().get_queryset()
        branch_ids = self.get_branch_ids()
        if branch_ids is None:
            return queryset
        if not branch_ids:
            return queryset.none()
        # Filter candidates who have applied to jobs in user's branches
        return queryset.filter(
            applications__job__department__branch_id__in=branch_ids
        ).distinct()


class JobApplicationViewSet(OrganizationViewSetMixin, BranchFilterMixin, viewsets.ModelViewSet):
    """
    ViewSet for job applications.
    Filtered by job posting's branch via department.
    """
    queryset = JobApplication.objects.none()
    serializer_class = JobApplicationSerializer
    permission_classes = [IsAuthenticated, RecruitmentTenantPermission, BranchPermission]
    filter_backends = [BranchFilterBackend, DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_class = JobApplicationFilter
    
    def get_queryset(self):
        queryset = super().get_queryset()
        branch_ids = self.get_branch_ids()
        if branch_ids is None:
            return queryset
        if not branch_ids:
            return queryset.none()
        # Filter by job's department's branch
        return queryset.filter(job__department__branch_id__in=branch_ids)

    @action(detail=True, methods=['post'])
    def change_stage(self, request, pk=None):
        """Move application to a new recruitment stage."""
        application = self.get_object()
        new_stage = request.data.get('stage')
        if new_stage:
            application.stage = new_stage
            application.save()
            return Response({'status': 'stage updated'})
        return Response({'error': 'stage not provided'}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=['post'])
    def convert_to_employee(self, request, pk=None):
        """Convert a hired candidate to an employee record."""
        from django.contrib.auth import get_user_model
        from apps.employees.models import Employee
        
        application = self.get_object()
        
        if application.stage != 'hired':
            return Response(
                {'error': 'Only hired candidates can be converted to employees'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        if not hasattr(application, 'offer') or application.offer.status != 'accepted':
            return Response(
                {'error': 'Candidate must have an accepted offer letter'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        candidate = application.candidate
        offer = application.offer
        job = application.job
        
        User = get_user_model()
        if User.objects.filter(email=candidate.email).exists():
            return Response(
                {'error': 'User with this email already exists'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        with transaction.atomic():
            user = User.objects.create_user(
                email=candidate.email,
                first_name=candidate.first_name,
                last_name=candidate.last_name,
                organization=application.organization,
            )
            
            employee_id = request.data.get('employee_id')
            if not employee_id:
                last_emp = Employee.objects.filter(
                    organization=application.organization
                ).order_by('-id').first()
                emp_num = (last_emp.id + 1) if last_emp else 1
                employee_id = f"EMP{emp_num:05d}"
            
            employee = Employee.objects.create(
                organization=application.organization,
                user=user,
                employee_id=employee_id,
                department=job.department,
                designation=offer.designation or job.designation,
                location=job.location,
                branch=job.branch,
                employment_type=job.employment_type,
                date_of_joining=offer.joining_date,
                created_by=request.user,
            )
            
            application.stage = 'hired'
            application.save(update_fields=['stage', 'updated_at'])
        
        return Response({
            'status': 'converted',
            'employee_id': employee.employee_id,
            'user_id': user.id,
        }, status=status.HTTP_201_CREATED)


class InterviewViewSet(OrganizationViewSetMixin, BranchFilterMixin, viewsets.ModelViewSet):
    """
    ViewSet for interviews.
    Filtered by application's job's branch.
    """
    queryset = Interview.objects.none()
    serializer_class = InterviewSerializer
    permission_classes = [IsAuthenticated, RecruitmentTenantPermission, BranchPermission]
    filter_backends = [BranchFilterBackend, DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_class = InterviewFilter
    
    def get_queryset(self):
        queryset = super().get_queryset()
        branch_ids = self.get_branch_ids()
        if branch_ids is None:
            return queryset
        if not branch_ids:
            return queryset.none()
        # Filter by application's job's department's branch
        return queryset.filter(application__job__department__branch_id__in=branch_ids)

    @action(detail=True, methods=['post'])
    def reschedule(self, request, pk=None):
        """Reschedule an interview to a new date/time."""
        interview = self.get_object()
        
        new_scheduled_at = request.data.get('scheduled_at')
        if not new_scheduled_at:
            return Response(
                {'error': 'scheduled_at is required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        if interview.status in ['completed', 'cancelled']:
            return Response(
                {'error': f'Cannot reschedule a {interview.status} interview'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        interview.scheduled_at = new_scheduled_at
        interview.status = 'rescheduled'
        if 'duration_minutes' in request.data:
            interview.duration_minutes = request.data['duration_minutes']
        if 'meeting_link' in request.data:
            interview.meeting_link = request.data['meeting_link']
        if 'location' in request.data:
            interview.location = request.data['location']
        interview.save()
        
        serializer = self.get_serializer(interview)
        return Response(serializer.data)

    @action(detail=True, methods=['post'])
    def cancel(self, request, pk=None):
        """Cancel a scheduled interview."""
        interview = self.get_object()
        
        if interview.status == 'cancelled':
            return Response(
                {'error': 'Interview is already cancelled'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        if interview.status == 'completed':
            return Response(
                {'error': 'Cannot cancel a completed interview'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        interview.status = 'cancelled'
        interview.save(update_fields=['status', 'updated_at'])
        return Response({'status': 'cancelled'})

    @action(detail=True, methods=['post'])
    def add_feedback(self, request, pk=None):
        """Add feedback and recommendation for an interview."""
        interview = self.get_object()
        
        feedback = request.data.get('feedback')
        rating = request.data.get('rating')
        recommendation = request.data.get('recommendation')
        
        if not any([feedback, rating, recommendation]):
            return Response(
                {'error': 'At least one of feedback, rating, or recommendation is required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        if recommendation and recommendation not in ['hire', 'reject', 'hold', 'next_round']:
            return Response(
                {'error': 'Invalid recommendation. Must be one of: hire, reject, hold, next_round'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        if feedback:
            interview.feedback = feedback
        if rating is not None:
            interview.rating = rating
        if recommendation:
            interview.recommendation = recommendation
        
        if interview.status == 'scheduled':
            interview.status = 'completed'
        
        interview.save()
        serializer = self.get_serializer(interview)
        return Response(serializer.data)


class OfferLetterViewSet(OrganizationViewSetMixin, BranchFilterMixin, viewsets.ModelViewSet):
    """
    ViewSet for offer letters.
    Contains sensitive compensation data - must be branch-filtered.
    """
    queryset = OfferLetter.objects.none()
    serializer_class = OfferLetterSerializer
    permission_classes = [IsAuthenticated, RecruitmentTenantPermission, BranchPermission]
    filter_backends = [BranchFilterBackend, DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_class = OfferLetterFilter
    
    def get_queryset(self):
        queryset = super().get_queryset()
        branch_ids = self.get_branch_ids()
        if branch_ids is None:
            return queryset
        if not branch_ids:
            return queryset.none()
        # Filter by application's job's department's branch
        return queryset.filter(application__job__department__branch_id__in=branch_ids)

    @action(detail=True, methods=['post'])
    def send(self, request, pk=None):
        """Send the offer letter to the candidate (set status to 'sent')."""
        offer = self.get_object()
        
        if offer.status != 'pending':
            return Response(
                {'error': f'Cannot send offer with status: {offer.status}'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        offer.status = 'sent'
        offer.save(update_fields=['status', 'updated_at'])
        
        return Response({'status': 'sent'})

    @action(detail=True, methods=['post'])
    def accept(self, request, pk=None):
        """Mark the offer letter as accepted by candidate."""
        offer = self.get_object()
        
        if offer.status != 'sent':
            return Response(
                {'error': 'Only sent offers can be accepted'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        offer.status = 'accepted'
        offer.accepted_at = timezone.now()
        offer.save(update_fields=['status', 'accepted_at', 'updated_at'])
        
        application = offer.application
        application.stage = 'hired'
        application.save(update_fields=['stage', 'updated_at'])
        
        return Response({'status': 'accepted', 'accepted_at': offer.accepted_at})

    @action(detail=True, methods=['post'])
    def reject(self, request, pk=None):
        """Mark the offer letter as rejected by candidate."""
        offer = self.get_object()
        
        if offer.status not in ['sent', 'pending']:
            return Response(
                {'error': f'Cannot reject offer with status: {offer.status}'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        offer.status = 'rejected'
        offer.save(update_fields=['status', 'updated_at'])
        
        application = offer.application
        application.stage = 'rejected'
        application.save(update_fields=['stage', 'updated_at'])
        
        return Response({'status': 'rejected'})

    @action(detail=True, methods=['post'])
    def extend(self, request, pk=None):
        """Extend the offer validity or modify offer terms."""
        offer = self.get_object()
        
        if offer.status in ['accepted', 'rejected']:
            return Response(
                {'error': f'Cannot extend offer with status: {offer.status}'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        valid_until = request.data.get('valid_until')
        offered_ctc = request.data.get('offered_ctc')
        joining_date = request.data.get('joining_date')
        
        if not any([valid_until, offered_ctc, joining_date]):
            return Response(
                {'error': 'At least one of valid_until, offered_ctc, or joining_date is required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        if valid_until:
            offer.valid_until = valid_until
        if offered_ctc:
            offer.offered_ctc = offered_ctc
        if joining_date:
            offer.joining_date = joining_date
        
        if offer.status == 'expired':
            offer.status = 'sent'
        
        offer.save()
        serializer = self.get_serializer(offer)
        return Response(serializer.data)
