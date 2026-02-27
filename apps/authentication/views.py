"""
Authentication Views
"""

import secrets
import pyotp
import qrcode
import io
import base64
import logging
from apps.core.openapi_serializers import EmptySerializer
from datetime import timedelta

from django.conf import settings
from django.utils import timezone
from django.core.exceptions import PermissionDenied

from rest_framework import status, views, viewsets, serializers, mixins
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.decorators import api_view, permission_classes, action

from rest_framework_simplejwt.views import TokenObtainPairView
from rest_framework_simplejwt.tokens import RefreshToken
from apps.authentication.services.emails import send_password_reset_email
from apps.core.throttling import (
    BurstRateThrottle,
    LoginRateThrottle,
    PasswordResetThrottle,
    TwoFactorRateThrottle,
)

from apps.authentication.authentication import CsrfExemptSessionAuthentication
from .models import User, UserSession, PasswordResetToken
from .serializers import (
    CustomTokenObtainPairSerializer,
    UserSerializer,
    UserCreateSerializer,
    UserOrgAdminCreateSerializer,
    UserSelfProfileSerializer,
    PasswordChangeSerializer,
    PasswordResetRequestSerializer,
    PasswordResetConfirmSerializer,
    TwoFactorEnableSerializer,
    TwoFactorVerifySerializer,
    UserSessionSerializer,
    OrganizationUserSerializer,
    BranchSerializer,
    BranchUserSerializer,
)
from .permissions import IsSameOrganization
from .models_hierarchy import OrganizationUser, Branch, BranchUser
from drf_spectacular.utils import extend_schema
# from apps.core.org_permissions import IsOrgAdminOrSuperuser
# from apps.core.tenant_guards import OrganizationViewSetMixin


# =====================================================
# LOGIN
# =====================================================

logger = logging.getLogger(__name__)

class SimpleUserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ['id', 'email', 'first_name', 'last_name', 'is_superuser']

class CustomTokenObtainPairView(TokenObtainPairView):
    """
    🔒 SECURITY-HARDENED LOGIN
    """
    authentication_classes = [CsrfExemptSessionAuthentication]
    permission_classes = [AllowAny]
    throttle_classes = [LoginRateThrottle, BurstRateThrottle]
    serializer_class = CustomTokenObtainPairSerializer

    def get(self, request, *args, **kwargs):
        return Response({"branding": self._get_branding_context(request)})

    def post(self, request, *args, **kwargs):
        response = super().post(request, *args, **kwargs)

        if response.status_code == 200:
            email = request.data.get("email")
            try:
                user = User.objects.get(email=email)
                
                request_org = getattr(request, 'organization', None)
                if request_org and not user.is_superuser:
                    is_member = user.organization_memberships.filter(
                        organization=request_org,
                        is_active=True,
                    ).exists()
                    if not is_member:
                        raise PermissionDenied("User is not a member of this organization")

                # 🔒 Enforce org binding
                if not user.is_superuser and not user.get_organization():
                    from django.core.exceptions import PermissionDenied
                    raise PermissionDenied("User is not assigned to an organization")

                user.record_login_attempt(
                    success=True,
                    ip_address=self.get_client_ip(request),
                    device=request.META.get("HTTP_USER_AGENT", "")
                )

                self.create_session(
                    request,
                    user,
                    response.data.get("refresh")
                )
            except User.DoesNotExist:
                pass

        if hasattr(response, "data"):
            response.data = response.data or {}
            response.data["branding"] = self._get_branding_context(request)

        return response

    def _get_branding_context(self, request):
        branding = getattr(request, "domain_branding", None)
        if branding:
            return branding
        return {
            "organization_id": None,
            "organization_name": getattr(settings, "DEFAULT_BRAND_NAME", "PS IntelliHR"),
            "logo_url": getattr(settings, "DEFAULT_BRAND_LOGO_URL", None),
            "primary_color": getattr(settings, "DEFAULT_BRAND_PRIMARY_COLOR", "#1976d2"),
            "secondary_color": getattr(settings, "DEFAULT_BRAND_SECONDARY_COLOR", "#dc004e"),
            "email": {},
        }

    def get_client_ip(self, request):
        xff = request.META.get("HTTP_X_FORWARDED_FOR")
        if xff:
            return xff.split(",")[0].strip()
        return request.META.get("REMOTE_ADDR")

    def create_session(self, request, user, refresh_token):
        user_agent = request.META.get("HTTP_USER_AGENT", "")
        session_org = getattr(request, 'organization', None) or user.get_organization()

        UserSession.objects.create(
            user=user,
            organization=session_org,
            session_key=secrets.token_urlsafe(32),
            refresh_token=refresh_token,
            ip_address=self.get_client_ip(request),
            user_agent=user_agent,
            device_type=self.detect_device_type(user_agent),
            expires_at=timezone.now() + timedelta(days=7),
        )

    def detect_device_type(self, user_agent):
        ua = user_agent.lower()
        if any(x in ua for x in ["mobile", "android", "iphone"]):
            return "mobile"
        if any(x in ua for x in ["tablet", "ipad"]):
            return "tablet"
        return "desktop"


