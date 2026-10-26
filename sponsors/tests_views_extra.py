"""Additional end-to-end coverage for the sponsor management views."""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth.models import User
from django.core import mail
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from hackathons.models import Hackathon
from sponsors.models import (
    Sponsor,
    SponsorEmailLog,
    Sponsorship,
    StatusChoices,
    StatusHistory,
    TierChoices,
)


def make_hackathon(organizer, *, title="Sponsor Flow Hackathon"):
    now = timezone.now()
    return Hackathon.objects.create(
        title=title,
        tagline="Sponsors welcome",
        description="Sponsor flow coverage.",
        category="AI",
        registration_start=now - timezone.timedelta(days=1),
        registration_deadline=now + timezone.timedelta(days=1),
        start_date=now + timezone.timedelta(days=2),
        end_date=now + timezone.timedelta(days=4),
        organizer=organizer,
        status=Hackathon.Status.REGISTRATION_OPEN,
        is_published=True,
    )


@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
class SponsorFlowTests(TestCase):
    def setUp(self):
        mail.outbox.clear()
        self.organizer = User.objects.create_user(
            username="flow-staff",
            password="password123",
            email="staff@esprit.tn",
            is_staff=True,
            is_superuser=True,
        )
        self.hackathon = make_hackathon(self.organizer)
        self.other_hackathon = make_hackathon(self.organizer, title="Second Hackathon")
        self.sponsor = Sponsor.objects.create(
            name="Flow Corp",
            sector="tech",
            description="Cloud partner.",
            contact_name="Karim",
            contact_email="karim@flow.example.com",
            website="https://flow.example.com",
        )
        self.sponsorship = Sponsorship.objects.create(
            sponsor=self.sponsor,
            hackathon=self.hackathon,
            tier=TierChoices.PLATINUM,
            amount=Decimal("5000.000"),
            status=StatusChoices.CONFIRME,
        )
        self.client.force_login(self.organizer)

    # ------------------------------------------------------------------
    # Public page and dashboard filters
    # ------------------------------------------------------------------

    def test_public_list_hackathon_filter(self):
        Sponsorship.objects.create(
            sponsor=Sponsor.objects.create(name="Second Corp"),
            hackathon=self.other_hackathon,
            tier=TierChoices.GOLD,
            status=StatusChoices.CONFIRME,
        )

        response = self.client.get(
            reverse("sponsors:public_list"), {"hackathon": self.other_hackathon.pk}
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["selected_hackathon"], self.other_hackathon)
        self.assertEqual(response.context["total_confirmed"], 1)
        self.assertContains(response, "Second Corp")
        self.assertNotContains(response, "Flow Corp")

    def test_public_list_ignores_unknown_hackathon_filter(self):
        response = self.client.get(reverse("sponsors:public_list"), {"hackathon": "999999"})
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.context["selected_hackathon"])
        self.assertEqual(response.context["total_confirmed"], 1)

    def test_dashboard_filters_by_hackathon_and_ignores_unknown_ids(self):
        url = reverse("sponsors:dashboard")

        response = self.client.get(url, {"hackathon": self.hackathon.pk})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["selected_hackathon"], self.hackathon)
        self.assertEqual(response.context["total_partnerships_count"], 1)

        response = self.client.get(url, {"hackathon": "999999"})
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.context["selected_hackathon"])
        self.assertEqual(response.context["total_funds_confirmed"], Decimal("5000.000"))

    # ------------------------------------------------------------------
    # Directory filters
    # ------------------------------------------------------------------

    def test_directory_filters_by_sector_tier_and_hackathon(self):
        other_sponsor = Sponsor.objects.create(name="Energy Corp", sector="energie")
        Sponsorship.objects.create(
            sponsor=other_sponsor,
            hackathon=self.other_hackathon,
            tier=TierChoices.BRONZE,
            amount=Decimal("500.000"),
            status=StatusChoices.PROSPECT,
        )
        url = reverse("sponsors:sponsor_list")

        cases = [
            {"sector": "energie"},
            {"tier": TierChoices.BRONZE},
            {"hackathon": self.other_hackathon.pk},
        ]
        for params in cases:
            with self.subTest(params=params):
                response = self.client.get(url, params)
                self.assertEqual(response.status_code, 200)
                self.assertContains(response, "Energy Corp")
                self.assertNotContains(response, "Flow Corp")

    # ------------------------------------------------------------------
    # Sponsor CRUD
    # ------------------------------------------------------------------

    def test_sponsor_create_update_and_delete(self):
        create_url = reverse("sponsors:sponsor_create")
        response = self.client.post(
            create_url,
            {
                "name": "New Partner",
                "sector": "finance",
                "website": "https://new.example.com",
                "description": "A new partner.",
                "contact_name": "Sam",
                "contact_email": "sam@new.example.com",
            },
        )
        created = Sponsor.objects.get(name="New Partner")
        self.assertRedirects(
            response, reverse("sponsors:sponsor_detail", args=[created.pk])
        )

        update_url = reverse("sponsors:sponsor_update", args=[created.pk])
        self.assertEqual(self.client.get(update_url).status_code, 200)
        response = self.client.post(
            update_url,
            {
                "name": "Renamed Partner",
                "sector": "finance",
                "website": "https://new.example.com",
                "description": "Updated description.",
                "contact_name": "Sam",
                "contact_email": "sam@new.example.com",
            },
        )
        self.assertRedirects(
            response, reverse("sponsors:sponsor_detail", args=[created.pk])
        )
        created.refresh_from_db()
        self.assertEqual(created.name, "Renamed Partner")

        delete_url = reverse("sponsors:sponsor_delete", args=[created.pk])
        self.assertEqual(self.client.get(delete_url).status_code, 200)
        response = self.client.post(delete_url)
        self.assertRedirects(response, reverse("sponsors:sponsor_list"))
        self.assertFalse(Sponsor.objects.filter(pk=created.pk).exists())

    # ------------------------------------------------------------------
    # Sponsorship CRUD
    # ------------------------------------------------------------------

    def test_sponsorship_create_uses_initial_values_and_records_history(self):
        create_url = reverse("sponsors:sponsorship_create")
        response = self.client.get(
            create_url,
            {"sponsor_id": self.sponsor.pk, "hackathon_id": self.other_hackathon.pk},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["form"].initial["sponsor"], str(self.sponsor.pk))
        self.assertEqual(
            response.context["form"].initial["hackathon"], str(self.other_hackathon.pk)
        )

        response = self.client.post(
            create_url,
            {
                "sponsor": self.sponsor.pk,
                "hackathon": self.other_hackathon.pk,
                "tier": TierChoices.GOLD,
                "amount": "2500.000",
                "contribution_type": "financier",
                "notes": "New agreement.",
            },
        )
        self.assertRedirects(response, reverse("sponsors:dashboard"))

        created = Sponsorship.objects.get(
            sponsor=self.sponsor, hackathon=self.other_hackathon
        )
        history = StatusHistory.objects.get(sponsorship=created)
        self.assertEqual(history.old_status, "")
        self.assertEqual(history.new_status, StatusChoices.PROSPECT)
        self.assertEqual(history.changed_by, self.organizer)

    def test_sponsorship_update_and_delete(self):
        update_url = reverse("sponsors:sponsorship_update", args=[self.sponsorship.pk])
        self.assertEqual(self.client.get(update_url).status_code, 200)

        response = self.client.post(
            update_url,
            {
                "sponsor": self.sponsor.pk,
                "hackathon": self.hackathon.pk,
                "tier": TierChoices.SILVER,
                "amount": "1200.000",
                "contribution_type": "matériel",
                "notes": "Revised terms.",
            },
        )
        self.assertRedirects(response, reverse("sponsors:dashboard"))
        self.sponsorship.refresh_from_db()
        self.assertEqual(self.sponsorship.tier, TierChoices.SILVER)
        # Status edits are not part of the form contract; the service is the only writer.
        self.assertEqual(self.sponsorship.status, StatusChoices.CONFIRME)

        delete_url = reverse("sponsors:sponsorship_delete", args=[self.sponsorship.pk])
        self.assertEqual(self.client.get(delete_url).status_code, 200)
        response = self.client.post(delete_url)
        self.assertRedirects(response, reverse("sponsors:dashboard"))
        self.assertFalse(Sponsorship.objects.filter(pk=self.sponsorship.pk).exists())

    # ------------------------------------------------------------------
    # Status workflow
    # ------------------------------------------------------------------

    def test_change_status_with_invalid_value_is_ignored(self):
        url = reverse("sponsors:sponsorship_change_status", args=[self.sponsorship.pk])
        response = self.client.post(url, {"status": "not-a-status"})
        self.assertRedirects(response, reverse("sponsors:dashboard"))
        self.sponsorship.refresh_from_db()
        self.assertEqual(self.sponsorship.status, StatusChoices.CONFIRME)
        self.assertFalse(StatusHistory.objects.filter(sponsorship=self.sponsorship).exists())

    def test_change_status_htmx_returns_row_partial(self):
        url = reverse("sponsors:sponsorship_change_status", args=[self.sponsorship.pk])
        response = self.client.post(
            url,
            {"status": StatusChoices.NEGOCIATION},
            HTTP_HX_REQUEST="true",
        )
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "sponsors/partials/sponsorship_row.html")
        self.sponsorship.refresh_from_db()
        self.assertEqual(self.sponsorship.status, StatusChoices.NEGOCIATION)

    def test_change_status_redirects_to_next_parameter(self):
        url = reverse("sponsors:sponsorship_change_status", args=[self.sponsorship.pk])
        response = self.client.post(
            url,
            {"status": StatusChoices.NEGOCIATION, "next": reverse("sponsors:sponsor_list")},
        )
        self.assertRedirects(response, reverse("sponsors:sponsor_list"))

    # ------------------------------------------------------------------
    # Contact emails
    # ------------------------------------------------------------------

    def test_contact_get_with_hackathon_and_htmx(self):
        url = reverse("sponsors:sponsor_contact", args=[self.sponsor.pk])

        response = self.client.get(
            url,
            {"template_key": "relance", "hackathon": self.other_hackathon.pk},
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Second Hackathon")

        response = self.client.get(url, HTTP_HX_REQUEST="true")
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "sponsors/partials/sponsor_contact_form.html")

    def test_contact_invalid_form_is_redisplayed(self):
        url = reverse("sponsors:sponsor_contact", args=[self.sponsor.pk])
        response = self.client.post(url, {"subject": "", "message": ""})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(SponsorEmailLog.objects.count(), 0)
        self.assertEqual(mail.outbox, [])

    def test_contact_without_recipient_shows_error(self):
        self.sponsor.contact_email = ""
        self.sponsor.save(update_fields=["contact_email"])
        url = reverse("sponsors:sponsor_contact", args=[self.sponsor.pk])
        response = self.client.post(
            url, {"subject": "Hello", "message": "Trying to reach out."}
        )
        self.assertEqual(response.status_code, 200)
        log = SponsorEmailLog.objects.get(sponsor=self.sponsor)
        self.assertFalse(log.success)
        self.assertIn("No contact email", log.error_message)
        self.assertContains(response, "Unable to send email")

    # ------------------------------------------------------------------
    # AI + recommendations + export
    # ------------------------------------------------------------------

    def test_ai_generate_email_with_hackathon_context(self):
        url = reverse("sponsors:sponsor_ai_generate_email", args=[self.sponsor.pk])
        with patch(
            "sponsors.views.generate_prospecting_email",
            return_value={
                "subject": "AI subject",
                "body": "AI body",
                "ai_generated": True,
                "notice": "Generated locally.",
            },
        ) as generator:
            response = self.client.post(
                url,
                {
                    "template_key": "invitation",
                    "tone": "amical",
                    "hackathon": self.other_hackathon.pk,
                },
                HTTP_HX_REQUEST="true",
            )
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "sponsors/partials/sponsor_contact_form.html")
        self.assertContains(response, "AI subject")
        generator.assert_called_once()
        self.assertEqual(generator.call_args.kwargs["hackathon"], self.other_hackathon)

    def test_recommendations_endpoint(self):
        url = reverse("sponsors:sponsor_recommendations", args=[self.hackathon.pk])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "sponsors/partials/recommendations_block.html")

    def test_export_error_is_reported_and_redirects(self):
        url = reverse("sponsors:sponsor_export_excel")
        with patch(
            "sponsors.views.export_sponsorships_to_excel",
            side_effect=RuntimeError("openpyxl missing"),
        ):
            response = self.client.get(url, follow=True)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.redirect_chain,
            [(reverse("sponsors:sponsor_list"), 302)],
        )
        self.assertContains(response, "openpyxl missing")
