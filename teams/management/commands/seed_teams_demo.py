from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from teams import services
from teams.models import Hackathon, SkillProfile, Team, TeamMember

PASSWORD = "demo12345"
HACKATHON_TITLE = "Hack Tunis 2026 (démo)"
TEAM_NAME = "Alpha Team"

# username, rôle principal, compétences, bio, cherche une équipe
DEMO_USERS = [
    (
        "demo_chef",
        "backend",
        "django, python, postgresql, docker",
        "Chef d'équipe, backend.",
        False,
    ),
    ("demo_front", "frontend", "react, javascript, css, tailwind", "Développeuse frontend.", False),
    ("demo_design", "designer", "figma, ui, ux, css", "Designer UI/UX.", True),
    ("demo_data", "data", "python, pandas, sql, machine learning", "Data scientist.", True),
    ("demo_dev", "backend", "django, python, api", "Autre développeur backend.", True),
    ("demo_mobile", "other", "flutter, firebase", "Développeur mobile.", True),
]


class Command(BaseCommand):
    help = "Create demo data (demo_* accounts, team, invitation)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--reset",
            action="store_true",
            help="Supprime d'abord les données de démo (comptes demo_*, hackathon de démo).",
        )

    @transaction.atomic
    def handle(self, *args, **options):
        User = get_user_model()

        if options["reset"]:
            User.objects.filter(username__startswith="demo_").delete()
            Hackathon.objects.filter(title=HACKATHON_TITLE).delete()
            self.stdout.write("Demo data removed.")

        today = timezone.localdate()
        hackathon, _ = Hackathon.objects.get_or_create(
            title=HACKATHON_TITLE,
            defaults={"start_date": today, "end_date": today + timezone.timedelta(days=2)},
        )

        users = {}
        for username, role, skills, bio, looking in DEMO_USERS:
            user, _ = User.objects.get_or_create(
                username=username, defaults={"email": f"{username}@example.com"}
            )
            user.set_password(PASSWORD)
            user.save()
            profile = getattr(user, "profile", None)
            if profile is not None and hasattr(profile, "email_verified"):
                profile.email_verified = True
                profile.save()
            SkillProfile.objects.update_or_create(
                user=user,
                defaults={
                    "main_role": role,
                    "skills": skills,
                    "bio": bio,
                    "looking_for_team": looking,
                },
            )
            users[username] = user

        team = Team.objects.filter(hackathon=hackathon, name=TEAM_NAME).first()
        if team is None:
            team = services.create_team(
                leader=users["demo_chef"],
                name=TEAM_NAME,
                description="Équipe de démonstration : il lui manque un designer et un profil data.",
                hackathon=hackathon,
                max_members=4,
            )

        if not TeamMember.objects.filter(team=team, user=users["demo_front"]).exists():
            services.join_team(
                team=team,
                user=users["demo_front"],
                role="frontend",
                skills="react, javascript, css, tailwind",
            )

        try:
            services.invite_user(
                team=team,
                invited_by=users["demo_chef"],
                invitee=users["demo_design"],
                message="On a besoin d'un designer, rejoins-nous !",
            )
        except services.TeamError:
            pass  # déjà invité ou déjà membre : rien à refaire

        self.stdout.write(self.style.SUCCESS("Demo data ready."))
        self.stdout.write(f"Password for all accounts: {PASSWORD}")
        self.stdout.write("Team leader: demo_chef  |  Pending invitee: demo_design")
        self.stdout.write(f"Team: {TEAM_NAME} ({hackathon.title})")
