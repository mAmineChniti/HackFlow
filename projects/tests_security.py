"""Regression tests for project security and correctness fixes.

Covers:
  * AI endpoints: POST-only category detection, per-user throttling, and no
    raw exception text in responses;
  * CSV export: spreadsheet formula injection is neutralised;
  * PDF export: the reportlab dependency is declared and the view works;
  * admin bulk decisions write to the immutable project history;
  * race-safe automatic slugs;
  * AI panel templates render model output as text, not HTML.
"""

from pathlib import Path
from unittest import mock

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from accounts.models import Profile
from projects.models import HistoriqueProjet, Project

User = get_user_model()

PASSWORD = "Sup3rSecret!pass"


class BaseProjectTestCase(TestCase):
    def setUp(self):
        cache.clear()

        self.student = User.objects.create_user(
            username="student", email="student@example.com", password=PASSWORD
        )
        self.student.profile.role = Profile.Role.STUDENT
        self.student.profile.save()

        self.organizer = User.objects.create_user(
            username="organizer",
            email="organizer@example.com",
            password=PASSWORD,
            is_staff=True,
        )
        self.organizer.profile.role = Profile.Role.ORGANIZER
        self.organizer.profile.save()

        self.admin = User.objects.create_superuser(
            username="root", email="root@example.com", password=PASSWORD
        )
        self.admin.profile.role = Profile.Role.ADMIN
        self.admin.profile.save()

        self.project = Project.objects.create(
            title="Probe Project",
            tagline="A tagline",
            description="A description long enough to be evaluated.",
            created_by=self.student,
            status=Project.Status.SUBMITTED,
        )


class AiEndpointTests(BaseProjectTestCase):
    @override_settings(AI_RATE_LIMIT_MAX=1, AI_RATE_LIMIT_WINDOW=60)
    def test_ai_analyze_is_throttled_per_user(self):
        client = Client()
        client.force_login(self.student)
        url = reverse("projects:ai_analyze", args=[self.project.slug])

        first = client.post(url)
        second = client.post(url)

        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 429)
        self.assertIn("error", second.json())

    @override_settings(AI_RATE_LIMIT_MAX=0)
    def test_ai_throttle_can_be_disabled(self):
        client = Client()
        client.force_login(self.student)
        url = reverse("projects:ai_analyze", args=[self.project.slug])

        for _ in range(3):
            self.assertEqual(client.post(url).status_code, 200)

    def test_ai_detect_category_rejects_get(self):
        client = Client()
        client.force_login(self.student)

        response = client.get(
            reverse("projects:ai_detect_category"),
            {"title": "django saas", "description": "web platform"},
        )

        self.assertEqual(response.status_code, 405)

    def test_ai_detect_category_accepts_post(self):
        client = Client()
        client.force_login(self.student)

        response = client.post(
            reverse("projects:ai_detect_category"),
            {"title": "django saas platform", "description": "web dashboard"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["category"], "web")

    @override_settings(AI_RATE_LIMIT_MAX=1)
    def test_ai_detect_category_is_throttled(self):
        client = Client()
        client.force_login(self.student)
        url = reverse("projects:ai_detect_category")

        first = client.post(url, {"title": "web app", "description": "django"})
        second = client.post(url, {"title": "web app", "description": "django"})

        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 429)

    def test_ai_analyze_does_not_leak_exception_text(self):
        client = Client()
        client.force_login(self.student)
        url = reverse("projects:ai_analyze", args=[self.project.slug])

        response = client.post(url)
        payload = response.json()

        self.assertEqual(response.status_code, 200)
        self.assertNotIn("error", payload)
        self.assertIn("source_key", payload)
        self.assertIn(payload["source_key"], {"remote", "heuristic"})

    def test_ai_analyze_cached_response_is_marked_as_cache(self):
        client = Client()
        client.force_login(self.student)
        url = reverse("projects:ai_analyze", args=[self.project.slug])

        client.post(url)
        payload = client.post(url).json()

        self.assertEqual(payload["source_key"], "cache")


