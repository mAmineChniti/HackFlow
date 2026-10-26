"""View-level coverage for the hackathons app: filters, CRUD, check-in and exports."""

from __future__ import annotations

import json
from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import Profile
from hackathons.forms import HackathonForm
from hackathons.models import Hackathon, HackathonRegistration

User = get_user_model()


def make_user(username, role=Profile.Role.STUDENT, *, superuser=False, staff=False, **extra):
    user = User.objects.create_user(
        username=username,
        email=f"{username}@example.com",
        password="S3curePassw0rd!",
        **extra,
    )
    user.profile.role = role
    user.profile.save()
    if superuser:
        user.is_superuser = True
    if staff:
        user.is_staff = True
    if superuser or staff:
        user.save(update_fields=["is_superuser", "is_staff"])
    return user


def make_hackathon(organizer, *, title="Coverage Cup", **overrides):
    now = timezone.now()
    values = {
        "title": title,
        "tagline": "Ship something real",
        "description": "A test hackathon used for coverage.",
        "category": "AI & Data",
        "registration_start": now - timedelta(days=2),
        "registration_deadline": now + timedelta(days=5),
        "start_date": now + timedelta(days=7),
        "end_date": now + timedelta(days=9),
        "max_participants": 50,
        "min_team_size": 1,
        "max_team_size": 4,
        "mode": Hackathon.Mode.HYBRID,
        "location": "Campus",
        "prize_pool": "$1,000",
        "organizer": organizer,
        "status": Hackathon.Status.REGISTRATION_OPEN,
        "is_published": True,
    }
    values.update(overrides)
    return Hackathon.objects.create(**values)


def registration_payload(**overrides):
    payload = {
        "university": "ESPRIT",
        "study_level": "ING3",
        "experience_level": "advanced",
        "selected_skills": ["Python", "Django"],
        "seeking_team": True,
        "motivation": "I want to build things.",
        "accepted_rules": True,
    }
    payload.update(overrides)
    return payload


def hackathon_form_payload(**overrides):
    now = timezone.now()
    payload = {
        "title": "Form Event",
        "tagline": "A new event",
        "description": "Created through the form.",
        "category": "Web",
        "mode": Hackathon.Mode.IN_PERSON,
        "location": "ESPRIT",
        "registration_start": (now - timedelta(days=1)).strftime("%Y-%m-%dT%H:%M"),
        "registration_deadline": (now + timedelta(days=2)).strftime("%Y-%m-%dT%H:%M"),
        "start_date": (now + timedelta(days=4)).strftime("%Y-%m-%dT%H:%M"),
        "end_date": (now + timedelta(days=6)).strftime("%Y-%m-%dT%H:%M"),
        "max_participants": 40,
        "min_team_size": 2,
        "max_team_size": 4,
        "prize_pool": "$500",
        "difficulty": Hackathon.Difficulty.ALL_LEVELS,
        "rules": "Be nice.",
        "contact_email": "organizer@example.com",
        "status": Hackathon.Status.REGISTRATION_OPEN,
        "is_published": True,
        "judges": [],
        "mentors": [],
    }
    payload.update(overrides)
    return payload