# =====================================================
# LOGOUT
# =====================================================

class LogoutView(APIView):
    permission_classes = [IsAuthenticated]
    serializer_class = EmptySerializer

    def post(self, request):
        refresh_token = request.data.get("refresh_token")

        if refresh_token:
            try:
                RefreshToken(refresh_token).blacklist()
            except Exception:
                pass

            UserSession.objects.filter(
                user=request.user,
                refresh_token=refresh_token,
            ).update(is_active=False)

        return Response({"success": True})


# =====================================================
# PROFILE
# =====================================================

class ProfileView(APIView):
    permission_classes = [IsAuthenticated]
    serializer_class = UserSelfProfileSerializer

    def get(self, request):
        serializer = UserSelfProfileSerializer(request.user)
        return Response(serializer.data)


@extend_schema(responses=UserSerializer)
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def user_profile(request):
    """
    🔒 User profile with tenant context
    """
    user = request.user
    serializer = UserSerializer(user)
    return Response(serializer.data)


# =====================================================
# PASSWORD MANAGEMENT
# =====================================================

class PasswordChangeView(APIView):
    permission_classes = [IsAuthenticated]
    serializer_class = PasswordChangeSerializer

    def post(self, request):
        serializer = PasswordChangeSerializer(
            data=request.data,
            context={"request": request}
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response({"success": True})


class PasswordResetRequestView(APIView):
    authentication_classes = [CsrfExemptSessionAuthentication]
    permission_classes = [AllowAny]
    throttle_classes = [PasswordResetThrottle, BurstRateThrottle]
    serializer_class = PasswordResetRequestSerializer

    def post(self, request):
        serializer = PasswordResetRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response({"success": True})


class PasswordResetConfirmView(APIView):
    authentication_classes = [CsrfExemptSessionAuthentication]
    permission_classes = [AllowAny]
    throttle_classes = [PasswordResetThrottle, BurstRateThrottle]
    serializer_class = PasswordResetConfirmSerializer

    def post(self, request):
        serializer = PasswordResetConfirmSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response({"success": True})


# =====================================================
# TWO FACTOR AUTH (2FA)
# =====================================================

class TwoFactorEnableView(APIView):
    permission_classes = [IsAuthenticated]
    throttle_classes = [TwoFactorRateThrottle, BurstRateThrottle]
    serializer_class = TwoFactorEnableSerializer

    def post(self, request):
        serializer = TwoFactorEnableSerializer(
            data=request.data,
            context={"request": request}
        )
        serializer.is_valid(raise_exception=True)
        data = serializer.save()
        return Response(data)


class TwoFactorVerifyView(APIView):
    permission_classes = [IsAuthenticated]
    throttle_classes = [TwoFactorRateThrottle, BurstRateThrottle]
    serializer_class = TwoFactorVerifySerializer

    def post(self, request):
        serializer = TwoFactorVerifySerializer(
            data=request.data,
            context={"request": request}
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response({"success": True})


class TwoFactorDisableView(APIView):
    permission_classes = [IsAuthenticated]
    throttle_classes = [TwoFactorRateThrottle, BurstRateThrottle]
    serializer_class = EmptySerializer

    def post(self, request):
        request.user.disable_2fa()
        return Response({"success": True})


# =====================================================
# USER MANAGEMENT (ORG ADMIN)
# =====================================================

from apps.core.rbac_hardening import SuperuserLeakageGuardMixin, AuditLogger


class UserViewSet(SuperuserLeakageGuardMixin, viewsets.ModelViewSet):
    """
    🔒 Tenant-safe user management with superuser leakage protection.

    S2 — SuperuserLeakageGuardMixin strips superuser records from
    org-scoped listings and blocks PATCH/DELETE of superuser accounts
    by non-superusers.
    """
    queryset = User.objects.none()
    permission_classes = [IsAuthenticated, IsSameOrganization]

    def check_permissions(self, request):
        super().check_permissions(request)
        from apps.core.org_permissions import IsOrgAdminOrSuperuser
        permission = IsOrgAdminOrSuperuser()
        if not permission.has_permission(request, self):
            self.permission_denied(request, message=getattr(permission, 'message', None))

    def get_queryset(self):
        request_org = getattr(self.request, 'organization', None)

        if request_org:
            qs = User.objects.filter(
                organization_memberships__organization=request_org,
                organization_memberships__is_active=True,
            ).distinct()
        elif self.request.user.is_superuser:
            qs = User.objects.all()
        else:
            return User.objects.none()

        # S2: SuperuserLeakageGuardMixin.get_queryset() further strips
        # is_superuser=True for non-superadmin callers
        user = self.request.user
        if not user.is_superuser:
            qs = qs.filter(is_superuser=False)

        return qs

    def get_serializer_class(self):
        if self.action == "create":
            return UserOrgAdminCreateSerializer
        return UserSerializer

    def create(self, request, *args, **kwargs):
        if not request.user.is_org_admin and not request.user.is_superuser:
            raise PermissionDenied("Only org admins can create users")
        return super().create(request, *args, **kwargs)

    def update(self, request, *args, **kwargs):
        target_user = self.get_object()

        # S2: Block modification of superuser by non-superuser
        if getattr(target_user, 'is_superuser', False) and not request.user.is_superuser:
            raise PermissionDenied("Cannot modify superuser accounts")

        if target_user == request.user and request.user.is_org_admin:
            raise PermissionDenied("Organization admins cannot modify their own account")

        if ("organization" in request.data or "organization_id" in request.data) and not request.user.is_superuser:
            raise PermissionDenied("Only superusers can change organization")

        if any(
            f in request.data
            for f in ["is_org_admin", "is_staff", "is_superuser"]
        ):
            if not request.user.is_superuser:
                raise PermissionDenied(
                    "Only superusers can modify privilege levels"
                )

        return super().update(request, *args, **kwargs)

    def destroy(self, request, *args, **kwargs):
        target_user = self.get_object()
        # S2: Block deletion of superuser by non-superuser
        if getattr(target_user, 'is_superuser', False) and not request.user.is_superuser:
            raise PermissionDenied("Cannot delete superuser accounts")
        return super().destroy(request, *args, **kwargs)


# Backward compatibility
UserManagementViewSet = UserViewSet


class OrganizationScopedViewMixin:
    """Utility mixin to enforce presence of request.organization for mutating actions."""

    def _require_org(self):
        org = getattr(self.request, 'organization', None)
        if org:
            return org
        raise PermissionDenied("Organization context required")


class OrganizationMembershipViewSet(OrganizationScopedViewMixin, viewsets.ModelViewSet):
    queryset = OrganizationUser.objects.select_related('organization', 'user')
    serializer_class = OrganizationUserSerializer
    permission_classes = [IsAuthenticated, IsSameOrganization]

    def get_queryset(self):
        qs = super().get_queryset()
        org = getattr(self.request, 'organization', None)
        if org:
            return qs.filter(organization=org)
        if self.request.user.is_superuser:
            return qs
        return qs.none()

    def perform_create(self, serializer):
        serializer.save(organization=self._require_org(), created_by=self.request.user)


class BranchViewSet(OrganizationScopedViewMixin, viewsets.ModelViewSet):
    queryset = Branch.objects.select_related('organization')
    serializer_class = BranchSerializer
    permission_classes = [IsAuthenticated, IsSameOrganization]

    def get_queryset(self):
        qs = super().get_queryset()
        org = getattr(self.request, 'organization', None)
        if org:
            return qs.filter(organization=org)
        if self.request.user.is_superuser:
            return qs
        return qs.none()

    def perform_create(self, serializer):
        serializer.save(organization=self._require_org(), created_by=self.request.user)

    @action(detail=False, methods=['get'], url_path='my-branches')
    def my_branches(self, request):
        try:
            user = request.user
            user_org = user.get_organization() if hasattr(user, 'get_organization') else None

            if not user_org:
                return Response({
                    'branches': [],
                    'current_branch': None,
                    'is_multi_branch': False,
                    'organization': None,
                    'message': 'No organization assigned'
                })

            branches = self._get_user_branches(user)
            current_branch_id = request.session.get('current_branch_id')
            current_branch = None

            if current_branch_id:
                current_branch = Branch.objects.filter(
                    id=current_branch_id,
                    is_active=True
                ).first()

            if not current_branch and branches:
                current_branch = branches[0]
                request.session['current_branch_id'] = str(current_branch.id)

            return Response({
                'branches': [
                    {
                        'id': str(branch.id),
                        'name': branch.name,
                        'code': branch.code,
                        'type': getattr(branch, 'branch_type', 'branch'),
                        'location': getattr(getattr(branch, 'location', None), 'name', None),
                        'is_headquarters': getattr(branch, 'is_headquarters', False),
                    }
                    for branch in branches if hasattr(branch, 'id')
                ],
                'current_branch': {
                    'id': str(current_branch.id),
                    'name': current_branch.name,
                    'code': current_branch.code,
                    'type': getattr(current_branch, 'branch_type', 'branch'),
                    'is_headquarters': getattr(current_branch, 'is_headquarters', False),
                } if current_branch else None,
                'is_multi_branch': len(branches) > 1,
                'organization': {
                    'id': str(user_org.id),
                    'name': getattr(user_org, 'name', None),
                }
            })
        except Exception as exc:
            logger.error("Error in my_branches: %s", exc, exc_info=True)
            return Response({
                'error': 'Internal Server Error in Branch View',
                'detail': str(exc)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    @action(detail=False, methods=['post'], url_path='switch-branch')
    def switch_branch(self, request):
        branch_id = request.data.get('branch_id')
        if not branch_id:
            return Response({'error': 'branch_id is required'}, status=status.HTTP_400_BAD_REQUEST)

        branches = self._get_user_branches(request.user)
        target_branch = next((b for b in branches if str(b.id) == str(branch_id)), None)

        if not target_branch:
            return Response({'error': 'Access denied or branch not found'}, status=status.HTTP_403_FORBIDDEN)

        request.session['current_branch_id'] = str(target_branch.id)

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

    @action(detail=False, methods=['get'], url_path='current-branch')
    def current_branch(self, request):
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
        branches = []
        try:
            branch_memberships = user.branch_memberships.filter(is_active=True).select_related('branch')
            branches = [membership.branch for membership in branch_memberships if membership.branch.is_active]
        except Exception:
            branches = []

        try:
            employee_branch = getattr(getattr(user, 'employee', None), 'branch', None)
            if employee_branch and employee_branch.is_active and employee_branch not in branches:
                branches.append(employee_branch)
        except Exception:
            pass

        if not branches:
            try:
                is_org_admin = user.organization_memberships.filter(
                    role=OrganizationUser.RoleChoices.ORG_ADMIN,
                    is_active=True
                ).exists()
            except Exception:
                is_org_admin = False

            if is_org_admin or user.is_superuser:
                user_org = user.get_organization() if hasattr(user, 'get_organization') else None
                if user_org:
                    try:
                        branches = list(Branch.objects.filter(organization=user_org, is_active=True))
                    except Exception:
                        branches = []

        return branches


class BranchUserViewSet(OrganizationScopedViewMixin, viewsets.ModelViewSet):
    queryset = BranchUser.objects.select_related('branch', 'branch__organization', 'user')
    serializer_class = BranchUserSerializer
    permission_classes = [IsAuthenticated, IsSameOrganization]

    def get_queryset(self):
        qs = super().get_queryset()
        org = getattr(self.request, 'organization', None)
        if org:
            return qs.filter(branch__organization=org)
        if self.request.user.is_superuser:
            return qs
        return qs.none()

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)


class UserSessionViewSet(
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.DestroyModelMixin,
    viewsets.GenericViewSet,
):
    queryset = UserSession.objects.select_related('user', 'organization')
    serializer_class = UserSessionSerializer
    permission_classes = [IsAuthenticated, IsSameOrganization]

    def get_queryset(self):
        qs = super().get_queryset()
        org = getattr(self.request, 'organization', None)
        if org:
            return qs.filter(organization=org)
        if self.request.user.is_superuser:
            return qs
        return qs.none()

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        if instance.user != request.user and not request.user.is_superuser:
            raise PermissionDenied('You may only revoke your own sessions')
        instance.is_active = False
        instance.save(update_fields=['is_active'])
        return Response(status=status.HTTP_204_NO_CONTENT)
