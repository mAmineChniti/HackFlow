from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from datetime import timedelta
from .models import Hackathon, HackathonRegistration

User = get_user_model()


class HackathonModelTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="organizer1", password="password123", email="org@hackflow.dev"
        )
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
            organizer=self.user,
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
