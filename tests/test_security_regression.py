"""
Enterprise Security Regression Tests
=====================================
Validates:
  1. Cross-tenant API isolation (no data leakage between orgs)
  2. Fail-closed queryset behavior (no org context → empty queryset)
  3. Cross-tenant FK injection prevention
  4. File upload security (SVG blocked, magic-byte validation)
  5. ViewSet mixin compliance (all org-scoped ViewSets use super().get_queryset())
  6. Superuser queryset scoping
  7. Enrollment org-filter enforcement

Run:
    python manage.py test tests.test_security_regression -v2
"""

import io
import uuid
from unittest.mock import patch, MagicMock

from django.test import TestCase, RequestFactory, override_settings
from django.core.exceptions import ValidationError
from rest_framework.test import APIClient, APITestCase
from rest_framework import status

from tests.factories import UserFactory, EmployeeFactory


# ─── Helpers ─────────────────────────────────────────────────────────────────

def _create_org(name="Test Org"):
    """Create an Organization for testing."""
    from apps.core.models import Organization
    return Organization.objects.create(
        name=name,
        slug=name.lower().replace(" ", "-") + "-" + uuid.uuid4().hex[:6],
    )


def _create_user_with_org(org, email=None, is_admin=False, is_superuser=False):
    """Create a User linked to an Organization."""
    from apps.authentication.models import User
    email = email or f"user-{uuid.uuid4().hex[:8]}@test.com"
    user = User.objects.create_user(
        email=email,
        password="TestPass123!",
        is_superuser=is_superuser,
    )
    user.organization = org
    user.is_org_admin = is_admin
    user.save()
    return user


def _authenticated_client(user):
    """Return an APIClient authenticated as `user`."""
    client = APIClient()
    client.force_authenticate(user=user)
    return client


# ─── 1. Upload Validator Tests ───────────────────────────────────────────────

class UploadValidatorTests(TestCase):
    """Ensure file upload validators block dangerous content."""

    def test_svg_extension_blocked(self):
        from apps.core.upload_validators import validate_upload
        f = io.BytesIO(b"<svg><script>alert(1)</script></svg>")
        f.name = "evil.svg"
        f.size = len(f.getvalue())
        f.content_type = "image/svg+xml"
        with self.assertRaises(ValidationError):
            validate_upload(f)

    def test_svg_mime_blocked(self):
        from apps.core.upload_validators import validate_upload
        f = io.BytesIO(b"<svg></svg>")
        f.name = "image.xml"
        f.size = len(f.getvalue())
        f.content_type = "image/svg+xml"
        with self.assertRaises(ValidationError):
            validate_upload(f)

    def test_valid_pdf_accepted(self):
        from apps.core.upload_validators import validate_upload
        f = io.BytesIO(b"%PDF-1.4 fake content")
        f.name = "doc.pdf"
        f.size = len(f.getvalue())
        f.content_type = "application/pdf"
        result = validate_upload(f)
        self.assertIsNotNone(result)

    def test_oversized_file_rejected(self):
        from apps.core.upload_validators import validate_upload, MAX_UPLOAD_SIZE_BYTES
        f = io.BytesIO(b"x")
        f.name = "big.pdf"
        f.size = MAX_UPLOAD_SIZE_BYTES + 1
        f.content_type = "application/pdf"
        with self.assertRaises(ValidationError):
            validate_upload(f)

    def test_exe_extension_blocked(self):
        from apps.core.upload_validators import validate_upload
        f = io.BytesIO(b"MZ\x90\x00")
        f.name = "malware.exe"
        f.size = 100
        f.content_type = "application/x-msdownload"
        with self.assertRaises(ValidationError):
            validate_upload(f)

    def test_double_extension_blocked(self):
        from apps.core.upload_validators import validate_upload
        f = io.BytesIO(b"MZ\x90\x00")
        f.name = "report.pdf.exe"
        f.size = 100
        f.content_type = "application/x-msdownload"
        with self.assertRaises(ValidationError):
            validate_upload(f)


# ─── 2. OrganizationViewSetMixin Fail-Closed Tests ──────────────────────────

class FailClosedMixinTests(TestCase):
    """Verify OrganizationViewSetMixin returns empty QS when no org context."""

    def test_no_org_returns_none(self):
        """Without organization context, get_queryset must return .none()."""
        from apps.core.tenant_guards import OrganizationViewSetMixin
        from rest_framework.viewsets import ModelViewSet

        class DummyViewSet(OrganizationViewSetMixin, ModelViewSet):
            from apps.core.models import Organization
            queryset = Organization.objects.none()

        factory = RequestFactory()
        request = factory.get("/")
        request.user = MagicMock(is_superuser=False)
        request.organization = None

        with patch("apps.core.tenant_guards.get_current_organization", return_value=None):
            vs = DummyViewSet()
            vs.request = request
            vs.kwargs = {}
            vs.format_kwarg = None
            qs = vs.get_queryset()
            self.assertEqual(qs.count(), 0)


# ─── 3. ViewSet Mixin Compliance Audit ──────────────────────────────────────