class HackathonListAndDetailTests(TestCase):
    def setUp(self):
        self.organizer = make_user("list-organizer", Profile.Role.ORGANIZER)
        self.student = make_user("list-student")
        self.judge = make_user("list-judge", Profile.Role.JUDGE)
        self.mentor = make_user("list-mentor", Profile.Role.MENTOR)
        self.hackathon = make_hackathon(self.organizer)
        self.hackathon.judges.add(self.judge)
        self.hackathon.mentors.add(self.mentor)
        self.draft = make_hackathon(
            self.organizer,
            title="Draft Event",
            status=Hackathon.Status.DRAFT,
            is_published=False,
            category="Cybersecurity",
            mode=Hackathon.Mode.ONLINE,
        )
        self.draft.judges.add(self.judge)
        self.draft.mentors.add(self.mentor)

    def test_list_view_filters_and_ordering(self):
        url = reverse("hackathons:list")
        cases = [
            {"q": "Coverage"},
            {"status": Hackathon.Status.REGISTRATION_OPEN},
            {"mode": Hackathon.Mode.HYBRID},
            {"category": "ai & data"},
            {"ordering": "newest"},
            {"ordering": "popular"},
            {"ordering": "not-a-real-ordering"},
        ]
        for params in cases:
            with self.subTest(params=params):
                response = self.client.get(url, params)
                self.assertEqual(response.status_code, 200)
        self.assertContains(self.client.get(url, {"q": "Coverage"}), "Coverage Cup")
        self.assertNotContains(self.client.get(url), "Draft Event")

    def test_list_view_htmx_returns_partial(self):
        response = self.client.get(reverse("hackathons:list"), HTTP_HX_REQUEST="true")
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "hackathons/partials/_hackathon_grid.html")

    def test_detail_visibility_per_role(self):
        detail_url = self.hackathon.get_absolute_url()
        draft_url = self.draft.get_absolute_url()
        self.assertEqual(self.client.get(detail_url).status_code, 200)
        self.assertEqual(self.client.get(draft_url).status_code, 404)

        for username in ("list-organizer", "list-judge", "list-mentor"):
            with self.subTest(username=username):
                self.client.force_login(User.objects.get(username=username))
                self.assertEqual(self.client.get(draft_url).status_code, 200)

        self.client.force_login(make_user("list-staff", staff=True))
        self.assertEqual(self.client.get(draft_url).status_code, 200)

        self.client.force_login(make_user("list-super", superuser=True))
        self.assertEqual(self.client.get(draft_url).status_code, 200)

    def test_detail_shows_registration_state_and_badge(self):
        registration = HackathonRegistration.objects.create(
            hackathon=self.hackathon,
            participant=self.student,
            status=HackathonRegistration.Status.CONFIRMED,
        )
        self.client.force_login(self.student)
        response = self.client.get(self.hackathon.get_absolute_url())
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["user_registration"], registration)
        self.assertEqual(response.context["confirmed_registrations_count"], 1)
        self.assertEqual(response.context["attendance_rate"], 0)
        self.assertIsNotNone(response.context["badge_qr_b64"])

        self.client.force_login(self.organizer)
        response = self.client.get(self.hackathon.get_absolute_url())
        self.assertTrue(response.context["is_organizer"])
        self.assertEqual(len(response.context["organizer_registrations"]), 1)

    def test_detail_staff_sees_registration_table(self):
        self.client.force_login(make_user("detail-staff", staff=True))
        response = self.client.get(self.hackathon.get_absolute_url())
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["organizer_registrations"].count(), 0)


class HackathonCrudViewTests(TestCase):
    def setUp(self):
        self.organizer = make_user("crud-organizer", Profile.Role.ORGANIZER)
        self.other_organizer = make_user("crud-other", Profile.Role.ORGANIZER)
        self.student = make_user("crud-student")
        self.hackathon = make_hackathon(self.organizer)

    def test_create_requires_login_and_role(self):
        # Both anonymous visitors and students are sent back to the catalogue by
        # the view's handle_no_permission override.
        self.assertRedirects(
            self.client.get(reverse("hackathons:create")), reverse("hackathons:list")
        )

        self.client.force_login(self.student)
        response = self.client.get(reverse("hackathons:create"))
        self.assertRedirects(response, reverse("hackathons:list"))

    def test_organizer_creates_hackathon(self):
        self.client.force_login(self.organizer)
        response = self.client.post(reverse("hackathons:create"), hackathon_form_payload())
        self.assertEqual(response.status_code, 302)
        created = Hackathon.objects.get(title="Form Event")
        self.assertEqual(created.organizer, self.organizer)
        self.assertRedirects(response, created.get_absolute_url())

    def test_superuser_can_create_hackathon(self):
        admin_user = make_user("crud-admin", superuser=True)
        self.client.force_login(admin_user)
        response = self.client.get(reverse("hackathons:create"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["page_title"], "Create a Hackathon")

    def test_invalid_create_form_is_redisplayed(self):
        self.client.force_login(self.organizer)
        response = self.client.post(reverse("hackathons:create"), {})
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Hackathon.objects.filter(title="Form Event").exists())

    def test_update_permissions_and_success(self):
        update_url = reverse("hackathons:update", args=[self.hackathon.slug])

        self.client.force_login(self.student)
        response = self.client.get(update_url)
        self.assertRedirects(response, reverse("hackathons:list"))

        self.client.force_login(self.other_organizer)
        response = self.client.get(update_url)
        self.assertRedirects(response, reverse("hackathons:list"))

        self.client.force_login(self.organizer)
        response = self.client.get(update_url)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["is_edit"])
        self.assertIn(self.hackathon.title, response.context["page_title"])

        payload = hackathon_form_payload(title="Updated Event")
        response = self.client.post(update_url, payload)
        self.assertEqual(response.status_code, 302)
        self.hackathon.refresh_from_db()
        self.assertEqual(self.hackathon.title, "Updated Event")

    def test_delete_permissions_and_success(self):
        delete_url = reverse("hackathons:delete", args=[self.hackathon.slug])

        self.client.force_login(self.other_organizer)
        self.assertEqual(self.client.get(delete_url).status_code, 403)

        self.client.force_login(self.organizer)
        response = self.client.get(delete_url)
        self.assertEqual(response.status_code, 200)

        response = self.client.post(delete_url)
        self.assertRedirects(response, reverse("hackathons:list"))
        self.assertFalse(Hackathon.objects.filter(pk=self.hackathon.pk).exists())


