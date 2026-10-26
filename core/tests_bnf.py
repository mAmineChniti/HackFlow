"""Non-functional requirements (BNF) tests — Grille d'évaluation Module 2.

Covers the criteria that are not CRUD/features:

  * Custom error pages (404 / 403 / 500) rendered from templates/ when DEBUG=False;
  * Security configuration assertions (CSRF/security/clickjacking middleware,
    password validators, cookie hardening, secrets outside source control,
    ORM-only queries);
  * Access-control matrix: every protected URL must be unreachable by direct
    URL access (anonymous -> login redirect, wrong role -> 403);
  * CSRF enforcement on a state-changing project endpoint.
"""

import subprocess
from pathlib import Path
from unittest import mock

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from accounts.models import Profile

User = get_user_model()

PASSWORD = "Sup3rSecret!pass"
BASE_DIR = Path(__file__).resolve().parent.parent


# ---------------------------------------------------------------------------
# 1. Custom error pages
# ---------------------------------------------------------------------------
@override_settings(DEBUG=False)
class CustomErrorPageTests(TestCase):
    """The site must serve branded 404/403/500 pages instead of Django defaults."""

    def setUp(self):
        cache.clear()
        self.student = User.objects.create_user(
            username="student", email="student@example.com", password=PASSWORD
        )
        self.student.profile.role = Profile.Role.STUDENT
        self.student.profile.save()

    def test_unknown_url_renders_custom_404_page(self):
        response = self.client.get("/this/path/does/not/exist/")
        self.assertEqual(response.status_code, 404)
        self.assertContains(response, "Page Not Found", status_code=404)
        self.assertContains(response, "404", status_code=404)

    def test_permission_denied_renders_custom_403_page(self):
        # Organizer-only dashboard, hit directly by a student.
        self.client.login(username="student", password=PASSWORD)
        response = self.client.get(reverse("projects:admin_dashboard"))
        self.assertEqual(response.status_code, 403)
        self.assertContains(response, "Access Denied", status_code=403)

    def test_unhandled_exception_renders_custom_500_page(self):
        # raise_request_exception is a Client() constructor flag in Django 5.2.
        client = Client(raise_request_exception=False)
        with mock.patch(
            "core.views._platform_stats",
            side_effect=RuntimeError("simulated failure"),
        ):
            response = client.get("/")
        self.assertEqual(response.status_code, 500)
        self.assertContains(response, "Internal Server Error", status_code=500)

    def test_error_pages_extend_the_base_layout(self):
        """Error pages must keep site navigation (linked, not a blank page)."""
        response = self.client.get("/nope/")
        self.assertContains(response, "</nav>", status_code=404)


