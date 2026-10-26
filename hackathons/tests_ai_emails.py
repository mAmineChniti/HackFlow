"""Unit tests for the hackathons AI engine and notification emails."""

from __future__ import annotations

from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core import mail
from django.test import TestCase, override_settings
from django.utils import timezone

from accounts.models import Profile
from hackathons.ai import (
    _parse_json_response,
    calculate_team_match_score,
    generate_hackathon_content,
    generate_project_ideas,
)
from hackathons.emails import (
    check_and_notify_capacity_thresholds,
    send_organizer_new_registration_email,
    send_student_registration_email,
    send_waitlist_promoted_email,
)
from hackathons.models import Hackathon, HackathonRegistration

User = get_user_model()


class ParseJsonResponseTests(TestCase):
    def test_returns_none_for_empty_payloads(self):
        self.assertIsNone(_parse_json_response(None, dict))
        self.assertIsNone(_parse_json_response("", dict))
        self.assertIsNone(_parse_json_response("not json at all", dict))

    def test_parses_code_fenced_json(self):
        payload = '```json\n{"tagline": "Ship it"}\n```'
        self.assertEqual(_parse_json_response(payload, dict), {"tagline": "Ship it"})

    def test_extracts_object_embedded_in_prose(self):
        payload = 'Sure, here you go: {"tagline": "Ship it"} — enjoy!'
        self.assertEqual(_parse_json_response(payload, dict), {"tagline": "Ship it"})

    def test_extracts_array_embedded_in_prose(self):
        payload = "Ideas: [{\"title\": \"One\"}]"
        self.assertEqual(_parse_json_response(payload, list), [{"title": "One"}])

    def test_rejects_payload_of_wrong_type(self):
        self.assertIsNone(_parse_json_response('{"tagline": "Ship it"}', list))


class GenerateHackathonContentTests(TestCase):
    def setUp(self):
        self.groq_key = patch("hackathons.ai.get_api_key", return_value=None)
        self.groq_key.start()

    def tearDown(self):
        self.groq_key.stop()

    def test_default_engine_returns_complete_content(self):
        data = generate_hackathon_content("Campus Builders", "Web", "students")
        self.assertEqual(
            set(data), {"tagline", "description", "rules", "suggested_skills"}
        )
        self.assertIn("Campus Builders", data["tagline"])
        self.assertGreaterEqual(len(data["suggested_skills"]), 4)

    def test_domain_detection(self):
        cases = {
            "AI Hack": "Unleash next-generation",
            "Cyber Shield": "Fortify digital frontiers",
            "Green Future": "Build sustainable technology",
            "Open Weekend": "open-canvas",
        }
        for title, expected_phrase in cases.items():
            with self.subTest(title=title):
                data = generate_hackathon_content(title)
                haystack = data["tagline"] + data["description"]
                self.assertIn(expected_phrase, haystack)

    @patch("hackathons.ai.call_groq")
    def test_uses_remote_json_when_configured(self, call_groq):
        call_groq.return_value = (
            '{"tagline": "Remote", "description": "Remote description", '
            '"rules": "Remote rules", "suggested_skills": ["Python"]}'
        )
        with patch("hackathons.ai.get_api_key", return_value="key"):
            data = generate_hackathon_content("Remote Event")
        self.assertEqual(data["tagline"], "Remote")
        call_groq.assert_called_once()

    @patch("hackathons.ai.call_groq")
    def test_falls_back_when_remote_json_is_incomplete(self, call_groq):
        call_groq.return_value = '{"tagline": "Only a tagline"}'
        with patch("hackathons.ai.get_api_key", return_value="key"):
            data = generate_hackathon_content("Fallback Event")
        self.assertIn("Fallback Event", data["tagline"])
        self.assertIn("description", data)

    @patch("hackathons.ai.call_groq")
    def test_falls_back_when_remote_call_returns_none(self, call_groq):
        call_groq.return_value = None
        with patch("hackathons.ai.get_api_key", return_value="key"):
            data = generate_hackathon_content("Failure Event")
        self.assertIn("Failure Event", data["tagline"])
        self.assertIn("description", data)