class HackathonRegistrationViewTests(TestCase):
    def setUp(self):
        self.organizer = make_user("reg-organizer", Profile.Role.ORGANIZER)
        self.student = make_user("reg-student")
        self.judge = make_user("reg-judge", Profile.Role.JUDGE)
        self.hackathon = make_hackathon(self.organizer)
        self.register_url = reverse("hackathons:register", args=[self.hackathon.slug])
        self.unregister_url = reverse("hackathons:unregister", args=[self.hackathon.slug])
        self.detail_url = self.hackathon.get_absolute_url()

    def test_anonymous_users_are_redirected_to_login(self):
        self.assertRedirects(
            self.client.get(self.register_url),
            f"{reverse('accounts:login')}?next={self.register_url}",
        )

    def test_organizer_cannot_register_as_participant(self):
        self.client.force_login(self.organizer)
        response = self.client.post(self.register_url, registration_payload())
        self.assertRedirects(response, self.detail_url)
        self.assertFalse(HackathonRegistration.objects.filter(participant=self.organizer).exists())

    def test_non_student_role_cannot_register(self):
        self.client.force_login(self.judge)
        response = self.client.post(self.register_url, registration_payload())
        self.assertRedirects(response, self.detail_url)
        self.assertFalse(HackathonRegistration.objects.filter(participant=self.judge).exists())

    def test_registration_not_open_yet(self):
        self.hackathon.registration_start = timezone.now() + timedelta(days=1)
        self.hackathon.save(update_fields=["registration_start"])
        self.client.force_login(self.student)
        response = self.client.post(self.register_url, registration_payload())
        self.assertRedirects(response, self.detail_url)
        self.assertFalse(HackathonRegistration.objects.exists())

    def test_registration_deadline_passed(self):
        self.hackathon.registration_deadline = timezone.now() - timedelta(days=1)
        self.hackathon.save(update_fields=["registration_deadline"])
        self.client.force_login(self.student)
        response = self.client.post(self.register_url, registration_payload())
        self.assertRedirects(response, self.detail_url)
        self.assertFalse(HackathonRegistration.objects.exists())

    def test_registration_status_must_be_open(self):
        self.hackathon.status = Hackathon.Status.DRAFT
        self.hackathon.save(update_fields=["status"])
        self.client.force_login(self.student)
        response = self.client.post(self.register_url, registration_payload())
        self.assertRedirects(response, self.detail_url)
        self.assertFalse(HackathonRegistration.objects.exists())

    def test_already_registered_user_is_redirected(self):
        HackathonRegistration.objects.create(hackathon=self.hackathon, participant=self.student)
        self.client.force_login(self.student)
        response = self.client.post(self.register_url, registration_payload())
        self.assertRedirects(response, self.detail_url)
        self.assertEqual(
            HackathonRegistration.objects.filter(
                hackathon=self.hackathon, participant=self.student
            ).count(),
            1,
        )

    def test_get_renders_registration_form(self):
        self.client.force_login(self.student)
        response = self.client.get(self.register_url)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "hackathons/register.html")
        self.assertFalse(response.context["is_full"])

    def test_invalid_submission_is_redisplayed(self):
        self.client.force_login(self.student)
        payload = registration_payload(selected_skills=[], accepted_rules=False)
        response = self.client.post(self.register_url, payload)
        self.assertEqual(response.status_code, 200)
        self.assertFalse(HackathonRegistration.objects.exists())

    def test_superuser_can_register(self):
        admin_user = make_user("reg-admin", superuser=True)
        self.client.force_login(admin_user)
        response = self.client.post(self.register_url, registration_payload())
        self.assertRedirects(response, self.detail_url)
        self.assertTrue(
            HackathonRegistration.objects.filter(participant=admin_user).exists()
        )

    def test_unregister_when_not_registered_warns(self):
        self.client.force_login(self.student)
        response = self.client.post(self.unregister_url)
        self.assertRedirects(response, self.detail_url)

    def test_unregister_via_get_does_not_delete(self):
        HackathonRegistration.objects.create(hackathon=self.hackathon, participant=self.student)
        self.client.force_login(self.student)
        self.client.get(self.unregister_url)
        self.assertTrue(
            HackathonRegistration.objects.filter(participant=self.student).exists()
        )

    def test_unregister_promotes_first_waitlisted_participant(self):
        Registration = HackathonRegistration
        confirmed = Registration.objects.create(
            hackathon=self.hackathon,
            participant=self.student,
            status=Registration.Status.CONFIRMED,
        )
        waiting = make_user("reg-waiting")
        waitlist = Registration.objects.create(
            hackathon=self.hackathon,
            participant=waiting,
            status=Registration.Status.WAITLIST,
        )
        self.client.force_login(self.student)
        self.client.post(self.unregister_url)

        self.assertFalse(Registration.objects.filter(pk=confirmed.pk).exists())
        waitlist.refresh_from_db()
        self.assertEqual(waitlist.status, Registration.Status.CONFIRMED)