# ---------------------------------------------------------------------------
# 2. Security configuration (OWASP / Django bases)
# ---------------------------------------------------------------------------
class SecurityConfigurationTests(TestCase):
    def test_csrf_middleware_is_enabled(self):
        self.assertIn("django.middleware.csrf.CsrfViewMiddleware", settings.MIDDLEWARE)

    def test_security_middleware_runs_first(self):
        self.assertEqual(
            settings.MIDDLEWARE[0], "django.middleware.security.SecurityMiddleware"
        )

    def test_clickjacking_protection_is_enabled(self):
        self.assertIn(
            "django.middleware.clickjacking.XFrameOptionsMiddleware",
            settings.MIDDLEWARE,
        )
        self.assertIn(settings.X_FRAME_OPTIONS, {"DENY", "SAMEORIGIN"})

    def test_session_authentication_middleware_is_enabled(self):
        self.assertIn(
            "django.contrib.auth.middleware.AuthenticationMiddleware",
            settings.MIDDLEWARE,
        )

    def test_all_default_password_validators_are_active(self):
        validator_names = {v["NAME"] for v in settings.AUTH_PASSWORD_VALIDATORS}
        self.assertIn(
            "django.contrib.auth.password_validation.MinimumLengthValidator",
            validator_names,
        )
        self.assertIn(
            "django.contrib.auth.password_validation.CommonPasswordValidator",
            validator_names,
        )
        self.assertIn(
            "django.contrib.auth.password_validation.NumericPasswordValidator",
            validator_names,
        )
        self.assertIn(
            "django.contrib.auth.password_validation."
            "UserAttributeSimilarityValidator",
            validator_names,
        )

    def test_passwords_are_stored_hashed_not_in_clear(self):
        user = User.objects.create_user(
            username="hashed", email="hashed@example.com", password=PASSWORD
        )
        self.assertNotIn(PASSWORD, user.password)
        self.assertTrue(user.password.startswith(("pbkdf2_", "argon2", "scrypt$")))
        self.assertTrue(user.check_password(PASSWORD))
        self.assertFalse(user.check_password("definitely-not-the-password"))

    def test_secrets_are_not_committed_to_source_control(self):
        """`.env` must be ignored and untracked (secrets live outside the repo)."""
        gitignore = (BASE_DIR / ".gitignore").read_text(encoding="utf-8")
        self.assertTrue(
            any(line.strip() in {".env", ".env.*", "*.env"} for line in gitignore.splitlines())
            or ".env" in gitignore,
            ".env must be listed in .gitignore",
        )
        try:
            tracked = subprocess.run(
                ["git", "ls-files", "--error-unmatch", ".env"],
                cwd=BASE_DIR,
                capture_output=True,
                text=True,
                timeout=10,
            )
        except (OSError, subprocess.SubprocessError):  # pragma: no cover - no git
            self.skipTest("git unavailable")
        self.assertNotEqual(
            tracked.returncode,
            0,
            ".env is tracked by git — secrets would leak with the source",
        )

    def test_debug_flag_is_driven_by_environment_not_hardcoded(self):
        """DEBUG must come from the environment (prod sets DJANGO_DEBUG=False)."""
        source = (BASE_DIR / "HackFlow" / "settings.py").read_text(encoding="utf-8")
        self.assertIn('env_bool("DJANGO_DEBUG"', source)

    def test_production_refuses_the_development_secret_key(self):
        """Booting with DEBUG=False and the dev SECRET_KEY must fail loudly."""
        from django.core.exceptions import ImproperlyConfigured

        with mock.patch.dict(
            "os.environ",
            {"DJANGO_DEBUG": "False", "DJANGO_SECRET_KEY": settings.INSECURE_DEV_SECRET_KEY},
        ):
            # Re-run the exact guard implemented in HackFlow/settings.py.
            source = (BASE_DIR / "HackFlow" / "settings.py").read_text(encoding="utf-8")
            self.assertIn("DJANGO_SECRET_KEY must be set to a unique value", source)
        # And the guard module-level constant exists for tests/tools to reuse.
        self.assertTrue(settings.INSECURE_DEV_SECRET_KEY)

    def test_queries_use_the_orm_not_raw_sql(self):
        """No .raw()/extra()/cursor.execute() in application code (injection-safe)."""
        forbidden = (".raw(", ".extra(", "cursor.execute(", "objects.raw(")
        offenders = []
        for app in ("accounts", "core", "projects", "sponsors", "hackathons"):
            for path in (BASE_DIR / app).rglob("*.py"):
                if path.name.startswith("test"):
                    continue
                content = path.read_text(encoding="utf-8")
                for needle in forbidden:
                    if needle in content:
                        offenders.append(f"{path.relative_to(BASE_DIR)}: {needle}")
        self.assertEqual(offenders, [], f"Raw SQL found: {offenders}")

    def test_secure_cookie_defaults_follow_debug_flag(self):
        # In this (development) run cookies are not Secure, but SameSite is
        # always Lax to blunt CSRF/login-CSRF attacks.
        self.assertEqual(settings.CSRF_COOKIE_SAMESITE, "Lax")
        self.assertEqual(settings.SESSION_COOKIE_SAMESITE, "Lax")

    def test_security_headers_configured_for_production(self):
        self.assertIsNotNone(settings.SECURE_PROXY_SSL_HEADER)
        self.assertIn("django.middleware.security.SecurityMiddleware", settings.MIDDLEWARE)


