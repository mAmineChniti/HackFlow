"""Create demonstration sponsors, partnerships, and status history."""

import datetime
from decimal import Decimal

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from hackathons.models import Hackathon
from sponsors.models import (
    ContributionTypeChoices,
    Sponsor,
    Sponsorship,
    StatusChoices,
    StatusHistory,
    TierChoices,
)
from sponsors.permissions import can_manage_sponsors


DEMO_SUFFIX = "(demo)"
DEMO_HACKATHON_NAME = f"HackFlow Challenge {DEMO_SUFFIX}"

SPONSORS_DATA = [
    {
        "name": f"Northstar AI {DEMO_SUFFIX}",
        "sector": "tech",
        "website": "https://northstar-ai.example",
        "contact_name": "Alex Example",
        "contact_email": "alex@northstar-ai.example",
        "description": "A fictional technology company for local demonstrations.",
        "tier": TierChoices.PLATINUM,
        "amount": Decimal("15000.000"),
        "status": StatusChoices.CONFIRME,
        "contribution_type": ContributionTypeChoices.FINANCIER,
        "notes": "Demo record.",
        "history": [
            StatusChoices.PROSPECT,
            StatusChoices.CONTACTE,
            StatusChoices.NEGOCIATION,
            StatusChoices.CONFIRME,
        ],
    },
    {
        "name": f"Cedar Finance {DEMO_SUFFIX}",
        "sector": "finance",
        "website": "https://cedar-finance.example",
        "contact_name": "Jamie Example",
        "contact_email": "jamie@cedar-finance.example",
        "description": "A fictional finance company for local demonstrations.",
        "tier": TierChoices.GOLD,
        "amount": Decimal("8500.000"),
        "status": StatusChoices.CONFIRME,
        "contribution_type": ContributionTypeChoices.FINANCIER,
        "notes": "Demo record.",
        "history": [
            StatusChoices.PROSPECT,
            StatusChoices.NEGOCIATION,
            StatusChoices.CONFIRME,
        ],
    },
    {
        "name": f"Orbit Telecom {DEMO_SUFFIX}",
        "sector": "tech",
        "website": "https://orbit-telecom.example",
        "contact_name": "Morgan Example",
        "contact_email": "morgan@orbit-telecom.example",
        "description": "A fictional telecom company for local demonstrations.",
        "tier": TierChoices.SILVER,
        "amount": Decimal("5000.000"),
        "status": StatusChoices.NEGOCIATION,
        "contribution_type": ContributionTypeChoices.MATERIEL,
        "notes": "Demo record.",
        "history": [
            StatusChoices.PROSPECT,
            StatusChoices.CONTACTE,
            StatusChoices.NEGOCIATION,
        ],
    },
    {
        "name": f"Mosaic Health {DEMO_SUFFIX}",
        "sector": "sante",
        "website": "https://mosaic-health.example",
        "contact_name": "Taylor Example",
        "contact_email": "taylor@mosaic-health.example",
        "description": "A fictional healthcare company for local demonstrations.",
        "tier": TierChoices.BRONZE,
        "amount": Decimal("2500.000"),
        "status": StatusChoices.CONTACTE,
        "contribution_type": ContributionTypeChoices.PRIX,
        "notes": "Demo record.",
        "history": [
            StatusChoices.PROSPECT,
            StatusChoices.CONTACTE,
        ],
    },
    {
        "name": f"Veridian Systems {DEMO_SUFFIX}",
        "sector": "tech",
        "website": "https://veridian-systems.example",
        "contact_name": "Casey Example",
        "contact_email": "casey@veridian-systems.example",
        "description": "A fictional software company for local demonstrations.",
        "tier": TierChoices.BRONZE,
        "amount": Decimal("1500.000"),
        "status": StatusChoices.PROSPECT,
        "contribution_type": ContributionTypeChoices.MENTORS,
        "notes": "Demo record.",
        "history": [StatusChoices.PROSPECT],
    },
]