class ExportTests(BaseProjectTestCase):
    def setUp(self):
        super().setUp()
        self.client.force_login(self.organizer)

    def test_csv_export_neutralises_formula_injection(self):
        Project.objects.create(
            title="=HYPERLINK(\"http://evil.example\")",
            tagline="+1234567890",
            description="payload",
            created_by=self.student,
            status=Project.Status.ACCEPTED,
        )

        response = self.client.get(reverse("projects:export_csv"))
        body = response.content.decode("utf-8")

        self.assertEqual(response.status_code, 200)
        self.assertIn("'=HYPERLINK", body)
        self.assertIn("'+1234567890", body)
        # The dangerous cell must not appear unescaped at the start of a field.
        self.assertNotIn(";=HYPERLINK", body)

    def test_pdf_export_returns_a_pdf(self):
        response = self.client.get(reverse("projects:export_pdf"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/pdf")
        self.assertTrue(bytes(response.content).startswith(b"%PDF"))

    def test_pdf_export_requires_organizer(self):
        student_client = Client()
        student_client.force_login(self.student)

        self.assertEqual(
            student_client.get(reverse("projects:export_pdf")).status_code, 403
        )


class AdminAuditTrailTests(BaseProjectTestCase):
    def test_bulk_accept_writes_history_entry(self):
        client = Client()
        client.force_login(self.admin)

        response = client.post(
            "/admin/projects/project/",
            {
                "action": "accept_selected_projects",
                "_selected_action": [str(self.project.pk)],
                "index": "0",
            },
        )

        self.assertEqual(response.status_code, 302)
        self.project.refresh_from_db()
        self.assertEqual(self.project.status, Project.Status.ACCEPTED)
        self.assertTrue(
            HistoriqueProjet.objects.filter(
                project=self.project, action=HistoriqueProjet.Action.ACCEPTED
            ).exists()
        )

    def test_bulk_reject_writes_history_entry_with_reason(self):
        client = Client()
        client.force_login(self.admin)

        client.post(
            "/admin/projects/project/",
            {
                "action": "reject_selected_projects",
                "_selected_action": [str(self.project.pk)],
                "index": "0",
            },
        )

        entry = HistoriqueProjet.objects.get(
            project=self.project, action=HistoriqueProjet.Action.REJECTED
        )
        self.assertTrue(entry.commentaire)

    def test_bulk_accept_skips_projects_that_are_not_reviewable(self):
        draft = Project.objects.create(
            title="Draft Project",
            tagline="t",
            description="d",
            created_by=self.student,
            status=Project.Status.DRAFT,
        )
        client = Client()
        client.force_login(self.admin)

        client.post(
            "/admin/projects/project/",
            {
                "action": "accept_selected_projects",
                "_selected_action": [str(draft.pk)],
                "index": "0",
            },
        )

        draft.refresh_from_db()
        self.assertEqual(draft.status, Project.Status.DRAFT)
        self.assertFalse(
            HistoriqueProjet.objects.filter(project=draft).exists()
        )


class SlugUniquenessTests(BaseProjectTestCase):
    def test_same_title_gets_distinct_slugs(self):
        first = Project.objects.create(
            title="Duplicate Title", tagline="t", description="d", created_by=self.student
        )
        second = Project.objects.create(
            title="Duplicate Title", tagline="t", description="d", created_by=self.student
        )

        self.assertNotEqual(first.slug, second.slug)
        self.assertEqual(first.slug, "duplicate-title")
        self.assertEqual(second.slug, "duplicate-title-1")

    def test_concurrent_slug_collision_retries_with_suffix(self):
        Project.objects.create(
            title="Race",
            tagline="t",
            description="d",
            created_by=self.student,
            slug="race",
        )

        real_filter = Project.objects.filter
        state = {"calls": 0}

        class AlwaysFree:
            def exclude(self, *args, **kwargs):
                return self

            def exists(self):
                return False

        def fake_filter(*args, **kwargs):
            state["calls"] += 1
            # Only the pre-check is faked: it reports the slug as free even
            # though a conflicting row already exists.
            if state["calls"] == 1:
                return AlwaysFree()
            return real_filter(*args, **kwargs)

        with mock.patch.object(Project.objects, "filter", side_effect=fake_filter):
            project = Project(
                title="Race", tagline="t", description="d", created_by=self.student
            )
            project.save()

        self.assertTrue(project.slug.startswith("race-"))
        self.assertNotEqual(project.slug, "race")
        self.assertEqual(Project.objects.filter(title="Race").count(), 2)


class AiTemplateRenderingTests(TestCase):
    def test_ai_panel_does_not_inject_model_output_as_html(self):
        template = (
            Path(__file__).resolve().parent.parent
            / "templates"
            / "projects"
            / "project_detail.html"
        ).read_text(encoding="utf-8")

        self.assertNotIn("li.innerHTML", template)
        self.assertNotIn("strengthsEl.innerHTML", template)

    def test_category_suggestion_does_not_inject_model_output_as_html(self):
        template = (
            Path(__file__).resolve().parent.parent
            / "templates"
            / "projects"
            / "project_form.html"
        ).read_text(encoding="utf-8")

        self.assertNotIn("${data.category_label}", template)
        self.assertNotIn("${data.reason", template)
