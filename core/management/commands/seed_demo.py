"""Create a complete, idempotent demo dataset for HackFlow.

The command is safe to run repeatedly and is used by the web container at
startup when ``SEED_DEMO_DATA=True``. It creates:

* one account for every role, plus a small student cohort
* registrations, schedules and FAQs for several hackathons
* projects in every status/category, with teams, history and mentor advice
* sponsors, sponsorships, status history and email logs
* generated banner/logo images for the demo assets

Passwords are never hardcoded. They must come from ``DEMO_ADMIN_PASSWORD`` and
``DEMO_PASSWORD`` (or the corresponding command-line options), and both must be
at least 12 characters long.
"""

from __future__ import annotations

import io
from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone
from django.utils.text import slugify
from PIL import Image, ImageDraw, ImageFont

from accounts.models import Profile
from hackathons.models import (
    Hackathon,
    HackathonFAQ,
    HackathonRegistration,
    HackathonSchedule,
)
from projects.models import ConseilMentor, HistoriqueProjet, Project, ProjectMember
from sponsors.models import (
    ContributionTypeChoices,
    Sponsor,
    SponsorEmailLog,
    Sponsorship,
    StatusChoices,
    StatusHistory,
    TierChoices,
)

User = get_user_model()

EMAIL_DOMAIN = "hackflow.example"
PASSWORD_MIN_LENGTH = 12

# (username, first_name, last_name, role, is_staff, is_superuser)
DEMO_USERS = [
    ("admin", "Ada", "Admin", Profile.Role.ADMIN, True, True),
    ("organizer", "Ines", "Gharbi", Profile.Role.ORGANIZER, True, False),
    ("judge", "Karim", "Mansour", Profile.Role.JUDGE, False, False),
    ("mentor", "Leila", "Ben Salah", Profile.Role.MENTOR, False, False),
    ("student", "Yasmine", "Ben Ali", Profile.Role.STUDENT, False, False),
    ("sarah", "Sarah", "Trabelsi", Profile.Role.STUDENT, False, False),
    ("alex", "Alex", "Martin", Profile.Role.STUDENT, False, False),
    ("maya", "Maya", "Haddad", Profile.Role.STUDENT, False, False),
    ("nour", "Nour", "El Amri", Profile.Role.STUDENT, False, False),
    ("yassine", "Yassine", "Khelifi", Profile.Role.STUDENT, False, False),
]
DEMO_STUDENTS = [row[0] for row in DEMO_USERS if row[3] == Profile.Role.STUDENT]

PALETTES = [
    ((16, 185, 129), (5, 46, 40)),
    ((56, 189, 248), (15, 23, 42)),
    ((244, 114, 182), (76, 29, 149)),
    ((251, 191, 36), (120, 53, 15)),
    ((167, 139, 250), (30, 27, 75)),
    ((34, 211, 238), (8, 47, 73)),
]