class Command(BaseCommand):
    help = "Create fictional demo sponsors and partnerships."

    def add_arguments(self, parser):
        parser.add_argument(
            "--force",
            action="store_true",
            help="Allow running when DEBUG is False.",
        )
        parser.add_argument(
            "--reset",
            action="store_true",
            help="Remove tagged demo records before recreating them.",
        )

    def handle(self, *args, **options):
        if not settings.DEBUG and not options["force"]:
            self.stderr.write(
                self.style.ERROR(
                    "Blocked: this command is restricted to DEBUG mode. "
                    "Pass --force to run it anyway."
                )
            )
            return

        with transaction.atomic():
            if options["reset"]:
                self.reset_demo_records()

            staff_user = next(
                (user for user in get_user_model().objects.all() if can_manage_sponsors(user)),
                None,
            )
            if staff_user is None:
                self.stderr.write(
                    self.style.ERROR(
                        "Blocked: no user with sponsor-management permission is "
                        "available to own the demo hackathon."
                    )
                )
                return

            now = timezone.now()
            hackathon, _ = Hackathon.objects.get_or_create(
                title=DEMO_HACKATHON_NAME,
                defaults={
                    "tagline": "Fictional AI and green technology demo",
                    "description": "A demo hackathon used by the sponsor seed command.",
                    "category": "AI & GreenTech",
                    "registration_start": now,
                    "registration_deadline": now + datetime.timedelta(days=14),
                    "start_date": now + datetime.timedelta(days=15),
                    "end_date": now + datetime.timedelta(days=17),
                    "organizer": staff_user,
                    "status": Hackathon.Status.REGISTRATION_OPEN,
                    "is_published": True,
                },
            )
            for sponsor_data in SPONSORS_DATA:
                data = sponsor_data.copy()
                history_statuses = data.pop("history")
                sponsor_defaults = {
                    key: data[key]
                    for key in (
                        "sector",
                        "website",
                        "contact_name",
                        "contact_email",
                        "description",
                    )
                }
                sponsor, _ = Sponsor.objects.update_or_create(
                    name=data["name"],
                    defaults=sponsor_defaults,
                )

                sponsorship, _ = Sponsorship.objects.update_or_create(
                    sponsor=sponsor,
                    hackathon=hackathon,
                    defaults={
                        "tier": data["tier"],
                        "amount": data["amount"],
                        "status": data["status"],
                        "contribution_type": data["contribution_type"],
                        "notes": data["notes"],
                    },
                )

                StatusHistory.objects.filter(sponsorship=sponsorship).delete()
                previous_status = None
                for status in history_statuses:
                    StatusHistory.objects.create(
                        sponsorship=sponsorship,
                        old_status=previous_status or status,
                        new_status=status,
                        changed_by=staff_user,
                    )
                    previous_status = status

        self.stdout.write(
            self.style.SUCCESS("Created or updated 5 tagged demo sponsors and their partnerships.")
        )

    def reset_demo_records(self):
        demo_hackathons = Hackathon.objects.filter(title=DEMO_HACKATHON_NAME)
        demo_sponsorships = Sponsorship.objects.filter(
            hackathon__in=demo_hackathons,
            sponsor__name__endswith=DEMO_SUFFIX,
        )
        partnership_count = demo_sponsorships.count()
        demo_sponsorships.delete()

        # Keep tagged records that still have non-demo relationships or logs.
        removable_sponsors = (
            Sponsor.objects.filter(name__endswith=DEMO_SUFFIX)
            .exclude(sponsorships__isnull=False)
            .exclude(email_logs__isnull=False)
        )
        sponsor_count = removable_sponsors.count()
        removable_sponsors.delete()

        removable_hackathons = demo_hackathons.exclude(sponsorships__isnull=False)
        hackathon_count = removable_hackathons.count()
        removable_hackathons.delete()

        self.stdout.write(
            "Reset tagged demo data: "
            f"{sponsor_count} sponsors, {partnership_count} partnerships, "
            f"{hackathon_count} hackathons removed."
        )