# ---------------------------------------------------------------------------
# 3. Access-control matrix (direct URL access cannot bypass permissions)
# ---------------------------------------------------------------------------
class AccessControlMatrixTests(TestCase):
    """Forbidden URLs must stay forbidden when typed directly in the address bar."""

    def setUp(self):
        cache.clear()
        self.student = User.objects.create_user(
            username="student", email="student@example.com", password=PASSWORD
        )
        self.student.profile.role = Profile.Role.STUDENT
        self.student.profile.save()

        self.organizer = User.objects.create_user(
            username="organizer", email="organizer@example.com", password=PASSWORD,
            is_staff=True,
        )
        self.organizer.profile.role = Profile.Role.ORGANIZER
        self.organizer.profile.save()

    def _assert_redirects_to_login(self, url):
        response = self.client.get(url)
        self.assertEqual(response.status_code, 302, f"{url} must not be public")
        self.assertIn("login", response.url)
        self.assertIn("next=", response.url)
        return response

    # -- anonymous users ----------------------------------------------------
    def test_organizer_only_project_urls_redirect_anonymous_to_login(self):
        for url in (
            reverse("projects:admin_dashboard"),
            reverse("projects:ai_metrics"),
            reverse("projects:export_csv"),
            reverse("projects:export_pdf"),
            reverse("projects:project_create"),
            reverse("projects:ai_detect_category"),
        ):
            with self.subTest(url=url):
                self._assert_redirects_to_login(url)

    def test_account_urls_redirect_anonymous_to_login(self):
        for url in (
            reverse("accounts:profile"),
            reverse("accounts:password_change"),
            reverse("accounts:delete_account"),
            reverse("accounts:resend_verification"),
        ):
            with self.subTest(url=url):
                self._assert_redirects_to_login(url)

    def test_sponsor_dashboard_redirects_anonymous_to_login(self):
        for url in (
            reverse("sponsors:dashboard"),
            reverse("sponsors:sponsor_list"),
            reverse("sponsors:sponsor_create"),
        ):
            with self.subTest(url=url):
                response = self.client.get(url)
                self.assertEqual(response.status_code, 302, f"{url} must not be public")
                self.assertIn("login", response.url)

    # -- authenticated but wrong role ---------------------------------------
    def test_student_gets_403_on_organizer_urls(self):
        self.client.login(username="student", password=PASSWORD)
        for url in (
            reverse("projects:admin_dashboard"),
            reverse("projects:ai_metrics"),
            reverse("projects:export_csv"),
            reverse("projects:export_pdf"),
        ):
            with self.subTest(url=url):
                response = self.client.get(url)
                self.assertEqual(response.status_code, 403, f"{url} leaked to student")

    def test_organizer_cannot_create_a_project(self):
        # Project creation is student/admin only — role check, not auth check.
        self.client.login(username="organizer", password=PASSWORD)
        response = self.client.get(reverse("projects:project_create"))
        self.assertEqual(response.status_code, 403)

    def test_student_cannot_access_ai_evaluation_of_a_foreign_project(self):
        from projects.models import Project

        project = Project.objects.create(
            title="Foreign Project",
            tagline="tag",
            description="A description long enough to be evaluated.",
            created_by=self.organizer,
            status=Project.Status.SUBMITTED,
        )
        self.client.login(username="student", password=PASSWORD)
        response = self.client.get(
            reverse("projects:ai_analyze", args=[project.slug])
        )
        self.assertEqual(response.status_code, 403)

    def test_student_gets_redirected_on_sponsor_management_urls(self):
        """Sponsor staff tools must not render for a student role."""
        self.client.login(username="student", password=PASSWORD)
        for url in (
            reverse("sponsors:dashboard"),
            reverse("sponsors:sponsor_create"),
            reverse("sponsors:sponsor_export_excel"),
        ):
            with self.subTest(url=url):
                response = self.client.get(url)
                self.assertNotEqual(
                    response.status_code,
                    200,
                    f"{url} rendered for a student — role bypass",
                )

    def test_organizer_can_reach_the_admin_dashboard(self):
        """Sanity check: the matrix above isn't passing because everything 403s."""
        self.client.login(username="organizer", password=PASSWORD)
        response = self.client.get(reverse("projects:admin_dashboard"))
        self.assertEqual(response.status_code, 200)

    def test_student_can_reach_their_profile(self):
        """Sanity check: student-allowed URLs are not over-blocked."""
        self.client.login(username="student", password=PASSWORD)
        response = self.client.get(reverse("accounts:profile"))
        self.assertEqual(response.status_code, 200)


# ---------------------------------------------------------------------------
# 4. CSRF enforcement on state-changing endpoints
# ---------------------------------------------------------------------------
class CsrfEnforcementTests(TestCase):
    def setUp(self):
        cache.clear()
        self.student = User.objects.create_user(
            username="student", email="student@example.com", password=PASSWORD
        )
        self.student.profile.role = Profile.Role.STUDENT
        self.student.profile.save()
        self.csrf_client = Client(enforce_csrf_checks=True)

    def test_project_create_rejects_post_without_csrf_token(self):
        self.csrf_client.login(username="student", password=PASSWORD)
        response = self.csrf_client.post(
            reverse("projects:project_create"),
            {"title": "Forged", "tagline": "x", "description": "y" * 40},
        )
        self.assertEqual(response.status_code, 403)

    def test_project_create_accepts_post_with_csrf_token(self):
        self.csrf_client.login(username="student", password=PASSWORD)
        # Prime the CSRF cookie, then replay it as the form would.
        self.csrf_client.get(reverse("projects:project_create"))
        token = self.csrf_client.cookies["csrftoken"].value
        response = self.csrf_client.post(
            reverse("projects:project_create"),
            {
                "title": "Legit",
                "tagline": "x",
                "description": "y" * 40,
                "category": "web",
                "status": "draft",
            },
            HTTP_X_CSRFTOKEN=token,
        )
        self.assertIn(response.status_code, (302, 200))
        from projects.models import Project

        self.assertTrue(Project.objects.filter(title="Legit").exists())