SPONSOR_SPECS = [
    {
        "name": "Northstar AI (demo)",
        "sector": "tech",
        "website": "https://northstar-ai.example",
        "contact_name": "Alex Example",
        "contact_email": "alex@northstar-ai.example",
        "description": "A fictional AI platform supporting student builders.",
        "initials": "NA",
        "palette": 0,
        "hackathon": "active",
        "tier": TierChoices.PLATINUM,
        "amount": Decimal("15000.000"),
        "status": StatusChoices.CONFIRME,
        "contribution_type": ContributionTypeChoices.FINANCIER,
        "notes": "Demo sponsor: platinum partner for the flagship event.",
        "history": [
            StatusChoices.PROSPECT,
            StatusChoices.CONTACTE,
            StatusChoices.NEGOCIATION,
            StatusChoices.CONFIRME,
        ],
        "emails": [
            (
                "HackFlow Challenge 2026 — partnership confirmation",
                "Thank you for confirming the platinum partnership. We have reserved "
                "your demo booth and included your logo on the event page.",
                False,
            ),
            (
                "Demo day logistics and mentor slots",
                "Here is the final logistics pack for demo day, including mentor "
                "slots and the judging schedule.",
                True,
            ),
        ],
    },
    {
        "name": "Cedar Finance (demo)",
        "sector": "finance",
        "website": "https://cedar-finance.example",
        "contact_name": "Jamie Example",
        "contact_email": "jamie@cedar-finance.example",
        "description": "A fictional fintech sponsoring the student prize pool.",
        "initials": "CF",
        "palette": 1,
        "hackathon": "active",
        "tier": TierChoices.GOLD,
        "amount": Decimal("8500.000"),
        "status": StatusChoices.CONFIRME,
        "contribution_type": ContributionTypeChoices.FINANCIER,
        "notes": "Demo sponsor: gold partner, confirmed funding.",
        "history": [
            StatusChoices.PROSPECT,
            StatusChoices.NEGOCIATION,
            StatusChoices.CONFIRME,
        ],
        "emails": [
            (
                "Invoice and booth details",
                "Please find the sponsorship invoice and your booth allocation "
                "attached to this message.",
                False,
            ),
        ],
    },
    {
        "name": "Orbit Telecom (demo)",
        "sector": "tech",
        "website": "https://orbit-telecom.example",
        "contact_name": "Morgan Example",
        "contact_email": "morgan@orbit-telecom.example",
        "description": "A fictional telecom providing connectivity and devices.",
        "initials": "OT",
        "palette": 5,
        "hackathon": "completed",
        "tier": TierChoices.SILVER,
        "amount": Decimal("5000.000"),
        "status": StatusChoices.CONFIRME,
        "contribution_type": ContributionTypeChoices.MATERIEL,
        "notes": "Demo sponsor: connectivity and loaned hardware.",
        "history": [
            StatusChoices.PROSPECT,
            StatusChoices.CONTACTE,
            StatusChoices.CONFIRME,
        ],
        "emails": [],
    },
    {
        "name": "Mosaic Health (demo)",
        "sector": "sante",
        "website": "https://mosaic-health.example",
        "contact_name": "Taylor Example",
        "contact_email": "taylor@mosaic-health.example",
        "description": "A fictional health-tech company offering challenge prizes.",
        "initials": "MH",
        "palette": 2,
        "hackathon": "active",
        "tier": TierChoices.BRONZE,
        "amount": Decimal("2500.000"),
        "status": StatusChoices.CONTACTE,
        "contribution_type": ContributionTypeChoices.PRIX,
        "notes": "Demo sponsor: contacted, prize package under discussion.",
        "history": [
            StatusChoices.PROSPECT,
            StatusChoices.CONTACTE,
        ],
        "emails": [],
    },
    {
        "name": "Veridian Systems (demo)",
        "sector": "tech",
        "website": "https://veridian-systems.example",
        "contact_name": "Casey Example",
        "contact_email": "casey@veridian-systems.example",
        "description": "A fictional software company offering engineering mentors.",
        "initials": "VS",
        "palette": 4,
        "hackathon": "ongoing",
        "tier": TierChoices.BRONZE,
        "amount": Decimal("1500.000"),
        "status": StatusChoices.PROSPECT,
        "contribution_type": ContributionTypeChoices.MENTORS,
        "notes": "Demo sponsor: prospect, mentor contribution proposed.",
        "history": [StatusChoices.PROSPECT],
        "emails": [],
    },
    {
        "name": "Atlas Cloud (demo)",
        "sector": "tech",
        "website": "https://atlas-cloud.example",
        "contact_name": "Jordan Example",
        "contact_email": "jordan@atlas-cloud.example",
        "description": "A fictional cloud provider sponsoring infrastructure credits.",
        "initials": "AC",
        "palette": 1,
        "hackathon": "ongoing",
        "tier": TierChoices.PLATINUM,
        "amount": Decimal("12000.000"),
        "status": StatusChoices.CONFIRME,
        "contribution_type": ContributionTypeChoices.FINANCIER,
        "notes": "Demo sponsor: platinum partner for the campus sprint.",
        "history": [
            StatusChoices.PROSPECT,
            StatusChoices.CONTACTE,
            StatusChoices.NEGOCIATION,
            StatusChoices.CONFIRME,
        ],
        "emails": [],
    },
    {
        "name": "Nova Energy (demo)",
        "sector": "energie",
        "website": "https://nova-energy.example",
        "contact_name": "Riley Example",
        "contact_email": "riley@nova-energy.example",
        "description": "A fictional cleantech company evaluating a gold partnership.",
        "initials": "NE",
        "palette": 3,
        "hackathon": "active",
        "tier": TierChoices.GOLD,
        "amount": Decimal("6000.000"),
        "status": StatusChoices.NEGOCIATION,
        "contribution_type": ContributionTypeChoices.FINANCIER,
        "notes": "Demo sponsor: negotiation in progress.",
        "history": [
            StatusChoices.PROSPECT,
            StatusChoices.CONTACTE,
            StatusChoices.NEGOCIATION,
        ],
        "emails": [
            (
                "Follow-up on the partnership proposal",
                "Thanks for the productive call. We are reviewing the gold package "
                "and will confirm the final scope this week.",
                True,
            ),
        ],
    },
    {
        "name": "Quantum Retail (demo)",
        "sector": "retail",
        "website": "https://quantum-retail.example",
        "contact_name": "Sam Example",
        "contact_email": "sam@quantum-retail.example",
        "description": "A fictional retailer that declined this edition.",
        "initials": "QR",
        "palette": 2,
        "hackathon": "ongoing",
        "tier": TierChoices.SILVER,
        "amount": Decimal("4000.000"),
        "status": StatusChoices.REFUSE,
        "contribution_type": ContributionTypeChoices.FINANCIER,
        "notes": "Demo sponsor: declined, useful for the pipeline history.",
        "history": [
            StatusChoices.PROSPECT,
            StatusChoices.CONTACTE,
            StatusChoices.NEGOCIATION,
            StatusChoices.REFUSE,
        ],
        "emails": [],
    },
    {
        "name": "GreenLeaf Labs (demo)",
        "sector": "energie",
        "website": "https://greenleaf-labs.example",
        "contact_name": "Avery Example",
        "contact_email": "avery@greenleaf-labs.example",
        "description": "A fictional climate lab sponsoring the GreenTech track.",
        "initials": "GL",
        "palette": 0,
        "hackathon": "completed",
        "tier": TierChoices.BRONZE,
        "amount": Decimal("2000.000"),
        "status": StatusChoices.CONFIRME,
        "contribution_type": ContributionTypeChoices.PRIX,
        "notes": "Demo sponsor: confirmed GreenTech prize sponsor.",
        "history": [
            StatusChoices.PROSPECT,
            StatusChoices.CONTACTE,
            StatusChoices.NEGOCIATION,
            StatusChoices.CONFIRME,
        ],
        "emails": [],
    },
]


def _font(size: int):
    """Return a usable font without relying on system font packages."""
    try:
        return ImageFont.load_default(size=size)
    except TypeError:  # pragma: no cover - older Pillow fallback
        return ImageFont.load_default()


def _wrap_text(draw, text: str, font, max_width: int) -> list[str]:
    words = text.split()
    lines: list[str] = []
    current = ""
    for word in words:
        candidate = f"{current} {word}".strip()
        box = draw.textbbox((0, 0), candidate, font=font)
        if box[2] - box[0] <= max_width or not current:
            current = candidate
        else:
            lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines


def _png_bytes(image: Image.Image) -> bytes:
    buffer = io.BytesIO()
    image.save(buffer, format="PNG", optimize=True)
    return buffer.getvalue()


def _gradient(size: tuple[int, int], start, end):
    image = Image.new("RGB", size)
    draw = ImageDraw.Draw(image)
    width, height = size
    for y in range(height):
        ratio = y / max(height - 1, 1)
        color = tuple(
            round(start[channel] + (end[channel] - start[channel]) * ratio) for channel in range(3)
        )
        draw.line((0, y, width, y), fill=color)
    return image, draw


def _make_banner(title: str, subtitle: str, palette_index: int) -> bytes:
    start, end = PALETTES[palette_index % len(PALETTES)]
    image, draw = _gradient((1200, 600), start, end)
    draw.rectangle((0, 470, 1200, 600), fill=(8, 12, 24))
    draw.ellipse((900, -160, 1320, 260), outline=(255, 255, 255), width=3)
    draw.ellipse((960, -100, 1260, 200), outline=(255, 255, 255), width=1)

    title_font = _font(62)
    subtitle_font = _font(26)
    label_font = _font(22)

    y = 105
    for line in _wrap_text(draw, title, title_font, 1020)[:2]:
        draw.text((72, y), line, font=title_font, fill=(255, 255, 255))
        y += 76

    y += 8
    for line in _wrap_text(draw, subtitle, subtitle_font, 1000)[:2]:
        draw.text((75, y), line, font=subtitle_font, fill=(214, 255, 183))
        y += 36

    draw.text((75, 525), "HackFlow · demo data", font=label_font, fill=(160, 174, 192))
    return _png_bytes(image)