class GenerateProjectIdeasTests(TestCase):
    def test_local_ideas_are_domain_specific(self):
        cyber = generate_project_ideas("Cyber CTF", "Security", "Capture the flag")
        ai = generate_project_ideas("AI Sprint", "Machine Learning", "Agents")
        general = generate_project_ideas("Open Weekend", "General", "Anything")

        for ideas in (cyber, ai, general):
            self.assertEqual(len(ideas), 3)
            for idea in ideas:
                self.assertEqual(
                    set(idea),
                    {"title", "problem", "solution", "tech_stack", "difficulty"},
                )
        self.assertIn("SentinelFlow", cyber[0]["title"])
        self.assertIn("DocuPulse", ai[0]["title"])
        self.assertIn("TeamSync", general[0]["title"])

    @patch("hackathons.ai.call_groq")
    def test_remote_ideas_are_used_when_valid(self, call_groq):
        call_groq.return_value = '[{"title": "Remote Idea", "problem": "p", "solution": "s"}]'
        with patch("hackathons.ai.get_api_key", return_value="key"):
            ideas = generate_project_ideas("Remote", "AI", "desc")
        self.assertEqual(ideas, [{"title": "Remote Idea", "problem": "p", "solution": "s"}])

    @patch("hackathons.ai.call_groq")
    def test_remote_payload_with_wrong_shape_falls_back(self, call_groq):
        call_groq.return_value = '["not", "objects"]'
        with patch("hackathons.ai.get_api_key", return_value="key"):
            ideas = generate_project_ideas("Remote", "AI", "desc")
        self.assertEqual(len(ideas), 3)
        self.assertIn("title", ideas[0])


class TeamMatchScoreTests(TestCase):
    def test_empty_skill_lists_return_neutral_score(self):
        result = calculate_team_match_score([], ["React"])
        self.assertEqual(result["score"], 50)
        self.assertEqual(result["overlap"], [])
        self.assertEqual(result["synergy"], "Basic Match")

    def test_requires_both_sides_to_have_skills(self):
        self.assertEqual(calculate_team_match_score(["Python"], [])["score"], 50)
        self.assertEqual(calculate_team_match_score(["  "], ["React"])["score"], 50)

    def test_complementary_domains_boost_the_score(self):
        result = calculate_team_match_score(
            ["Python", "Django"], ["React", "Figma", "Kubernetes"]
        )
        self.assertGreaterEqual(result["score"], 85)
        self.assertIn("Dream Team", result["synergy"])
        self.assertEqual(result["overlap"], [])
        self.assertIn("react", result["complementary"])

    def test_overlapping_skills_are_reported(self):
        result = calculate_team_match_score(["Python", "Django"], ["Python", "Django"])
        self.assertEqual(set(result["overlap"]), {"python", "django"})
        self.assertEqual(result["complementary"], [])
        self.assertLessEqual(result["score"], 98)
        self.assertIn("Good Match", result["synergy"])


