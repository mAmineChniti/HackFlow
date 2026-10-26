"""Unit coverage for the landing-page helpers and edge cases in ``core.views``."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone as dt_timezone
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TestCase
from django.urls import reverse
from django.utils import timezone

from core import views
from hackathons.models import Hackathon
from projects.models import Project

User = get_user_model()


def make_event(organizer, title, start_offset, end_offset, **overrides):
    now = timezone.now()
    values = {
        "title": title,
        "tagline": "Theme",
        "description": "A test event.",
        "category": "General",
        "registration_start": now - timedelta(days=5),
        "registration_deadline": now - timedelta(days=1),
        "start_date": now + timedelta(days=start_offset),
        "end_date": now + timedelta(days=end_offset),
        "organizer": organizer,
        "status": Hackathon.Status.REGISTRATION_OPEN,
        "is_published": True,
    }
    values.update(overrides)
    return Hackathon.objects.create(**values)


class DateHelperTests(SimpleTestCase):
    def test_event_local_date_handles_missing_aware_and_naive_values(self):
        self.assertIsNone(views._event_local_date(None))

        aware = timezone.make_aware(datetime(2026, 11, 14, 9, 30))
        self.assertEqual(views._event_local_date(aware), date(2026, 11, 14))

        naive = datetime(2026, 11, 15, 18, 0)
        self.assertEqual(views._event_local_date(naive), date(2026, 11, 15))

    def test_format_date_range_branches(self):
        start = date(2026, 11, 14)
        end = date(2026, 11, 16)

        self.assertEqual(views._format_date_range(None, None), "Dates to be announced")
        self.assertEqual(views._format_date_range(start, None), "From 14 Nov 2026")
        self.assertEqual(views._format_date_range(None, end), "Until 16 Nov 2026")
        self.assertEqual(views._format_date_range(start, start), "14 Nov 2026")
        self.assertEqual(views._format_date_range(start, end), "14 – 16 Nov 2026")
        self.assertEqual(
            views._format_date_range(date(2026, 11, 30), date(2026, 12, 2)),
            "30 Nov – 02 Dec 2026",
        )
        self.assertEqual(
            views._format_date_range(date(2026, 12, 31), date(2027, 1, 2)),
            "31 Dec 2026 – 02 Jan 2027",
        )

    def test_event_status_branches(self):
        today = date(2026, 11, 15)
        self.assertEqual(
            views._event_status(date(2026, 11, 1), date(2026, 11, 2), today), "Completed"
        )
        self.assertEqual(
            views._event_status(date(2026, 11, 20), date(2026, 11, 22), today), "Upcoming"
        )
        self.assertEqual(
            views._event_status(date(2026, 11, 14), date(2026, 11, 16), today), "Live now"
        )
        self.assertEqual(views._event_status(None, None, today), "Announced")

    def test_event_duration(self):
        self.assertIsNone(views._event_duration(None, date(2026, 11, 2)))
        self.assertIsNone(views._event_duration(date(2026, 11, 1), None))
        self.assertEqual(
            views._event_duration(date(2026, 11, 1), date(2026, 11, 3)), 3
        )

    def test_initials(self):
        self.assertEqual(views._initials(""), "??")
        self.assertEqual(views._initials("TeamSync"), "TE")
        self.assertEqual(views._initials("Eco Route"), "ER")


class FeaturedEventTests(SimpleTestCase):
    class Event:
        def __init__(self, name, start=None, end=None):
            self.name = name
            self.start_date = start
            self.end_date = end

    def test_no_events_returns_none(self):
        self.assertIsNone(views._featured_event([], date(2026, 11, 15)))

    def test_prefers_ongoing_then_upcoming_then_finished(self):
        today = date(2026, 11, 15)
        ongoing = self.Event(
            "Ongoing",
            timezone.make_aware(datetime(2026, 11, 14)),
            timezone.make_aware(datetime(2026, 11, 16)),
        )
        upcoming = self.Event(
            "Upcoming",
            timezone.make_aware(datetime(2026, 11, 20)),
            timezone.make_aware(datetime(2026, 11, 22)),
        )
        finished = self.Event(
            "Finished",
            timezone.make_aware(datetime(2026, 11, 1)),
            timezone.make_aware(datetime(2026, 11, 2)),
        )

        self.assertEqual(views._featured_event([upcoming, ongoing], today), ongoing)
        self.assertEqual(views._featured_event([finished, upcoming], today), upcoming)
        self.assertEqual(views._featured_event([finished], today), finished)

    def test_undated_events_fall_back_to_first_entry(self):
        undated = self.Event("Undated")
        self.assertEqual(views._featured_event([undated], date(2026, 11, 15)), undated)


class PlatformStatsTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="stats-builder", password="pwd")

    def test_stats_count_only_visible_records(self):
        make_event(self.user, "Visible", 2, 4)
        make_event(self.user, "Cancelled", 2, 4, status=Hackathon.Status.CANCELLED)
        Project.objects.create(
            title="Draft project",
            tagline="Draft",
            description="Draft",
            created_by=self.user,
            status=Project.Status.DRAFT,
        )
        Project.objects.create(
            title="Submitted project",
            tagline="Live",
            description="Live",
            created_by=self.user,
            status=Project.Status.SUBMITTED,
        )

        stats = views._platform_stats()
        self.assertEqual(stats["events"], 1)
        self.assertEqual(stats["projects"], 1)
        self.assertEqual(stats["builders"], 1)
        self.assertEqual(stats["confirmed_sponsorships"], 0)
        self.assertEqual(stats["funding"], 0)

    def test_stats_work_without_the_optional_sponsors_app(self):
        with patch.object(views, "Sponsorship", None):
            stats = views._platform_stats()
        self.assertEqual(stats["confirmed_sponsorships"], 0)
        self.assertEqual(stats["funding"], 0)


class BuildEventTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="builder-owner", password="pwd")

    def test_cancelled_and_finished_statuses_override_dates(self):
        cancelled = make_event(
            self.user,
            "Cancelled Event",
            2,
            4,
            status=Hackathon.Status.CANCELLED,
        )
        finished = make_event(
            self.user,
            "Finished Event",
            2,
            4,
            status=Hackathon.Status.FINISHED,
        )
        today = timezone.localdate()

        cancelled_card = views._build_event(cancelled, 0, today)
        finished_card = views._build_event(finished, 1, today)
        self.assertEqual(cancelled_card["status"], "Cancelled")
        self.assertTrue(cancelled_card["is_cancelled"])
        self.assertTrue(cancelled_card["is_finished"])
        self.assertEqual(finished_card["status"], "Completed")
        self.assertFalse(finished_card["is_cancelled"])

    def test_card_uses_registered_count_fallback_and_defaults(self):
        event = make_event(
            self.user,
            "Plain Event",
            2,
            4,
            prize_pool="",
            location="",
        )
        card = views._build_event(event, 2, timezone.localdate())
        self.assertEqual(card["registered"], 0)
        self.assertEqual(card["progress"], 0)
        self.assertEqual(card["prize"], "Prize TBA")
        self.assertEqual(
            card["dates"],
            views._format_date_range(
                views._event_local_date(event.start_date),
                views._event_local_date(event.end_date),
            ),
        )
        self.assertEqual(card["gradient"], views.EVENT_GRADIENTS[2])


class HomePageEdgeCaseTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="home-owner", password="pwd")

    def test_home_page_caps_the_grid_at_six_upcoming_events(self):
        for index in range(8):
            make_event(self.user, f"Upcoming {index}", 2 + index, 4 + index)

        response = self.client.get(reverse("core:home"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context["hackathons"]), 6)

    def test_home_page_fills_remaining_slots_with_past_events(self):
        make_event(self.user, "Past One", -10, -8)
        make_event(self.user, "Past Two", -6, -4)
        make_event(self.user, "Cancelled Past", -7, -5, status=Hackathon.Status.CANCELLED)
        for index in range(5):
            make_event(self.user, f"Upcoming {index}", 2 + index, 4 + index)

        response = self.client.get(reverse("core:home"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context["hackathons"]), 6)
        titles = [card["title"] for card in response.context["hackathons"]]
        self.assertIn("Past Two", titles)
        self.assertNotIn("Cancelled Past", titles)