def _make_logo(initials: str, palette_index: int) -> bytes:
    start, end = PALETTES[palette_index % len(PALETTES)]
    image, draw = _gradient((512, 512), start, end)
    draw.rounded_rectangle((30, 30, 482, 482), radius=96, outline=(255, 255, 255), width=6)
    font = _font(176)
    box = draw.textbbox((0, 0), initials, font=font)
    width = box[2] - box[0]
    height = box[3] - box[1]
    draw.text(
        ((512 - width) / 2, (512 - height) / 2 - box[1]),
        initials,
        font=font,
        fill=(255, 255, 255),
    )
    return _png_bytes(image)


def _ensure_image(field, filename: str, content: bytes) -> bool:
    """Attach a generated image only when the file is missing."""
    if field and field.name:
        try:
            if field.storage.exists(field.name):
                return False
        except Exception:
            pass
    field.save(filename, ContentFile(content), save=True)
    return True


def _upsert_first(model, lookup: dict, defaults: dict):
    """Update the first matching row, or create one when none exists."""
    instance = model.objects.filter(**lookup).order_by("pk").first()
    if instance is None:
        return model.objects.create(**{**lookup, **defaults}), True
    for field, value in defaults.items():
        setattr(instance, field, value)
    instance.save()
    return instance, False


def _submission_entry(user, date) -> dict:
    return {
        "type": "submission",
        "action": "First project submission",
        "user": user.get_username(),
        "date": date.isoformat(),
        "date_display": date.strftime("%b %d, %Y at %H:%M"),
        "reviewed_at": date.isoformat(),
        "reviewed_at_display": date.strftime("%b %d, %Y at %H:%M"),
    }


def _decision_entry(user, date, decision: str, reason: str = "") -> dict:
    display = "Accepted" if decision == "accept" else "Rejected"
    return {
        "type": "decision",
        "decision": decision,
        "decision_display": display,
        "reason": reason,
        "reviewed_by": user.get_username(),
        "reviewed_at": date.isoformat(),
        "reviewed_at_display": date.strftime("%b %d, %Y at %H:%M"),
        "date": date.isoformat(),
        "date_display": date.strftime("%b %d, %Y at %H:%M"),
    }


