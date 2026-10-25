from django.conf import settings
from django.core.validators import MaxValueValidator, MinLengthValidator, MinValueValidator
from django.db import models


class Hackathon(models.Model):
    """Modèle PROVISOIRE : sera remplacé par celui du module Gestion des hackathons."""
    title = models.CharField("Titre", max_length=120)
    start_date = models.DateField("Date de début")
    end_date = models.DateField("Date de fin")

    def __str__(self):
        return self.title


class Team(models.Model):
    name = models.CharField(
        "Nom",
        max_length=60,
        validators=[MinLengthValidator(3, "Le nom doit contenir au moins 3 caractères.")],
    )
    description = models.TextField("Description", blank=True)
    hackathon = models.ForeignKey(
        Hackathon, on_delete=models.CASCADE, related_name="teams", verbose_name="Hackathon"
    )
    leader = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
        related_name="led_teams", verbose_name="Chef d'équipe",
    )
    max_members = models.PositiveSmallIntegerField(
        "Nombre max de membres", default=4,
        validators=[MinValueValidator(2), MaxValueValidator(6)],
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-created_at",)
        constraints = [
            models.UniqueConstraint(fields=["hackathon", "name"], name="unique_team_name_per_hackathon")
        ]

    def __str__(self):
        return f"{self.name} ({self.hackathon})"

    @property
    def is_full(self):
        return self.members.count() >= self.max_members


class TeamMember(models.Model):
    class Role(models.TextChoices):
        LEADER = "leader", "Chef d'équipe"
        BACKEND = "backend", "Développeur backend"
        FRONTEND = "frontend", "Développeur frontend"
        DESIGNER = "designer", "Designer UI/UX"
        DATA = "data", "Data / IA"
        OTHER = "other", "Autre"

    team = models.ForeignKey(Team, on_delete=models.CASCADE, related_name="members")
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="team_memberships"
    )
    role = models.CharField("Rôle", max_length=10, choices=Role.choices, default=Role.OTHER)
    skills = models.CharField("Compétences", max_length=200, blank=True,
                              help_text="Séparées par des virgules : python, django, figma")
    joined_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["team", "user"], name="unique_member_per_team")
        ]

    def __str__(self):
        return f"{self.user} - {self.team}"




class SkillProfile(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="skill_profile"
    )
    main_role = models.CharField(
        "Rôle principal", max_length=10,
        choices=[c for c in TeamMember.Role.choices if c[0] != "leader"],
        default=TeamMember.Role.OTHER,
    )
    skills = models.CharField(
        "Compétences", max_length=200, blank=True,
        help_text="Séparées par des virgules : python, django, figma",
    )
    bio = models.TextField("Présentation", blank=True)
    looking_for_team = models.BooleanField("Je cherche une équipe", default=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Compétences de {self.user}"    