@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
class RegistrationEmailTests(TestCase):
    def setUp(self):
        mail.outbox.clear()
        self.organizer = User.objects.create_user(
            username="mail-organizer",
            email="organizer@example.com",
            password="S3curePassw0rd!",
            first_name="Olivia",
        )
        self.organizer.profile.role = Profile.Role.ORGANIZER
        self.organizer.profile.save()
        self.student = User.objects.create_user(
            username="mail-student",
            email="student@example.com",
            password="S3curePassw0rd!",
            first_name="Sam",
        )
        self.hackathon = self.make_hackathon()
        self.registration = HackathonRegistration.objects.create(
            hackathon=self.hackathon,
            participant=self.student,
            status=HackathonRegistration.Status.CONFIRMED,
            university="ESPRIT",
            study_level=HackathonRegistration.StudyLevel.ING3,
            experience_level=HackathonRegistration.ExperienceLevel.ADVANCED,
            skills="Python, Django",
            seeking_team=True,
        )

    def make_hackathon(self, **overrides):
        now = timezone.now()
        values = {
            "title": "Email Event",
            "tagline": "Email me",
            "description": "Coverage for notification emails.",
            "category": "AI",
            "registration_start": now - timedelta(days=2),
            "registration_deadline": now + timedelta(days=5),
            "start_date": now + timedelta(days=7),
            "end_date": now + timedelta(days=9),
            "max_participants": 10,
            "organizer": self.organizer,
            "status": Hackathon.Status.REGISTRATION_OPEN,
            "is_published": True,
            "contact_email": "team@example.com",
        }
        values.update(overrides)
        return Hackathon.objects.create(**values)

    def test_confirmed_email_contains_schedule(self):
        send_student_registration_email(self.registration)
        self.assertEqual(len(mail.outbox), 1)
        message = mail.outbox[0]
        self.assertIn("Registration Confirmed", message.subject)
        self.assertEqual(message.to, ["student@example.com"])
        self.assertIn("Email Event", message.body)

    def test_waitlist_email_mentions_capacity(self):
        self.registration.status = HackathonRegistration.Status.WAITLIST
        self.registration.save(update_fields=["status"])
        send_student_registration_email(self.registration)
        self.assertIn("Waitlist Confirmation", mail.outbox[0].subject)
        self.assertIn("priority waitlist", mail.outbox[0].body)

    def test_missing_recipient_is_a_noop(self):
        self.student.email = ""
        self.student.save(update_fields=["email"])
        send_student_registration_email(self.registration)
        send_waitlist_promoted_email(self.registration)
        self.assertEqual(mail.outbox, [])

    def test_send_failures_are_logged_not_raised(self):
        with patch("hackathons.emails.send_mail", side_effect=RuntimeError("smtp down")):
            send_student_registration_email(self.registration)
            send_waitlist_promoted_email(self.registration)
            send_organizer_new_registration_email(self.registration)
        self.assertEqual(mail.outbox, [])

    def test_waitlist_promotion_email(self):
        send_waitlist_promoted_email(self.registration)
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("CONFIRMED", mail.outbox[0].subject)
        self.assertIn("Email Event", mail.outbox[0].body)

    def test_organizer_email_deduplicates_recipients(self):
        self.organizer.email = self.hackathon.contact_email
        self.organizer.save(update_fields=["email"])
        send_organizer_new_registration_email(self.registration)
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ["team@example.com"])
        self.assertIn("mail-student", mail.outbox[0].subject)
        self.assertIn("Python, Django", mail.outbox[0].body)

    def test_organizer_email_without_recipients_is_noop(self):
        self.organizer.email = ""
        self.organizer.save(update_fields=["email"])
        self.hackathon.contact_email = ""
        self.hackathon.save(update_fields=["contact_email"])
        send_organizer_new_registration_email(self.registration)
        self.assertEqual(mail.outbox, [])

    def test_capacity_alert_at_80_percent(self):
        HackathonRegistration.objects.filter(pk=self.registration.pk).update(status="confirmed")
        for index in range(7):
            participant = User.objects.create_user(
                username=f"capacity-{index}", email=f"capacity-{index}@example.com"
            )
            HackathonRegistration.objects.create(
                hackathon=self.hackathon, participant=participant
            )
        # 8 confirmed of 10 → 80% threshold crossed.
        check_and_notify_capacity_thresholds(self.hackathon, previous_count=7)
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("80% Capacity", mail.outbox[0].subject)

    def test_capacity_alert_at_100_percent(self):
        for index in range(9):
            participant = User.objects.create_user(
                username=f"full-{index}", email=f"full-{index}@example.com"
            )
            HackathonRegistration.objects.create(
                hackathon=self.hackathon, participant=participant
            )
        check_and_notify_capacity_thresholds(self.hackathon, previous_count=9)
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("Maximum Capacity", mail.outbox[0].subject)

    def test_capacity_alert_skips_invalid_configurations(self):
        check_and_notify_capacity_thresholds(self.hackathon, previous_count=8)
        self.assertEqual(mail.outbox, [])

        self.hackathon.max_participants = 0
        self.hackathon.save(update_fields=["max_participants"])
        check_and_notify_capacity_thresholds(self.hackathon, previous_count=0)
        self.assertEqual(mail.outbox, [])
