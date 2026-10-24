import uuid

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.urls import reverse
from django.utils import timezone
from django.utils.text import slugify


class Hackathon(models.Model):
    """
    Central model for the platform — every other module (teams, projects,
    sponsors, rooms) references a Hackathon.
    """

    # ── Lifecycle status machine ─────────────────────────────────────
    class Status(models.TextChoices):
        DRAFT = "draft", "Brouillon"
        REGISTRATION_OPEN = "registration_open", "Inscriptions ouvertes"
        ONGOING = "ongoing", "En cours"
        JUDGING = "judging", "Évaluation"
        FINISHED = "finished", "Terminé"
        CANCELLED = "cancelled", "Annulé"

    # ── Event mode ───────────────────────────────────────────────────
    class Mode(models.TextChoices):
        ONLINE = "online", "En ligne"
        IN_PERSON = "in_person", "Présentiel"
        HYBRID = "hybrid", "Hybride"

    # ── Difficulty level ─────────────────────────────────────────────
    class Difficulty(models.TextChoices):
        BEGINNER = "beginner", "Débutant"
        INTERMEDIATE = "intermediate", "Intermédiaire"
        ADVANCED = "advanced", "Avancé"
        ALL_LEVELS = "all_levels", "Tous niveaux"

    # ── General information ──────────────────────────────────────────
    title = models.CharField(
        max_length=200,
        verbose_name="Titre",
    )
    slug = models.SlugField(
        max_length=220,
        unique=True,
        blank=True,
        help_text="Auto-generated from title if left blank.",
    )
    tagline = models.CharField(
        max_length=255,
        verbose_name="Slogan",
        help_text="One-line catchy description.",
    )
    description = models.TextField(
        verbose_name="Description détaillée",
    )
    category = models.CharField(
        max_length=100,
        verbose_name="Catégorie",
        help_text="Ex: AI & Data, Web3, GreenTech, Cybersecurity…",
    )
    banner_image = models.ImageField(
        upload_to="hackathons/banners/",
        blank=True,
        null=True,
        verbose_name="Bannière",
    )

    # ── Dates & scheduling ───────────────────────────────────────────
    registration_start = models.DateTimeField(
        verbose_name="Ouverture des inscriptions",
    )
    registration_deadline = models.DateTimeField(
        verbose_name="Date limite d'inscription",
    )
    start_date = models.DateTimeField(
        verbose_name="Début du hackathon",
    )
    end_date = models.DateTimeField(
        verbose_name="Fin du hackathon",
    )

    # ── Mode & location ──────────────────────────────────────────────
    mode = models.CharField(
        max_length=20,
        choices=Mode.choices,
        default=Mode.IN_PERSON,
        verbose_name="Modalité",
    )
    location = models.CharField(
        max_length=255,
        blank=True,
        default="",
        verbose_name="Lieu",
        help_text="Physical venue, Discord/Teams link, or both for hybrid.",
    )

    # ── Capacity & team rules ────────────────────────────────────────
    max_participants = models.PositiveIntegerField(
        default=100,
        verbose_name="Nombre max de participants",
    )
    min_team_size = models.PositiveSmallIntegerField(
        default=2,
        verbose_name="Taille min d'une équipe",
    )
    max_team_size = models.PositiveSmallIntegerField(
        default=4,
        verbose_name="Taille max d'une équipe",
    )

    # ── Prize & level ────────────────────────────────────────────────
    prize_pool = models.CharField(
        max_length=100,
        blank=True,
        default="",
        verbose_name="Prix / Récompense",
        help_text="Ex: 5 000 TND, Certificats, Matériel…",
    )
    difficulty = models.CharField(
        max_length=20,
        choices=Difficulty.choices,
        default=Difficulty.ALL_LEVELS,
        verbose_name="Niveau de difficulté",
    )

    # ── Rules & resources ────────────────────────────────────────────
    rules = models.TextField(
        blank=True,
        default="",
        verbose_name="Règlement",
        help_text="Markdown supported.",
    )
    resources_link = models.URLField(
        blank=True,
        default="",
        verbose_name="Lien ressources",
        help_text="Link to a shared Drive, Notion page, etc.",
    )
    contact_email = models.EmailField(
        blank=True,
        default="",
        verbose_name="Email de contact",
    )

    # ── Ownership & status ───────────────────────────────────────────
    organizer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="organized_hackathons",
        verbose_name="Organisateur",
    )
    status = models.CharField(
        max_length=25,
        choices=Status.choices,
        default=Status.DRAFT,
        verbose_name="Statut",
    )
    is_published = models.BooleanField(
        default=False,
        verbose_name="Publié",
        help_text="Only published hackathons appear in the public catalogue.",
    )

    # ── Timestamps ───────────────────────────────────────────────────
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-start_date"]
        verbose_name = "Hackathon"
        verbose_name_plural = "Hackathons"

    # ── Auto slug ────────────────────────────────────────────────────
    def save(self, *args, **kwargs):
        if not self.slug:
            base_slug = slugify(self.title)
            slug = base_slug
            counter = 1
            while Hackathon.objects.filter(slug=slug).exclude(pk=self.pk).exists():
                slug = f"{base_slug}-{counter}"
                counter += 1
            self.slug = slug
        super().save(*args, **kwargs)

    def clean(self):
        """Cross-field validation for dates and team sizes."""
        errors = {}

        if self.registration_start and self.registration_deadline:
            if self.registration_deadline <= self.registration_start:
                errors["registration_deadline"] = (
                    "La date limite d'inscription doit être postérieure "
                    "à l'ouverture des inscriptions."
                )

        if self.registration_deadline and self.start_date:
            if self.start_date < self.registration_deadline:
                errors["start_date"] = (
                    "Le hackathon ne peut pas commencer avant la fin "
                    "des inscriptions."
                )

        if self.start_date and self.end_date:
            if self.end_date <= self.start_date:
                errors["end_date"] = (
                    "La date de fin doit être postérieure à la date de début."
                )

        if self.min_team_size and self.max_team_size:
            if self.min_team_size > self.max_team_size:
                errors["min_team_size"] = (
                    "La taille minimale ne peut pas dépasser la taille maximale."
                )

        if errors:
            raise ValidationError(errors)

    def __str__(self):
        return self.title

    def get_absolute_url(self):
        return reverse("hackathons:detail", kwargs={"slug": self.slug})

    # ── Computed helpers ─────────────────────────────────────────────
    @property
    def is_registration_open(self):
        """True when the current time falls within the registration window."""
        now = timezone.now()
        return (
            self.status == self.Status.REGISTRATION_OPEN
            and self.registration_start <= now <= self.registration_deadline
        )

    @property
    def is_ongoing(self):
        now = timezone.now()
        return self.start_date <= now <= self.end_date

    @property
    def is_past(self):
        return timezone.now() > self.end_date

    @property
    def days_until_start(self):
        delta = self.start_date - timezone.now()
        return max(delta.days, 0)

    @property
    def registration_progress_percent(self):
        """Percentage of capacity filled (capped at 100)."""
        registered = self.registrations.count()
        if self.max_participants == 0:
            return 0
        return min(int((registered / self.max_participants) * 100), 100)

    @property
    def registered_count(self):
        return self.registrations.count()