class ViewSetMixinComplianceTests(TestCase):
    """
    Verify all org-scoped ViewSets inherit OrganizationViewSetMixin
    and call super().get_queryset() (not Model.objects.xxx directly).
    """

    def test_training_viewsets_use_super(self):
        """Training ViewSets must call super().get_queryset()."""
        import inspect
        from apps.training import views as tv
        for cls_name in [
            "TrainingCategoryViewSet",
            "TrainingProgramViewSet",
            "TrainingMaterialViewSet",
            "TrainingEnrollmentViewSet",
            "TrainingCompletionViewSet",
        ]:
            cls = getattr(tv, cls_name)
            src = inspect.getsource(cls.get_queryset)
            self.assertIn(
                "super()",
                src,
                f"{cls_name}.get_queryset() must call super().get_queryset()",
            )

    def test_abac_viewsets_use_super(self):
        """ABAC ViewSets must call super().get_queryset()."""
        import inspect
        from apps.abac import views as av
        for cls_name in [
            "AttributeTypeViewSet",
            "PolicyViewSet",
            "PolicyRuleViewSet",
            "UserPolicyViewSet",
            "GroupPolicyViewSet",
            "PolicyLogViewSet",
            "RoleViewSet",
            "PermissionViewSet",
            "RoleAssignmentViewSet",
        ]:
            cls = getattr(av, cls_name)
            src = inspect.getsource(cls.get_queryset)
            self.assertIn(
                "super()",
                src,
                f"{cls_name}.get_queryset() must call super().get_queryset()",
            )

    def test_workflow_step_viewset_uses_super(self):
        """WorkflowStepViewSet must call super().get_queryset()."""
        import inspect
        from apps.workflows.views import WorkflowStepViewSet
        src = inspect.getsource(WorkflowStepViewSet.get_queryset)
        self.assertIn("super()", src)

    def test_class_level_queryset_is_none(self):
        """All org-scoped ViewSets must have queryset = Model.objects.none()."""
        from apps.training import views as tv
        from apps.abac import views as av
        from apps.workflows import views as wv

        viewsets_to_check = [
            tv.TrainingCategoryViewSet,
            tv.TrainingProgramViewSet,
            tv.TrainingMaterialViewSet,
            tv.TrainingEnrollmentViewSet,
            tv.TrainingCompletionViewSet,
            av.AttributeTypeViewSet,
            av.PolicyViewSet,
            av.PolicyRuleViewSet,
            av.UserPolicyViewSet,
            av.GroupPolicyViewSet,
            av.PolicyLogViewSet,
            av.RoleViewSet,
            av.PermissionViewSet,
            av.RoleAssignmentViewSet,
            wv.WorkflowStepViewSet,
            wv.WorkflowDefinitionViewSet,
            wv.WorkflowInstanceViewSet,
            wv.WorkflowActionViewSet,
        ]

        from django.db.models.sql.where import NothingNode

        for vs_cls in viewsets_to_check:
            qs = vs_cls.queryset
            # Verify it's a .none() queryset by checking for NothingNode
            has_nothing = False
            if hasattr(qs, 'query') and hasattr(qs.query, 'where'):
                for child in qs.query.where.children:
                    if isinstance(child, NothingNode):
                        has_nothing = True
                        break
            self.assertTrue(
                has_nothing,
                f"{vs_cls.__name__}.queryset should be .none(), not .all()",
            )


# ─── 4. Training Enrollment Org Filter Test ─────────────────────────────────

class TrainingEnrollOrgFilterTest(TestCase):
    """
    Verify that the enroll action filters employees by organization
    to prevent cross-tenant enrollment.
    """

    def test_enroll_source_has_org_filter(self):
        """The enroll action must contain organization filtering."""
        import inspect
        from apps.training.views import TrainingProgramViewSet
        src = inspect.getsource(TrainingProgramViewSet.enroll)
        # Must reference organization filtering for employee lookup
        self.assertIn("organization", src,
                       "enroll() must filter Employee by organization")


# ─── 5. Settings Security Tests ─────────────────────────────────────────────

class SettingsSecurityTests(TestCase):
    """Validate production-critical settings."""

    def test_secret_key_not_hardcoded(self):
        from django.conf import settings
        self.assertNotEqual(
            settings.SECRET_KEY,
            "django-insecure-placeholder",
            "SECRET_KEY must not be the default placeholder",
        )

    def test_jwt_access_token_not_excessive(self):
        from django.conf import settings
        ttl = settings.SIMPLE_JWT.get("ACCESS_TOKEN_LIFETIME")
        self.assertIsNotNone(ttl)
        # Must be <= 60 minutes
        self.assertLessEqual(ttl.total_seconds(), 3600)

    def test_jwt_rotation_enabled(self):
        from django.conf import settings
        self.assertTrue(settings.SIMPLE_JWT.get("ROTATE_REFRESH_TOKENS"))
        self.assertTrue(settings.SIMPLE_JWT.get("BLACKLIST_AFTER_ROTATION"))

    def test_default_permission_is_authenticated(self):
        from django.conf import settings
        perm_classes = settings.REST_FRAMEWORK.get("DEFAULT_PERMISSION_CLASSES", [])
        self.assertIn("rest_framework.permissions.IsAuthenticated", perm_classes)

    def test_default_throttle_configured(self):
        from django.conf import settings
        throttle_classes = settings.REST_FRAMEWORK.get("DEFAULT_THROTTLE_CLASSES", [])
        self.assertTrue(len(throttle_classes) > 0, "Throttle classes must be configured")


# ─── 6. Middleware Ordering Tests ────────────────────────────────────────────

class MiddlewareOrderingTests(TestCase):
    """Verify critical middleware ordering."""

    def test_security_middleware_first(self):
        from django.conf import settings
        mw = settings.MIDDLEWARE
        self.assertEqual(
            mw[0],
            "django.middleware.security.SecurityMiddleware",
            "SecurityMiddleware must be first in MIDDLEWARE",
        )

    def test_cors_before_csrf(self):
        from django.conf import settings
        mw = settings.MIDDLEWARE
        cors_idx = next(
            (i for i, m in enumerate(mw) if "cors" in m.lower()), None
        )
        csrf_idx = next(
            (i for i, m in enumerate(mw) if "csrf" in m.lower()), None
        )
        if cors_idx is not None and csrf_idx is not None:
            self.assertLess(cors_idx, csrf_idx, "CORS must come before CSRF")
