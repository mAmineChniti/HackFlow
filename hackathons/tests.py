from datetime import timedelta
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from accounts.models import Profile
from .models import Hackathon, HackathonRegistration

User = get_user_model()


class HackathonModelTest(TestCase):
    def setUp(self):
        self.organizer = User.objects.create_user(
            username="organizer1", password="password123", email="org@hackflow.dev"
        )
        self.organizer.profile.role = Profile.Role.ORGANIZER
        self.organizer.profile.save()

        self.student = User.objects.create_user(
            username="student1", password="password123", email="student@hackflow.dev"
        )
        self.student.profile.role = Profile.Role.STUDENT
        self.student.profile.save()

        now = timezone.now()
        self.hackathon = Hackathon.objects.create(
            title="AI Innovation Cup",
            tagline="Ship AI apps",
            description="Detailed AI event description",
            category="AI",
            registration_start=now - timedelta(days=2),
            registration_deadline=now + timedelta(days=5),
            start_date=now + timedelta(days=7),
            end_date=now + timedelta(days=9),
            max_participants=50,
            organizer=self.organizer,
            status=Hackathon.Status.REGISTRATION_OPEN,
            is_published=True,
        )

    def test_slug_auto_generation(self):
        self.assertEqual(self.hackathon.slug, "ai-innovation-cup")

    def test_registration_window(self):
        self.assertTrue(self.hackathon.is_registration_open)

    def test_views_response(self):
        # List view
        response = self.client.get(reverse("hackathons:list"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "AI Innovation Cup")

        # Detail view
        response = self.client.get(self.hackathon.get_absolute_url())
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "AI Innovation Cup")

    def test_student_cannot_create_hackathon(self):
        self.client.login(username="student1", password="password123")
        response = self.client.get(reverse("hackathons:create"))
        # Student should be redirected with an error message
        self.assertEqual(response.status_code, 302)
        self.assertRedirects(response, reverse("hackathons:list"))

    def test_organizer_can_access_create_hackathon(self):
        self.client.login(username="organizer1", password="password123")
        response = self.client.get(reverse("hackathons:create"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Create a Hackathon")

    def test_student_can_register_before_deadline(self):
        self.client.login(username="student1", password="password123")
        post_url = reverse("hackathons:register", kwargs={"slug": self.hackathon.slug})
        payload = {
            "university": "ESPRIT",
            "study_level": "ING1",
            "experience_level": "intermediate",
            "selected_skills": ["Python", "Django"],
            "motivation": "I love AI",
            "accepted_rules": True,
        }
        response = self.client.post(post_url, payload)
        self.assertEqual(response.status_code, 302)
        reg = HackathonRegistration.objects.filter(
            hackathon=self.hackathon, participant=self.student
        ).first()
        self.assertIsNotNone(reg)
        self.assertEqual(reg.status, HackathonRegistration.Status.CONFIRMED)
        self.assertEqual(reg.university, "ESPRIT")

    def test_waitlist_and_promotion_flow(self):
        # Set max capacity to 1
        self.hackathon.max_participants = 1
        self.hackathon.save()

        # Register student 1 (confirmed)
        reg1 = HackathonRegistration.objects.create(
            hackathon=self.hackathon,
            participant=self.student,
            status=HackathonRegistration.Status.CONFIRMED,
        )

        # Create student 2
        student2 = User.objects.create_user(
            username="student2", password="password123", email="s2@test.dev"
        )
        student2.profile.role = Profile.Role.STUDENT
        student2.profile.save()

        # Register student 2 (should be placed on waitlist)
        self.client.login(username="student2", password="password123")
        post_url = reverse("hackathons:register", kwargs={"slug": self.hackathon.slug})
        payload = {
            "university": "INSAT",
            "study_level": "L3",
            "experience_level": "beginner",
            "selected_skills": ["React"],
            "accepted_rules": True,
        }
        response = self.client.post(post_url, payload)
        self.assertEqual(response.status_code, 302)

        reg2 = HackathonRegistration.objects.filter(
            hackathon=self.hackathon, participant=student2
        ).first()
        self.assertIsNotNone(reg2)
        self.assertEqual(reg2.status, HackathonRegistration.Status.WAITLIST)

        # Student 1 unregisters -> Student 2 should be promoted to confirmed
        self.client.login(username="student1", password="password123")
        unreg_url = reverse("hackathons:unregister", kwargs={"slug": self.hackathon.slug})
        self.client.post(unreg_url)

        # Check that reg1 is deleted and reg2 is now CONFIRMED
        self.assertFalse(HackathonRegistration.objects.filter(id=reg1.id).exists())
        reg2.refresh_from_db()
        self.assertEqual(reg2.status, HackathonRegistration.Status.CONFIRMED)

    def test_student_cannot_unregister_after_deadline(self):
        # Register student first
        HackathonRegistration.objects.create(hackathon=self.hackathon, participant=self.student)
        # Shift deadline to past
        self.hackathon.registration_deadline = timezone.now() - timedelta(days=1)
        self.hackathon.save()

        self.client.login(username="student1", password="password123")
        post_url = reverse("hackathons:unregister", kwargs={"slug": self.hackathon.slug})
        response = self.client.post(post_url)
        # Registration should still exist because deadline passed!
        self.assertTrue(
            HackathonRegistration.objects.filter(
                hackathon=self.hackathon, participant=self.student
            ).exists()
        )

    def test_organizer_cannot_register_as_participant(self):
        self.client.login(username="org_user", password="password123")
        post_url = reverse("hackathons:register", kwargs={"slug": self.hackathon.slug})
        response = self.client.post(
            post_url,
            data={
                "university": "ESPRIT",
                "study_level": "ing",
                "skills": ["python"],
                "experience_level": "intermediate",
                "accepted_rules": True,
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertFalse(HackathonRegistration.objects.filter(participant=self.organizer).exists())

    def test_participant_badge_view(self):
        # Register student first
        reg = HackathonRegistration.objects.create(
            hackathon=self.hackathon,
            participant=self.student,
            status=HackathonRegistration.Status.CONFIRMED,
        )
        self.assertTrue(reg.ticket_code.startswith("HF-"))

        self.client.login(username="student1", password="password123")
        badge_url = reverse("hackathons:participant_badge", kwargs={"slug": self.hackathon.slug})
        response = self.client.get(badge_url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, reg.ticket_code)
        self.assertContains(response, "Official Event Credential")
        self.assertContains(response, "data:image/png;base64,")

    def test_organizer_checkin_validation(self):
        reg = HackathonRegistration.objects.create(
            hackathon=self.hackathon,
            participant=self.student,
            status=HackathonRegistration.Status.CONFIRMED,
        )
        self.assertFalse(reg.checked_in)

        # Organizer logs in and validates check-in
        self.client.login(username="organizer1", password="password123")
        checkin_url = reverse(
            "hackathons:organizer_checkin",
            kwargs={"slug": self.hackathon.slug, "ticket_code": reg.ticket_code},
        )

        # GET checkin screen
        get_resp = self.client.get(checkin_url)
        self.assertEqual(get_resp.status_code, 200)
        self.assertContains(get_resp, reg.ticket_code)

        # POST to confirm door check-in
        post_resp = self.client.post(checkin_url)
        self.assertEqual(post_resp.status_code, 200)
        reg.refresh_from_db()
        self.assertTrue(reg.checked_in)
        self.assertIsNotNone(reg.checked_in_at)
        self.assertContains(post_resp, "✓ PARTICIPANT CHECKED-IN")