class HackathonDashboardTests(TestCase):
    def setUp(self):
        self.organizer = make_user("dash-organizer", Profile.Role.ORGANIZER)
        self.hackathon = make_hackathon(self.organizer)

    def dashboard_url(self):
        return reverse("hackathons:dashboard")

    def test_admin_dashboard(self):
        self.client.force_login(make_user("dash-admin", superuser=True))
        response = self.client.get(self.dashboard_url())
        self.assertEqual(response.context["user_role"], "admin")

    def test_judge_dashboard(self):
        judge = make_user("dash-judge", Profile.Role.JUDGE)
        self.hackathon.judges.add(judge)
        self.client.force_login(judge)
        response = self.client.get(self.dashboard_url())
        self.assertEqual(response.context["user_role"], "judge")

    def test_mentor_dashboard(self):
        mentor = make_user("dash-mentor", Profile.Role.MENTOR)
        self.hackathon.mentors.add(mentor)
        self.client.force_login(mentor)
        response = self.client.get(self.dashboard_url())
        self.assertEqual(response.context["user_role"], "mentor")

    def test_organizer_dashboard(self):
        self.client.force_login(self.organizer)
        response = self.client.get(self.dashboard_url())
        self.assertEqual(response.context["user_role"], "organizer")

    def test_student_dashboard(self):
        student = make_user("dash-student")
        HackathonRegistration.objects.create(hackathon=self.hackathon, participant=student)
        self.client.force_login(student)
        response = self.client.get(self.dashboard_url())
        self.assertEqual(response.context["user_role"], "student")


class HackathonAiEndpointTests(TestCase):
    def setUp(self):
        self.organizer = make_user("ai-organizer", Profile.Role.ORGANIZER)
        self.student = make_user("ai-student")
        self.hackathon = make_hackathon(self.organizer)

    def test_get_method_is_rejected(self):
        self.client.force_login(self.organizer)
        response = self.client.get(reverse("hackathons:ai_generate"))
        self.assertEqual(response.status_code, 405)
        self.assertJSONEqual(response.content, {"error": "POST method required."})

    def test_only_organizers_can_generate(self):
        self.client.force_login(self.student)
        response = self.client.post(reverse("hackathons:ai_generate"), {"title": "X"})
        self.assertEqual(response.status_code, 403)

    def test_missing_title_returns_400(self):
        self.client.force_login(self.organizer)
        response = self.client.post(reverse("hackathons:ai_generate"), {"category": "AI"})
        self.assertEqual(response.status_code, 400)
        self.assertJSONEqual(
            response.content, {"error": "Please provide an event title first."}
        )

    def test_form_encoded_generation(self):
        self.client.force_login(self.organizer)
        response = self.client.post(
            reverse("hackathons:ai_generate"),
            {"title": "AI Camp", "category": "AI", "hints": "agents"},
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["success"])
        self.assertIn("tagline", payload["data"])

    def test_json_generation(self):
        self.client.force_login(self.organizer)
        response = self.client.post(
            reverse("hackathons:ai_generate"),
            data=json.dumps({"title": "Green Camp", "category": "GreenTech"}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["success"])

    def test_generation_failure_returns_500(self):
        self.client.force_login(self.organizer)
        with patch(
            "hackathons.views.generate_hackathon_content", side_effect=RuntimeError("boom")
        ):
            response = self.client.post(
                reverse("hackathons:ai_generate"), {"title": "Broken"}
            )
        self.assertEqual(response.status_code, 500)
        self.assertJSONEqual(response.content, {"error": "boom"})

    def test_public_ideas_endpoint(self):
        response = self.client.get(reverse("hackathons:ai_ideas", args=[self.hackathon.slug]))
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["success"])
        self.assertGreaterEqual(len(payload["ideas"]), 3)


