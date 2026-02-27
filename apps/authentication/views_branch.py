"""
Branch Selector Views - Allow users to switch between branches
"""

from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.shortcuts import get_object_or_404
from apps.authentication.models import User, Branch, BranchUser
from apps.core.openapi_serializers import EmptySerializer
# from apps.core.context import set_current_organization, set_current_branch
import logging
import traceback

logger = logging.getLogger(__name__)

class BranchSelectorViewSet(viewsets.ViewSet):
    """
    ViewSet for branch selection and switching.
    Provides endpoints to list accessible branches and switch the current context.
    """
    permission_classes = [IsAuthenticated]
    serializer_class = EmptySerializer

    @action(detail=False, methods=['get'], url_path='my-branches')
    def my_branches(self, request):
        """
        Get all branches the current user has access to.
        Includes current branch indicator.
        """
        try:
            user = request.user
            user_org = user.get_organization() if hasattr(user, 'get_organization') else None
            
            if not user_org:
                # User has no organization - return empty branch list
                return Response({
                    'branches': [],
                    'current_branch': None,
                    'is_multi_branch': False,
                    'organization': None,
                    'message': 'No organization assigned'
                })
            
            # Get accessible branches
            branches = self._get_user_branches(user)
            
            # Get current branch from session or default
            current_branch_id = request.session.get('current_branch_id')
            current_branch = None
            
            if current_branch_id:
                 try:
                    current_branch = Branch.objects.filter(
                        id=current_branch_id,
                        is_active=True
                    ).first()
                 except:
                    current_branch = None
            
            # If no current branch or invalid, use first available
            if not current_branch and branches:
                current_branch = branches[0]
                request.session['current_branch_id'] = str(current_branch.id)
            
            return Response({
                'branches': [{
                    'id': str(branch.id),
                    'name': branch.name,
                    'code': branch.code,
                    'type': getattr(branch, 'branch_type', 'branch'),
                    'location': getattr(branch.location, 'name', None) if hasattr(branch, 'location') and branch.location else None,
                    'is_headquarters': getattr(branch, 'is_headquarters', False),
                } for branch in branches if hasattr(branch, 'id')],
                'current_branch': {
                    'id': str(current_branch.id),
                    'name': current_branch.name,
                    'code': current_branch.code,
                    'type': getattr(current_branch, 'branch_type', 'branch'),
                    'is_headquarters': getattr(current_branch, 'is_headquarters', False),
                } if current_branch and hasattr(current_branch, 'id') else None,
                'is_multi_branch': len(branches) > 1,
                'organization': {
                    'id': str(user_org.id),
                    'name': getattr(user_org, 'name', None),
                }
            })
        except Exception as e:
            logger.error(f"Error in my_branches: {str(e)}")
            logger.error(traceback.format_exc())
            return Response({
                "error": "Internal Server Error in Branch View",
                "detail": str(e)
            }, status=500)

    @action(detail=False, methods=['post'], url_path='switch')
    def switch_branch(self, request):
        """
        Switch current branch context.
        Validates that user has access to the target branch.
        """
        branch_id = request.data.get('branch_id')
        if not branch_id:
            return Response({'error': 'branch_id is required'}, status=status.HTTP_400_BAD_REQUEST)
            
        user = request.user
        
        # Verify access
        branches = self._get_user_branches(user)
        target_branch = None
        for b in branches:
            if str(b.id) == branch_id:
                target_branch = b
                break
                
        if not target_branch:
            return Response({'error': 'Access denied or branch not found'}, status=status.HTTP_403_FORBIDDEN)
            
        # Set in session
        request.session['current_branch_id'] = str(target_branch.id)
        
        # Set in thread context
        try:
            from apps.core.context import set_current_branch
            set_current_branch(target_branch)
        except ImportError:
            pass
        
        return Response({
            'status': 'success',
            'branch': {
                'id': str(target_branch.id),
                'name': target_branch.name,
                'code': target_branch.code
            }
        })

    def current_branch(self, request):
        """
        Return the current branch context for the user.
        This method is wired directly in urls.py for schema compatibility.
        """
        response = self.my_branches(request)
        if response.status_code != status.HTTP_200_OK:
            return response
        data = response.data or {}
        return Response({
            'current_branch': data.get('current_branch'),
            'organization': data.get('organization'),
            'is_multi_branch': data.get('is_multi_branch', False),
        })

    def _get_user_branches(self, user):
        """
        Internal helper to resolve accessible branches for a user.
        Logic:
        1. Explicit assignments in BranchUser
        2. Employee record branch
        3. If org admin/superuser, all branches in organization
        """
        branches = []
        
        # 1. Direct assignments via BranchUser
        try:
            branch_memberships = user.branch_memberships.filter(is_active=True).select_related('branch')
            branches = [membership.branch for membership in branch_memberships if membership.branch.is_active]
        except:
            pass
            
        # 2. Add branch from employee record if not already there
        try:
            if hasattr(user, 'employee') and user.employee.branch:
                emp_branch = user.employee.branch
                if emp_branch.is_active and emp_branch not in branches:
                    branches.append(emp_branch)
        except:
            pass
            
        # 3. If no branches yet but user is org admin or superuser, give all branches
        if not branches:
            is_org_admin = False
            try:
                is_org_admin = user.organization_memberships.filter(
                    role='ORG_ADMIN', 
                    is_active=True
                ).exists()
            except:
                pass
                
            if is_org_admin or user.is_superuser:
                user_org = user.get_organization() if hasattr(user, 'get_organization') else None
                if user_org:
                    try:
                        branches = list(Branch.objects.filter(organization=user_org, is_active=True))
                    except:
                        pass
        
        return branches