class Command(BaseCommand):
    help = "Create or refresh the complete HackFlow demo dataset (idempotent)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--password",
            default="",
            help=(
                "Password for non-admin demo users. Defaults to the "
                "DEMO_PASSWORD environment variable."
            ),
        )
        parser.add_argument(
            "--admin-password",
            default="",
            help=(
                "Password for the demo admin. Defaults to the "
                "DEMO_ADMIN_PASSWORD environment variable."
            ),
        )
        parser.add_argument(
            "--reset-passwords",
            action="store_true",
            help="Reset passwords for demo users that already exist.",
        )
        parser.add_argument(
            "--skip-media",
            action="store_true",
            help="Do not generate demo banner and logo images.",
        )

    def handle(self, *args, **options):
        import os

        admin_password = (options["admin_password"] or os.getenv("DEMO_ADMIN_PASSWORD", "")).strip()
        user_password = (options["password"] or os.getenv("DEMO_PASSWORD", "")).strip()

        if len(admin_password) < PASSWORD_MIN_LENGTH:
            raise CommandError(
                "DEMO_ADMIN_PASSWORD must be set to at least "
                f"{PASSWORD_MIN_LENGTH} characters (or pass --admin-password)."
            )
        if len(user_password) < PASSWORD_MIN_LENGTH:
            raise CommandError(
                "DEMO_PASSWORD must be set to at least "
                f"{PASSWORD_MIN_LENGTH} characters (or pass --password)."
            )

        now = timezone.now()
        with transaction.atomic():
            users = self._seed_users(
                now,
                admin_password=admin_password,
                user_password=user_password,
                reset_passwords=options["reset_passwords"],
            )
            hackathons = self._seed_hackathons(
                now,
                users,
                generate_media=not options["skip_media"],
            )
            self._seed_registrations(now, users, hackathons)
            projects = self._seed_projects(now, users, hackathons)
            sponsors = self._seed_sponsors(
                now,
                users,
                hackathons,
                generate_media=not options["skip_media"],
            )

        self._report(users, hackathons, projects, sponsors)

    # ------------------------------------------------------------------
    # Users
    # ------------------------------------------------------------------

    def _seed_users(self, now, *, admin_password, user_password, reset_passwords):
        users = {}
        for username, first_name, last_name, role, is_staff, is_superuser in DEMO_USERS:
            user, created = User.objects.get_or_create(
                username=username,
                defaults={
                    "email": f"{username}@{EMAIL_DOMAIN}",
                    "first_name": first_name,
                    "last_name": last_name,
                    "is_active": True,
                },
            )
            user.email = f"{username}@{EMAIL_DOMAIN}"
            user.first_name = first_name
            user.last_name = last_name
            user.is_active = True
            user.is_staff = is_staff
            user.is_superuser = is_superuser

            password = admin_password if role == Profile.Role.ADMIN else user_password
            if created or reset_passwords:
                user.set_password(password)
            user.save()

            profile, _ = Profile.objects.get_or_create(user=user)
            profile.role = role
            if not profile.email_verified or not profile.email_verified_at:
                profile.email_verified = True
                profile.email_verified_at = now
            profile.save()
            users[username] = user

        return users

    # ------------------------------------------------------------------
    # Hackathons
    # ------------------------------------------------------------------

    def _seed_hackathons(self, now, users, *, generate_media: bool):
        organizer = users["organizer"]
        specs = [
            {
                "slug": "hackflow-challenge-2026",
                "title": "HackFlow Challenge 2026",
                "tagline": "Build what tomorrow's campus needs.",
                "description": (
                    "The flagship HackFlow edition brings students, mentors and "
                    "sponsors together for a 48-hour build sprint. Teams ship an "
                    "AI, web, IoT or GreenTech product and pitch it to a jury."
                ),
                "category": "AI & GreenTech",
                "registration_start": now - timedelta(days=20),
                "registration_deadline": now + timedelta(days=10),
                "start_date": now + timedelta(days=14),
                "end_date": now + timedelta(days=16),
                "mode": Hackathon.Mode.HYBRID,
                "location": "ESPRIT Campus, Tunis + Discord",
                "max_participants": 120,
                "min_team_size": 2,
                "max_team_size": 4,
                "prize_pool": "$15,000 + incubation",
                "difficulty": Hackathon.Difficulty.ALL_LEVELS,
                "rules": (
                    "Teams of 2–4. All code must be written during the event. "
                    "Open-source libraries are welcome. Be kind and follow the "
                    "code of conduct."
                ),
                "resources_link": "https://github.com/hackflow-demo/resources",
                "contact_email": "organizer@hackflow.example",
                "status": Hackathon.Status.REGISTRATION_OPEN,
                "is_published": True,
                "palette": 0,
                "schedule": [
                    ("Check-in & opening", "Registration desk, team matching and kickoff.", 0, 9),
                    ("Mentor office hours", "Product, AI and backend mentors available.", 0, 14),
                    ("Midnight build check", "Progress demos and snacks.", 1, 0),
                    ("Pitch rehearsal", "Rehearse the 3-minute demo with mentors.", 1, 16),
                    (
                        "Final pitches & awards",
                        "Jury demos followed by the awards ceremony.",
                        2,
                        10,
                    ),
                ],
                "faqs": [
                    (
                        "Who can join?",
                        "Any student or recent graduate curious about building. "
                        "You can join alone and find a team during the opening.",
                    ),
                    (
                        "Do I need a team?",
                        "No. Teams of 2–4 are allowed; solo builders can use the "
                        "team-matching session at check-in.",
                    ),
                    (
                        "What should I bring?",
                        "Your laptop, charger and student ID. Meals, Wi-Fi and "
                        "mentor support are provided.",
                    ),
                    (
                        "How is the demo judged?",
                        "Jury members score impact, technical execution, product "
                        "clarity and the quality of the live pitch.",
                    ),
                ],
            },
            {
                "slug": "smart-campus-sprint-2026",
                "title": "Smart Campus Sprint 2026",
                "tagline": "Make the campus smarter in one weekend.",
                "description": (
                    "A fast, in-person sprint focused on IoT, sustainability and "
                    "student life. Teams prototype sensors, dashboards and services "
                    "for the ESPRIT campus."
                ),
                "category": "IoT & Sustainability",
                "registration_start": now - timedelta(days=60),
                "registration_deadline": now - timedelta(days=10),
                "start_date": now - timedelta(days=1),
                "end_date": now + timedelta(days=2),
                "mode": Hackathon.Mode.IN_PERSON,
                "location": "ESPRIT Innovation Lab",
                "max_participants": 5,
                "min_team_size": 2,
                "max_team_size": 3,
                "prize_pool": "5,000 TND + hardware kits",
                "difficulty": Hackathon.Difficulty.INTERMEDIATE,
                "rules": (
                    "Use the provided sensors responsibly and document your wiring. "
                    "Teams must demo a working prototype."
                ),
                "resources_link": "https://github.com/hackflow-demo/iot-starter",
                "contact_email": "organizer@hackflow.example",
                "status": Hackathon.Status.ONGOING,
                "is_published": True,
                "palette": 1,
                "schedule": [
                    (
                        "Check-in & kit pickup",
                        "Participant badges, sensors and safety briefing.",
                        0,
                        8,
                    ),
                    ("Hacking begins", "Teams start building in the innovation lab.", 0, 10),
                    ("Mentor checkpoint", "Review architecture and scope with mentors.", 1, 11),
                    ("Prototype demos", "Three-minute demos to the jury.", 2, 15),
                ],
                "faqs": [
                    (
                        "Is hardware provided?",
                        "Yes, a limited sensor kit is available. Bring your own "
                        "laptop and any extra components you want to use.",
                    ),
                    (
                        "Can I join remotely?",
                        "This edition is in-person only because the hardware kits stay in the lab.",
                    ),
                    (
                        "Where do I check in?",
                        "Use the check-in desk on the hackathon page or scan the "
                        "QR badge you receive after registration.",
                    ),
                ],
            },
            {
                "slug": "esprit-ai-hackathon-2025",
                "title": "ESPRIT AI Hackathon 2025",
                "tagline": "A finished edition full of AI prototypes.",
                "description": (
                    "The previous AI-focused edition. Projects explored healthcare, "
                    "education and climate, and the winners are preserved here as "
                    "reference demos."
                ),
                "category": "Artificial Intelligence",
                "registration_start": now - timedelta(days=220),
                "registration_deadline": now - timedelta(days=190),
                "start_date": now - timedelta(days=180),
                "end_date": now - timedelta(days=178),
                "mode": Hackathon.Mode.IN_PERSON,
                "location": "ESPRIT Auditorium",
                "max_participants": 200,
                "min_team_size": 2,
                "max_team_size": 4,
                "prize_pool": "10,000 TND",
                "difficulty": Hackathon.Difficulty.ADVANCED,
                "rules": (
                    "All models and datasets had to be documented. The jury "
                    "evaluated technical depth, novelty and responsible AI."
                ),
                "resources_link": "https://github.com/hackflow-demo/ai-2025",
                "contact_email": "organizer@hackflow.example",
                "status": Hackathon.Status.FINISHED,
                "is_published": True,
                "palette": 2,
                "schedule": [
                    ("Opening keynote", "AI for public good.", 0, 9),
                    ("Dataset clinic", "Office hours with data mentors.", 0, 15),
                    ("Final demos", "Eight finalist teams pitch.", 2, 10),
                    ("Awards", "Winners announced.", 2, 16),
                ],
                "faqs": [
                    (
                        "Can I reuse a project from another hackathon?",
                        "No. The project had to be built specifically for this event, "
                        "though open-source libraries were allowed.",
                    ),
                    (
                        "Are the winning projects public?",
                        "Yes. The finalist and winner projects are visible in the "
                        "project gallery as reference demos.",
                    ),
                ],
            },
            {
                "slug": "cybershield-ctf-2027",
                "title": "CyberShield CTF 2027",
                "tagline": "A draft capture-the-flag edition.",
                "description": (
                    "An upcoming cybersecurity capture-the-flag event. This record "
                    "is intentionally unpublished so organizers can demo draft "
                    "workflows before the public launch."
                ),
                "category": "Cybersecurity",
                "registration_start": now + timedelta(days=30),
                "registration_deadline": now + timedelta(days=60),
                "start_date": now + timedelta(days=70),
                "end_date": now + timedelta(days=72),
                "mode": Hackathon.Mode.ONLINE,
                "location": "HackFlow CTF platform",
                "max_participants": 80,
                "min_team_size": 1,
                "max_team_size": 4,
                "prize_pool": "Certificates + swag",
                "difficulty": Hackathon.Difficulty.ADVANCED,
                "rules": "No attacks against the platform or other teams.",
                "resources_link": "https://github.com/hackflow-demo/ctf",
                "contact_email": "organizer@hackflow.example",
                "status": Hackathon.Status.DRAFT,
                "is_published": False,
                "palette": 4,
                "schedule": [
                    ("Draft planning", "Internal planning session.", 0, 10),
                ],
                "faqs": [
                    (
                        "Is this event public?",
                        "Not yet. The organizer can publish it after the programme "
                        "and challenges are ready.",
                    ),
                ],
            },
            {
                "slug": "healthtech-sprint-2026",
                "title": "HealthTech Sprint 2026",
                "tagline": "Cancelled edition kept for status demos.",
                "description": (
                    "A cancelled health-tech edition. It demonstrates the cancelled "
                    "state and is excluded from the landing-page statistics."
                ),
                "category": "HealthTech",
                "registration_start": now - timedelta(days=5),
                "registration_deadline": now + timedelta(days=5),
                "start_date": now + timedelta(days=10),
                "end_date": now + timedelta(days=12),
                "mode": Hackathon.Mode.HYBRID,
                "location": "ESPRIT Campus + Discord",
                "max_participants": 60,
                "min_team_size": 2,
                "max_team_size": 4,
                "prize_pool": "TBA",
                "difficulty": Hackathon.Difficulty.BEGINNER,
                "rules": "Event cancelled; this record is for demo purposes.",
                "resources_link": "https://github.com/hackflow-demo/healthtech",
                "contact_email": "organizer@hackflow.example",
                "status": Hackathon.Status.CANCELLED,
                "is_published": True,
                "palette": 3,
                "schedule": [],
                "faqs": [
                    (
                        "Why was the event cancelled?",
                        "The demo record shows how a cancelled event appears in the "
                        "catalogue without counting toward the live statistics.",
                    ),
                ],
            },
        ]

        hackathons = {}
        for index, spec in enumerate(specs):
            schedule = spec.pop("schedule")
            faqs = spec.pop("faqs")
            palette = spec.pop("palette")
            slug = spec.pop("slug")
            hackathon_fields = {**spec, "organizer": organizer}
            hackathon, _ = Hackathon.objects.update_or_create(
                slug=slug,
                defaults=hackathon_fields,
            )
            hackathon.judges.add(users["judge"])
            hackathon.mentors.add(users["mentor"])

            if generate_media:
                _ensure_image(
                    hackathon.banner_image,
                    f"banner-{hackathon.slug}.png",
                    _make_banner(
                        hackathon.title,
                        hackathon.tagline,
                        palette if index < len(PALETTES) else index,
                    ),
                )

            for order, (title, description, days, hours) in enumerate(schedule):
                scheduled_at = hackathon.start_date + timedelta(days=days, hours=hours)
                _upsert_first(
                    HackathonSchedule,
                    {"hackathon": hackathon, "title": title},
                    {"description": description, "scheduled_at": scheduled_at},
                )

            for order, (question, answer) in enumerate(faqs):
                _upsert_first(
                    HackathonFAQ,
                    {"hackathon": hackathon, "question": question},
                    {"answer": answer, "order": order},
                )

            key = {
                "hackflow-challenge-2026": "active",
                "smart-campus-sprint-2026": "ongoing",
                "esprit-ai-hackathon-2025": "completed",
                "cybershield-ctf-2027": "draft",
                "healthtech-sprint-2026": "cancelled",
            }[slug]
            hackathons[key] = hackathon

        return hackathons

    # ------------------------------------------------------------------
    # Registrations
    # ------------------------------------------------------------------

    def _seed_registrations(self, now, users, hackathons):
        confirmed_groups = {
            "active": DEMO_STUDENTS,
            "ongoing": ["student", "sarah", "alex", "maya", "nour"],
            "completed": DEMO_STUDENTS,
        }
        waitlist_groups = {"ongoing": ["yassine"]}
        checked_in_groups = {
            "ongoing": {"student", "sarah", "alex"},
            "completed": set(DEMO_STUDENTS),
        }

        for key, usernames in confirmed_groups.items():
            hackathon = hackathons[key]
            for index, username in enumerate(usernames):
                self._upsert_registration(
                    hackathon,
                    users[username],
                    status=HackathonRegistration.Status.CONFIRMED,
                    checked_in=username in checked_in_groups.get(key, set()),
                    index=index,
                    now=now,
                )
            for index, username in enumerate(waitlist_groups.get(key, [])):
                self._upsert_registration(
                    hackathon,
                    users[username],
                    status=HackathonRegistration.Status.WAITLIST,
                    checked_in=False,
                    index=index + len(usernames),
                    now=now,
                )

    def _upsert_registration(self, hackathon, user, *, status, checked_in, index, now):
        skills = [
            "Python, Django, PostgreSQL",
            "React, TypeScript, Tailwind",
            "Figma, product design, user research",
            "PyTorch, NLP, data pipelines",
            "ESP32, sensors, embedded C",
            "Next.js, Supabase, UX writing",
        ]
        study_levels = [
            HackathonRegistration.StudyLevel.ING3,
            HackathonRegistration.StudyLevel.M2,
            HackathonRegistration.StudyLevel.M1,
            HackathonRegistration.StudyLevel.ING2,
            HackathonRegistration.StudyLevel.L3,
            HackathonRegistration.StudyLevel.ING1,
        ]
        experience_levels = [
            HackathonRegistration.ExperienceLevel.ADVANCED,
            HackathonRegistration.ExperienceLevel.INTERMEDIATE,
            HackathonRegistration.ExperienceLevel.INTERMEDIATE,
            HackathonRegistration.ExperienceLevel.ADVANCED,
            HackathonRegistration.ExperienceLevel.BEGINNER,
            HackathonRegistration.ExperienceLevel.INTERMEDIATE,
        ]
        checked_in_at = None
        if checked_in:
            checked_in_at = hackathon.start_date + timedelta(hours=8, minutes=index * 7)
            if checked_in_at > now:
                checked_in_at = now - timedelta(hours=2)

        defaults = {
            "status": status,
            "university": "ESPRIT School of Engineering",
            "study_level": study_levels[index % len(study_levels)],
            "skills": skills[index % len(skills)],
            "experience_level": experience_levels[index % len(experience_levels)],
            "seeking_team": index % 3 == 0,
            "tshirt_dietary": "M / No dietary restrictions",
            "portfolio_url": f"https://github.com/hackflow-demo/{user.username}",
            "motivation": (
                "I want to build a useful prototype with a multidisciplinary team "
                "and learn from the mentors."
            ),
            "accepted_rules": True,
            "ticket_code": (f"HF-DEMO-{hackathon.slug[:14].upper()}-{user.username[:8].upper()}"),
            "checked_in": checked_in,
            "checked_in_at": checked_in_at,
        }
        HackathonRegistration.objects.update_or_create(
            hackathon=hackathon,
            participant=user,
            defaults=defaults,
        )

    # ------------------------------------------------------------------
    # Projects
    # ------------------------------------------------------------------

    def _seed_projects(self, now, users, hackathons):
        organizer = users["organizer"]
        active = hackathons["active"]
        ongoing = hackathons["ongoing"]
        completed = hackathons["completed"]

        specs = [
            {
                "slug": "campus-compass",
                "title": "Campus Compass",
                "tagline": "A personalised campus navigation and services app.",
                "description": (
                    "Campus Compass helps new students find classrooms, labs, "
                    "administrative offices and student services. It combines an "
                    "interactive map with opening hours, accessibility data and a "
                    "small AI assistant for common questions."
                ),
                "category": Project.Category.WEB,
                "hackathon": active.title,
                "status": Project.Status.DRAFT,
                "deadline": now + timedelta(days=21),
                "score": None,
                "submitted_at": None,
                "reviewed_at": None,
                "rejection_reason": "",
                "team": [
                    ("student", ProjectMember.Role.CHEF_DE_PROJET),
                    ("sarah", ProjectMember.Role.DEVELOPPEUR),
                    ("alex", ProjectMember.Role.DESIGNER),
                ],
                "history": [],
                "advice": [],
            },
            {
                "slug": "medisync-ai",
                "title": "MediSync AI",
                "tagline": "Turn messy clinical notes into clear care summaries.",
                "description": (
                    "MediSync AI extracts medication, allergies and follow-up tasks "
                    "from free-text notes, then produces a structured summary for "
                    "care teams. The prototype includes a human-review step and a "
                    "synthetic-data evaluation report."
                ),
                "category": Project.Category.AI,
                "hackathon": active.title,
                "status": Project.Status.SUBMITTED,
                "deadline": now + timedelta(days=14),
                "score": None,
                "submitted_at": now - timedelta(days=2),
                "reviewed_at": None,
                "rejection_reason": "",
                "team": [
                    ("sarah", ProjectMember.Role.CHEF_DE_PROJET),
                    ("student", ProjectMember.Role.DEVELOPPEUR),
                    ("maya", ProjectMember.Role.DEVELOPPEUR),
                ],
                "history": [
                    (
                        HistoriqueProjet.Action.SUBMITTED,
                        "sarah",
                        "",
                        now - timedelta(days=2),
                    ),
                ],
                "advice": [],
            },
            {
                "slug": "agripulse-iot",
                "title": "AgriPulse IoT",
                "tagline": "Low-cost soil sensors for smarter irrigation.",
                "description": (
                    "AgriPulse pairs an ESP32 sensor node with a Django dashboard. "
                    "It tracks soil moisture and temperature, raises low-water "
                    "alerts and suggests irrigation windows based on weather data."
                ),
                "category": Project.Category.IOT,
                "hackathon": active.title,
                "status": Project.Status.UNDER_REVIEW,
                "deadline": now + timedelta(days=7),
                "score": None,
                "submitted_at": now - timedelta(days=5),
                "reviewed_at": None,
                "rejection_reason": "",
                "team": [
                    ("alex", ProjectMember.Role.CHEF_DE_PROJET),
                    ("nour", ProjectMember.Role.DEVELOPPEUR),
                    ("student", ProjectMember.Role.DESIGNER),
                ],
                "history": [
                    (
                        HistoriqueProjet.Action.SUBMITTED,
                        "alex",
                        "",
                        now - timedelta(days=5),
                    ),
                    (
                        HistoriqueProjet.Action.UNDER_REVIEW,
                        "organizer",
                        "Technical review started.",
                        now - timedelta(days=1),
                    ),
                ],
                "advice": [
                    (
                        "Your sensor calibration section is strong. Add a failure "
                        "mode for Wi-Fi loss and a short data-retention note before "
                        "the final pitch."
                    ),
                ],
            },
            {
                "slug": "ecoroute",
                "title": "EcoRoute",
                "tagline": "Plan the lowest-carbon route across campus.",
                "description": (
                    "EcoRoute compares walking, shuttle and bike routes by carbon "
                    "cost and travel time. The mobile-first prototype includes "
                    "accessibility filters and a leaderboard for sustainable trips."
                ),
                "category": Project.Category.GREEN,
                "hackathon": ongoing.title,
                "status": Project.Status.ACCEPTED,
                "deadline": now - timedelta(days=10),
                "score": 8,
                "submitted_at": now - timedelta(days=20),
                "reviewed_at": now - timedelta(days=15),
                "rejection_reason": "",
                "team": [
                    ("maya", ProjectMember.Role.CHEF_DE_PROJET),
                    ("sarah", ProjectMember.Role.DEVELOPPEUR),
                    ("yassine", ProjectMember.Role.DESIGNER),
                ],
                "history": [
                    (
                        HistoriqueProjet.Action.SUBMITTED,
                        "maya",
                        "",
                        now - timedelta(days=20),
                    ),
                    (
                        HistoriqueProjet.Action.ACCEPTED,
                        "organizer",
                        "",
                        now - timedelta(days=15),
                    ),
                ],
                "advice": [
                    (
                        "The carbon model needs a clear source for emission factors. "
                        "Document the assumptions and add a fallback when location "
                        "permission is denied."
                    ),
                    (
                        "Your onboarding is clear. Prepare a 30-second story for the "
                        "jury that starts with the student problem, not the algorithm."
                    ),
                ],
            },
            {
                "slug": "chainvote",
                "title": "ChainVote",
                "tagline": "Verifiable student elections with a simple audit trail.",
                "description": (
                    "ChainVote explores verifiable campus elections. The prototype "
                    "uses signed ballots and an append-only audit log while keeping "
                    "voter identities private."
                ),
                "category": Project.Category.CYBER,
                "hackathon": ongoing.title,
                "status": Project.Status.REJECTED,
                "deadline": now - timedelta(days=10),
                "score": 4,
                "submitted_at": now - timedelta(days=22),
                "reviewed_at": now - timedelta(days=18),
                "rejection_reason": (
                    "The prototype did not demonstrate a working ballot-verification "
                    "flow end to end, and the threat model was incomplete."
                ),
                "team": [
                    ("nour", ProjectMember.Role.CHEF_DE_PROJET),
                    ("alex", ProjectMember.Role.DEVELOPPEUR),
                    ("student", ProjectMember.Role.DESIGNER),
                ],
                "history": [
                    (
                        HistoriqueProjet.Action.SUBMITTED,
                        "nour",
                        "",
                        now - timedelta(days=22),
                    ),
                    (
                        HistoriqueProjet.Action.REJECTED,
                        "organizer",
                        "Incomplete ballot-verification demo and threat model.",
                        now - timedelta(days=18),
                    ),
                ],
                "advice": [
                    (
                        "The problem is important, but the demo stopped at the UI. "
                        "Focus the resubmission on one verifiable ballot path and an "
                        "explicit threat model."
                    ),
                ],
            },
            {
                "slug": "signbridge",
                "title": "SignBridge",
                "tagline": "Real-time sign-language captions for campus talks.",
                "description": (
                    "SignBridge turns spoken talks into live captions and simple "
                    "sign-language prompts. It was built with accessibility "
                    "advocates and tested on recorded campus presentations."
                ),
                "category": Project.Category.MOBILE,
                "hackathon": completed.title,
                "status": Project.Status.FINALIST,
                "deadline": now - timedelta(days=40),
                "score": 9,
                "submitted_at": now - timedelta(days=60),
                "reviewed_at": now - timedelta(days=50),
                "rejection_reason": "",
                "team": [
                    ("student", ProjectMember.Role.CHEF_DE_PROJET),
                    ("maya", ProjectMember.Role.DEVELOPPEUR),
                    ("nour", ProjectMember.Role.DESIGNER),
                ],
                "history": [
                    (
                        HistoriqueProjet.Action.SUBMITTED,
                        "student",
                        "",
                        now - timedelta(days=60),
                    ),
                    (
                        HistoriqueProjet.Action.ACCEPTED,
                        "organizer",
                        "",
                        now - timedelta(days=50),
                    ),
                    (
                        HistoriqueProjet.Action.FINALIST,
                        "organizer",
                        "Selected for the final pitch.",
                        now - timedelta(days=45),
                    ),
                ],
                "advice": [
                    (
                        "The accessibility testing notes are excellent. Add latency "
                        "numbers and a plan for low-bandwidth classrooms."
                    ),
                ],
            },
            {
                "slug": "neuronotes",
                "title": "NeuroNotes",
                "tagline": "AI study notes that adapt to how you learn.",
                "description": (
                    "NeuroNotes converts lecture material into structured notes, "
                    "flashcards and short quizzes. The winner of the previous AI "
                    "edition used a retrieval pipeline with citation checks."
                ),
                "category": Project.Category.AI,
                "hackathon": completed.title,
                "status": Project.Status.WINNER,
                "deadline": now - timedelta(days=45),
                "score": 10,
                "submitted_at": now - timedelta(days=70),
                "reviewed_at": now - timedelta(days=55),
                "rejection_reason": "",
                "team": [
                    ("sarah", ProjectMember.Role.CHEF_DE_PROJET),
                    ("alex", ProjectMember.Role.DEVELOPPEUR),
                    ("yassine", ProjectMember.Role.DESIGNER),
                ],
                "history": [
                    (
                        HistoriqueProjet.Action.SUBMITTED,
                        "sarah",
                        "",
                        now - timedelta(days=70),
                    ),
                    (
                        HistoriqueProjet.Action.ACCEPTED,
                        "organizer",
                        "",
                        now - timedelta(days=55),
                    ),
                    (
                        HistoriqueProjet.Action.FINALIST,
                        "organizer",
                        "Selected for the final pitch.",
                        now - timedelta(days=48),
                    ),
                    (
                        HistoriqueProjet.Action.WINNER,
                        "organizer",
                        "Grand prize winner.",
                        now - timedelta(days=46),
                    ),
                ],
                "advice": [
                    (
                        "Keep the citation-first design; it is the strongest part of "
                        "the product. For the next iteration, measure study outcomes "
                        "with a small controlled group."
                    ),
                    (
                        "The pitch was clear and the live demo worked. Rehearse the "
                        "failure case so you can recover quickly on stage."
                    ),
                ],
            },
            {
                "slug": "opendata-studio",
                "title": "OpenData Studio",
                "tagline": "Turn public datasets into classroom-ready dashboards.",
                "description": (
                    "OpenData Studio lets teachers compose simple dashboards from "
                    "open datasets without writing code. The prototype includes "
                    "templates for transport, air quality and campus energy data."
                ),
                "category": Project.Category.OTHER,
                "hackathon": active.title,
                "status": Project.Status.ACCEPTED,
                "deadline": now + timedelta(days=3),
                "score": 7,
                "submitted_at": now - timedelta(days=12),
                "reviewed_at": now - timedelta(days=8),
                "rejection_reason": "",
                "team": [
                    ("yassine", ProjectMember.Role.CHEF_DE_PROJET),
                    ("student", ProjectMember.Role.DEVELOPPEUR),
                    ("maya", ProjectMember.Role.DESIGNER),
                ],
                "history": [
                    (
                        HistoriqueProjet.Action.SUBMITTED,
                        "yassine",
                        "",
                        now - timedelta(days=12),
                    ),
                    (
                        HistoriqueProjet.Action.ACCEPTED,
                        "organizer",
                        "",
                        now - timedelta(days=8),
                    ),
                ],
                "advice": [],
            },
        ]

        projects = {}
        for spec in specs:
            team = spec.pop("team")
            history = spec.pop("history")
            advice = spec.pop("advice")
            slug = spec.pop("slug")
            created_by = users[team[0][0]]
            spec["reviewed_by"] = organizer if spec["reviewed_at"] else None
            spec["review_history"] = []
            if spec["submitted_at"]:
                spec["review_history"].append(_submission_entry(created_by, spec["submitted_at"]))
            if spec["reviewed_at"]:
                decision = "reject" if spec["status"] == Project.Status.REJECTED else "accept"
                spec["review_history"].append(
                    _decision_entry(
                        organizer,
                        spec["reviewed_at"],
                        decision,
                        spec.get("rejection_reason", ""),
                    )
                )

            project, _ = Project.objects.update_or_create(
                slug=slug,
                defaults={
                    **spec,
                    "created_by": created_by,
                    "repository_url": f"https://github.com/hackflow-demo/{slug}",
                    "demo_url": f"https://{slug}.example.com",
                    "video_url": f"https://videos.example.com/{slug}",
                },
            )

            for username, role in team:
                ProjectMember.objects.update_or_create(
                    project=project,
                    user=users[username],
                    defaults={"role": role, "is_accepted": True},
                )

            for text in advice:
                _upsert_first(
                    ConseilMentor,
                    {"project": project, "mentor": users["mentor"], "texte": text},
                    {},
                )

            for action, actor_username, comment, date in history:
                _upsert_first(
                    HistoriqueProjet,
                    {
                        "project": project,
                        "action": action,
                        "acteur": users[actor_username],
                    },
                    {"commentaire": comment, "date": date},
                )

            projects[slug] = project

        return projects

    # ------------------------------------------------------------------
    # Sponsors
    # ------------------------------------------------------------------

    def _seed_sponsors(self, now, users, hackathons, *, generate_media: bool):
        organizer = users["organizer"]
        sponsors: dict[str, Sponsor] = {}

        for index, spec in enumerate(SPONSOR_SPECS):
            name = spec["name"]
            sponsor, _ = Sponsor.objects.update_or_create(
                name=name,
                defaults={
                    "sector": spec["sector"],
                    "website": spec["website"],
                    "contact_name": spec["contact_name"],
                    "contact_email": spec["contact_email"],
                    "description": spec["description"],
                },
            )
            if generate_media:
                _ensure_image(
                    sponsor.logo,
                    f"logo-{slugify(name)}.png",
                    _make_logo(spec["initials"], spec["palette"]),
                )

            sponsorship, _ = Sponsorship.objects.update_or_create(
                sponsor=sponsor,
                hackathon=hackathons[spec["hackathon"]],
                defaults={
                    "tier": spec["tier"],
                    "amount": spec["amount"],
                    "status": spec["status"],
                    "contribution_type": spec["contribution_type"],
                    "notes": spec["notes"],
                },
            )

            statuses = spec["history"]
            for status_index, status in enumerate(statuses):
                previous = statuses[status_index - 1] if status_index else status
                changed_at = now - timedelta(days=70 - status_index * 5 - index)
                _upsert_first(
                    StatusHistory,
                    {
                        "sponsorship": sponsorship,
                        "old_status": previous,
                        "new_status": status,
                        "changed_by": organizer,
                    },
                    {"changed_at": changed_at},
                )

            for email_index, (subject, body, ai_generated) in enumerate(spec.get("emails", [])):
                _upsert_first(
                    SponsorEmailLog,
                    {"sponsor": sponsor, "subject": subject},
                    {
                        "body": body,
                        "sent_by": organizer,
                        "sent_at": now - timedelta(days=3 + email_index, hours=email_index),
                        "success": True,
                        "ai_generated": ai_generated,
                        "error_message": "",
                    },
                )

            sponsors[name] = sponsor

        return sponsors

    # ------------------------------------------------------------------
    # Reporting
    # ------------------------------------------------------------------

    def _report(self, users, hackathons, projects, sponsors):
        hackathon_slugs = [hackathon.slug for hackathon in hackathons.values()]
        project_slugs = list(projects.keys())
        sponsor_names = list(sponsors.keys())

        self.stdout.write(self.style.SUCCESS("Demo data seeded successfully."))
        self.stdout.write(
            "  users:          "
            f"{User.objects.filter(username__in=users).count()} "
            f"({', '.join(users)})"
        )
        self.stdout.write(
            f"  hackathons:     {Hackathon.objects.filter(slug__in=hackathon_slugs).count()}"
        )
        self.stdout.write(
            "  registrations:  "
            f"{HackathonRegistration.objects.filter(hackathon__slug__in=hackathon_slugs).count()}"
        )
        self.stdout.write(
            "  projects:       "
            f"{Project.objects.filter(slug__in=project_slugs).count()} "
            f"({Project.objects.filter(slug__in=project_slugs).values('status').distinct().count()} statuses)"
        )
        self.stdout.write(
            "  team members:   "
            f"{ProjectMember.objects.filter(project__slug__in=project_slugs).count()}"
        )
        self.stdout.write(
            "  mentor advice:  "
            f"{ConseilMentor.objects.filter(project__slug__in=project_slugs).count()}"
        )
        self.stdout.write(
            "  project history:"
            f" {HistoriqueProjet.objects.filter(project__slug__in=project_slugs).count()}"
        )
        self.stdout.write(
            f"  sponsors:       {Sponsor.objects.filter(name__in=sponsor_names).count()}"
        )
        self.stdout.write(
            "  sponsorships:   "
            f"{Sponsorship.objects.filter(sponsor__name__in=sponsor_names).count()}"
        )
        self.stdout.write(
            "  sponsor history:"
            f" {StatusHistory.objects.filter(sponsorship__sponsor__name__in=sponsor_names).count()}"
        )
        self.stdout.write(
            "  sponsor emails: "
            f"{SponsorEmailLog.objects.filter(sponsor__name__in=sponsor_names).count()}"
        )
        self.stdout.write(
            "Passwords are not printed. Use DEMO_ADMIN_PASSWORD for admin and "
            "DEMO_PASSWORD for the other demo users."
        )