class HackathonExportAndCheckinTests(TestCase):
    def setUp(self):
        self.organizer = make_user("checkin-organizer", Profile.Role.ORGANIZER)
        self.student = make_user("checkin-student", first_name="Sam", last_name="Builder")
        self.judge = make_user("checkin-judge", Profile.Role.JUDGE)
        self.hackathon = make_hackathon(self.organizer)
        self.registration = HackathonRegistration.objects.create(
            hackathon=self.hackathon,
            participant=self.student,
            status=HackathonRegistration.Status.CONFIRMED,
            university="ESPRIT",
            study_level=HackathonRegistration.StudyLevel.M2,
            experience_level=HackathonRegistration.ExperienceLevel.ADVANCED,
            skills="Python, Django",
            seeking_team=True,
            portfolio_url="https://example.com/portfolio",
            motivation="Learn a lot",
        )

    def test_export_csv_for_organizer(self):
        self.client.force_login(self.organizer)
        response = self.client.get(
            reverse("hackathons:export_participants", args=[self.hackathon.slug])
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "text/csv; charset=utf-8")
        self.assertIn("attachment;", response["Content-Disposition"])
        content = response.content.decode("utf-8-sig")
        self.assertIn("Username", content)
        self.assertIn("checkin-student", content)
        self.assertIn("Python, Django", content)
        self.assertIn("https://example.com/portfolio", content)

    def test_export_csv_denied_for_students(self):
        self.client.force_login(self.student)
        response = self.client.get(
            reverse("hackathons:export_participants", args=[self.hackathon.slug])
        )
        self.assertRedirects(response, self.hackathon.get_absolute_url())

    def test_badge_with_ticket_supplied_by_organizer(self):
        self.client.force_login(self.organizer)
        response = self.client.get(
            reverse("hackathons:participant_badge", args=[self.hackathon.slug]),
            {"ticket": self.registration.ticket_code},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["registration"], self.registration)
        self.assertTrue(response.context["is_organizer"])

    def test_badge_synthetic_for_unregistered_visitor(self):
        self.registration.delete()
        self.client.force_login(self.student)
        response = self.client.get(
            reverse("hackathons:participant_badge", args=[self.hackathon.slug])
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["registration"].ticket_code.startswith("HF-PASS-"))

    def test_badge_falls_back_to_first_registration(self):
        other = make_user("checkin-other")
        self.client.force_login(other)
        response = self.client.get(
            reverse("hackathons:participant_badge", args=[self.hackathon.slug])
        )
        self.assertEqual(response.context["registration"], self.registration)

    def test_checkin_page_marks_attendance_once(self):
        self.client.force_login(self.organizer)
        url = reverse(
            "hackathons:organizer_checkin",
            args=[self.hackathon.slug, self.registration.ticket_code],
        )

        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["is_authorized"])

        response = self.client.post(url)
        self.assertEqual(response.context["action_done"], "checked_in_now")
        self.registration.refresh_from_db()
        self.assertTrue(self.registration.checked_in)
        self.assertIsNotNone(self.registration.checked_in_at)

        response = self.client.post(url)
        self.assertEqual(response.context["action_done"], "already_checked_in")

    def test_checkin_page_does_not_mark_unauthorized_users(self):
        self.client.force_login(self.student)
        url = reverse(
            "hackathons:organizer_checkin",
            args=[self.hackathon.slug, self.registration.ticket_code],
        )
        response = self.client.post(url)
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.context["is_authorized"])
        self.assertIsNone(response.context["action_done"])
        self.registration.refresh_from_db()
        self.assertFalse(self.registration.checked_in)

    def test_checkin_allows_assigned_judge(self):
        self.hackathon.judges.add(self.judge)
        self.client.force_login(self.judge)
        url = reverse(
            "hackathons:organizer_checkin",
            args=[self.hackathon.slug, self.registration.ticket_code],
        )
        self.client.post(url)
        self.registration.refresh_from_db()
        self.assertTrue(self.registration.checked_in)

    def test_toggle_checkin_permissions_and_round_trip(self):
        url = reverse(
            "hackathons:toggle_checkin",
            args=[self.hackathon.slug, self.registration.ticket_code],
        )

        self.client.force_login(self.student)
        response = self.client.post(url)
        self.assertRedirects(response, self.hackathon.get_absolute_url())

        self.client.force_login(self.organizer)
        self.client.post(url)
        self.registration.refresh_from_db()
        self.assertTrue(self.registration.checked_in)
        self.assertIsNotNone(self.registration.checked_in_at)

        self.client.post(url)
        self.registration.refresh_from_db()
        self.assertFalse(self.registration.checked_in)
        self.assertIsNone(self.registration.checked_in_at)