class HackathonSchedule(models.Model):
    """
    Timeline entries for a hackathon — ceremonies, checkpoints, deadlines.
    Displayed as a vertical timeline on the detail page.
    """
    hackathon = models.ForeignKey(
        Hackathon,
        on_delete=models.CASCADE,
        related_name="schedule_items",
    )
    title = models.CharField(max_length=200, verbose_name="Titre")
    description = models.TextField(blank=True, default="", verbose_name="Description")
    scheduled_at = models.DateTimeField(verbose_name="Date & heure")

    class Meta:
        ordering = ["scheduled_at"]
        verbose_name = "Étape du programme"
        verbose_name_plural = "Programme du hackathon"

    def __str__(self):
        return f"{self.hackathon.title} — {self.title}"


class HackathonRegistration(models.Model):
    """
    Tracks individual user registrations for a hackathon.
    Acts as the link between a participant and a hackathon before teams
    are formed.
    """
    hackathon = models.ForeignKey(
        Hackathon,
        on_delete=models.CASCADE,
        related_name="registrations",
    )
    participant = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="hackathon_registrations",
    )
    registered_at = models.DateTimeField(auto_now_add=True)
    motivation = models.TextField(
        blank=True,
        default="",
        verbose_name="Motivation",
        help_text="Why do you want to participate?",
    )
    skills = models.CharField(
        max_length=255,
        blank=True,
        default="",
        verbose_name="Compétences",
        help_text="Comma-separated: Python, React, ML…",
    )

    class Meta:
        ordering = ["-registered_at"]
        unique_together = [("hackathon", "participant")]
        verbose_name = "Inscription"
        verbose_name_plural = "Inscriptions"

    def __str__(self):
        return f"{self.participant.get_username()} → {self.hackathon.title}"

    def clean(self):
        """Prevent registration when hackathon is full or closed."""
        if self.hackathon.registered_count >= self.hackathon.max_participants:
            raise ValidationError("Ce hackathon a atteint sa capacité maximale.")
        if not self.hackathon.is_registration_open:
            raise ValidationError("Les inscriptions ne sont pas ouvertes.")


class HackathonFAQ(models.Model):
    """
    Frequently asked questions specific to a hackathon.
    """
    hackathon = models.ForeignKey(
        Hackathon,
        on_delete=models.CASCADE,
        related_name="faqs",
    )
    question = models.CharField(max_length=300, verbose_name="Question")
    answer = models.TextField(verbose_name="Réponse")
    order = models.PositiveSmallIntegerField(default=0, verbose_name="Ordre")

    class Meta:
        ordering = ["order"]
        verbose_name = "FAQ"
        verbose_name_plural = "FAQs"

    def __str__(self):
        return f"FAQ: {self.question[:50]}"
