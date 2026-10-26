"""Tests that the landing page is data-driven rather than hardcoded.

Everything here fails if the home view goes back to returning literal demo
lists: each assertion creates a record and checks it reaches the HTML.
"""

from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from hackathons.models import Hackathon
from projects.models import Project
from sponsors.models import Sponsor, Sponsorship, StatusChoices, TierChoices

User = get_user_model()


class HomePageDataTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="builder", email="builder@example.com", password="pwd"
        )

    def _make_project(self, title, **kwargs):
        defaults = {
            "tagline": "A tagline",
            "description": "A description",
            "created_by": self.user,
            "status": Project.Status.SUBMITTED,
        }
        defaults.update(kwargs)
        return Project.objects.create(title=title, **defaults)

    def _make_event(self, name, start_offset, end_offset, theme="Theme"):
        now = timezone.now()
        return Hackathon.objects.create(
            title=name,
            tagline=theme,
            description="A test hackathon.",
            category="General",
            registration_start=now - timedelta(days=1),
            registration_deadline=now + timedelta(days=max(start_offset - 1, 0)),
            start_date=now + timedelta(days=start_offset),
            end_date=now + timedelta(days=end_offset),
            organizer=self.user,
            status=Hackathon.Status.REGISTRATION_OPEN,
            is_published=True,
        )

    # ------------------------------------------------------------------
    # Events
    # ------------------------------------------------------------------
    def test_events_section_renders_database_rows(self):
        self._make_event("Alpha Hack", 5, 7, theme="Robotics")

        response = self.client.get(reverse("core:home"))

        self.assertContains(response, "Alpha Hack")
        self.assertContains(response, "Robotics")
        self.assertNotContains(response, "No hackathons announced yet")

    def test_events_section_shows_empty_state_without_rows(self):
        response = self.client.get(reverse("core:home"))

        self.assertContains(response, "No hackathons announced yet")

    def test_deleted_event_disappears_from_the_page(self):
        event = self._make_event("Temporary Event", 3, 5)
        self.assertContains(self.client.get(reverse("core:home")), "Temporary Event")

        event.delete()

        self.assertNotContains(self.client.get(reverse("core:home")), "Temporary Event")

    def test_event_status_is_derived_from_dates(self):
        self._make_event("Future Event", 10, 12)
        self._make_event("Running Event", -1, 1)
        self._make_event("Past Event", -20, -18)

        content = self.client.get(reverse("core:home")).content.decode()

        self.assertIn("Future Event", content)
        self.assertIn("Upcoming", content)
        self.assertIn("Live now", content)
        self.assertIn("Completed", content)

    def test_same_month_dates_are_formatted_as_a_range(self):
        now = timezone.localtime()
        year = now.year if now.month <= 11 else now.year + 1
        start = now.replace(year=year, month=11, day=14, hour=9, minute=0, second=0, microsecond=0)
        Hackathon.objects.create(
            title="Range Event",
            tagline="Date formatting",
            description="A test hackathon.",
            category="General",
            registration_start=start - timedelta(days=1),
            registration_deadline=start - timedelta(hours=1),
            start_date=start,
            end_date=start + timedelta(days=2),
            organizer=self.user,
            status=Hackathon.Status.REGISTRATION_OPEN,
            is_published=True,
        )

        content = self.client.get(reverse("core:home")).content.decode()

        self.assertIn("14 – 16 Nov", content)

    def test_event_with_blank_optional_details_uses_fallbacks(self):
        self._make_event("Bare Event", 5, 7, theme="")

        response = self.client.get(reverse("core:home"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Bare Event")
        self.assertContains(response, "Details to be announced")
        self.assertContains(response, "Prize TBA")

    # ------------------------------------------------------------------
    # Leaderboard
    # ------------------------------------------------------------------
    def test_leaderboard_uses_scored_projects(self):
        self._make_project("Scored Project", status=Project.Status.ACCEPTED, score=9)

        response = self.client.get(reverse("core:home"))

        self.assertContains(response, "Scored Project")
        self.assertContains(response, "9/10")
        self.assertNotContains(response, "No projects have been scored yet")

    def test_leaderboard_ignores_unscored_projects(self):
        self._make_project("Unscored Project", score=None)

        response = self.client.get(reverse("core:home"))

        # It may still appear under "recent submissions", but never as a rank.
        self.assertEqual(response.context["leaderboard"], [])
        self.assertContains(response, "No projects have been scored yet")

    def test_leaderboard_excludes_drafts(self):
        self._make_project("Draft Scored Project", status=Project.Status.DRAFT, score=10)

        response = self.client.get(reverse("core:home"))

        self.assertNotContains(response, "Draft Scored Project")

    def test_leaderboard_orders_by_score(self):
        self._make_project("Lower Scored", score=4, status=Project.Status.ACCEPTED)
        self._make_project("Higher Scored", score=8, status=Project.Status.ACCEPTED)

        content = self.client.get(reverse("core:home")).content.decode()

        self.assertLess(content.index("Higher Scored"), content.index("Lower Scored"))

    # ------------------------------------------------------------------
    # Recent submissions (hero tabs)
    # ------------------------------------------------------------------
    def test_recent_submissions_show_real_projects(self):
        self._make_project("Submitted Entry", status=Project.Status.SUBMITTED)
        self._make_project("Draft Entry", status=Project.Status.DRAFT)

        response = self.client.get(reverse("core:home"))

        self.assertContains(response, "Submitted Entry")
        self.assertNotContains(response, "Draft Entry")

    # ------------------------------------------------------------------
    # Platform counters
    # ------------------------------------------------------------------
    def test_counters_reflect_the_database(self):
        User.objects.create_user(username="second", email="second@example.com")
        self._make_project("Counted Project")
        self._make_event("Counted Event", 1, 2)
        sponsor = Sponsor.objects.create(name="Counted Sponsor")
        Sponsorship.objects.create(
            sponsor=sponsor,
            hackathon=Hackathon.objects.get(title="Counted Event"),
            tier=TierChoices.GOLD,
            amount=Decimal("1500.000"),
            status=StatusChoices.CONFIRME,
        )

        response = self.client.get(reverse("core:home"))

        self.assertEqual(response.context["stats"]["builders"], 2)
        self.assertEqual(response.context["stats"]["projects"], 1)
        self.assertEqual(response.context["stats"]["events"], 1)
        self.assertEqual(response.context["stats"]["confirmed_sponsorships"], 1)
        self.assertEqual(response.context["stats"]["funding"], Decimal("1500.000"))

    def test_old_fake_counters_are_gone(self):
        content = self.client.get(reverse("core:home")).content.decode()

        for fake in ("120K+", "850+", "$4.2M", "2,418", "$50,000"):
            self.assertNotIn(fake, content)

    # ------------------------------------------------------------------
    # Robustness
    # ------------------------------------------------------------------
    def test_page_renders_with_an_empty_database(self):
        response = self.client.get(reverse("core:home"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "No hackathons announced yet")
        self.assertContains(response, "No projects have been scored yet")

    def test_featured_event_prefers_the_next_event(self):
        self._make_event("Past Featured", -30, -28)
        self._make_event("Next Featured", 4, 6)

        response = self.client.get(reverse("core:home"))

        self.assertEqual(response.context["featured_event"]["name"], "Next Featured")

    def test_featured_event_picks_the_soonest_of_several_upcoming(self):
        self._make_event("Later Event", 40, 42)
        self._make_event("Sooner Event", 5, 7)
        self._make_event("Latest Event", 90, 92)

        response = self.client.get(reverse("core:home"))

        self.assertEqual(response.context["featured_event"]["name"], "Sooner Event")

    def test_featured_event_prefers_a_running_event_over_upcoming(self):
        self._make_event("Upcoming Event", 6, 8)
        self._make_event("Running Event", -1, 1)

        response = self.client.get(reverse("core:home"))

        self.assertEqual(response.context["featured_event"]["name"], "Running Event")

    def test_featured_event_falls_back_to_latest_when_all_are_past(self):
        self._make_event("Older Event", -40, -38)
        self._make_event("Newest Past Event", -10, -8)

        response = self.client.get(reverse("core:home"))

        self.assertEqual(response.context["featured_event"]["name"], "Newest Past Event")