class HackathonFormTests(TestCase):
    def setUp(self):
        self.organizer = make_user("form-organizer", Profile.Role.ORGANIZER)
        self.judge = make_user("form-judge", Profile.Role.JUDGE)
        self.mentor = make_user("form-mentor", Profile.Role.MENTOR)

    def test_form_querysets_and_initial_dates(self):
        hackathon = make_hackathon(self.organizer)
        form = HackathonForm(instance=hackathon)

        self.assertIn(self.judge, form.fields["judges"].queryset)
        self.assertNotIn(self.mentor, form.fields["judges"].queryset)
        self.assertIn(self.mentor, form.fields["mentors"].queryset)
        self.assertNotIn(self.judge, form.fields["mentors"].queryset)
        self.assertEqual(
            form.initial["start_date"], hackathon.start_date.strftime("%Y-%m-%dT%H:%M")
        )

    def test_form_rejects_inverted_dates_and_team_sizes(self):
        now = timezone.now()
        form = HackathonForm(
            data=hackathon_form_payload(
                registration_start=(now + timedelta(days=2)).strftime("%Y-%m-%dT%H:%M"),
                registration_deadline=(now + timedelta(days=2)).strftime("%Y-%m-%dT%H:%M"),
                start_date=(now + timedelta(days=1)).strftime("%Y-%m-%dT%H:%M"),
                end_date=now.strftime("%Y-%m-%dT%H:%M"),
                min_team_size=5,
                max_team_size=2,
            )
        )
        self.assertFalse(form.is_valid())
        self.assertIn("registration_deadline", form.errors)
        self.assertIn("start_date", form.errors)
        self.assertIn("end_date", form.errors)
        self.assertIn("min_team_size", form.errors)


class RegistrationFormTests(TestCase):
    def setUp(self):
        self.organizer = make_user("rform-organizer", Profile.Role.ORGANIZER)
        self.student = make_user("rform-student")
        self.hackathon = make_hackathon(self.organizer)

    def test_existing_skills_are_split_into_popular_and_other(self):
        from hackathons.forms import RegistrationForm

        registration = HackathonRegistration.objects.create(
            hackathon=self.hackathon,
            participant=self.student,
            skills="Python, Rust, Django",
        )
        form = RegistrationForm(instance=registration)
        self.assertEqual(form.initial["selected_skills"], ["Python", "Django"])
        self.assertEqual(form.initial["other_skills"], "Rust")

    def test_other_skills_are_merged(self):
        from hackathons.forms import RegistrationForm

        form = RegistrationForm(
            data=registration_payload(selected_skills=[], other_skills="Rust, Go")
        )
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data["skills"], "Rust, Go")

    def test_direct_hidden_skills_are_kept_when_no_checkboxes_chosen(self):
        from hackathons.forms import RegistrationForm

        form = RegistrationForm(
            data=registration_payload(selected_skills=[], skills="Elixir, Erlang")
        )
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data["skills"], "Elixir, Erlang")

    def test_missing_skills_and_rules_raise_errors(self):
        from hackathons.forms import RegistrationForm

        form = RegistrationForm(data=registration_payload(selected_skills=[], accepted_rules=False))
        self.assertFalse(form.is_valid())
        self.assertIn("selected_skills", form.errors)
        self.assertIn("accepted_rules", form.errors)
