import uuid

from django.conf import settings
from django.db import IntegrityError, models, transaction
from django.urls import reverse
from django.utils import timezone
from django.utils.text import slugify

from core.fields import HTTPSURLField


class Project(models.Model):
    """
    Modèle principal pour la gestion d'un projet soumis lors d'un hackathon.
    """

    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        SUBMITTED = "submitted", "Submitted"
        UNDER_REVIEW = "under_review", "Under Review"
        ACCEPTED = "accepted", "Accepted"
        REJECTED = "rejected", "Rejected"
        FINALIST = "finalist", "Finalist"
        WINNER = "winner", "Winner"

    class Category(models.TextChoices):
        WEB = "web", "Web Development"
        MOBILE = "mobile", "Mobile Application"
        AI = "ai", "Artificial Intelligence & Data"
        IOT = "iot", "IoT & Embedded Systems"
        CYBER = "cyber", "Cybersecurity"
        GREEN = "green", "GreenTech & Climate"
        OTHER = "other", "Other"

    title = models.CharField(
        max_length=200,
        verbose_name="Project title",
        help_text="A catchy name for your project or product.",
    )
    slug = models.SlugField(
        max_length=220,
        unique=True,
        blank=True,
        verbose_name="Slug (URL)",
        help_text="Generated automatically from the title when left blank.",
    )
    tagline = models.CharField(
        max_length=250,
        verbose_name="Tagline / Short pitch",
        help_text="One sentence summarizing the problem and your solution.",
    )
    description = models.TextField(
        verbose_name="Detailed description",
        help_text="A complete explanation of your solution, features, and architecture.",
    )
    category = models.CharField(
        max_length=30,
        choices=Category.choices,
        default=Category.WEB,
        verbose_name="Category / Track",
    )
    hackathon = models.CharField(
        max_length=150,
        blank=True,
        default="HackFlow 2026",
        verbose_name="Hackathon",
        help_text="Name or edition of the hackathon associated with this project.",
    )
    status = models.CharField(
        max_length=25,
        choices=Status.choices,
        default=Status.DRAFT,
        verbose_name="Project status",
        db_index=True,  # Frequently filtered
    )
    deadline = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="Submission deadline",
        help_text="Deadline after which the project can no longer be edited or submitted.",
    )

    # Suivi d'évaluation / Décisions Admin
    rejection_reason = models.TextField(
        blank=True,
        verbose_name="Rejection reason",
        help_text="Explanation shown to the team when a project is rejected.",
    )
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="reviewed_projects",
        verbose_name="Reviewed by (Admin)",
    )
    reviewed_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="Decision date",
    )
    submitted_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="Submission date",
        help_text="Date on which the project was submitted or resubmitted.",
    )

    @property
    def date_soumission(self):
        return self.submitted_at

    @date_soumission.setter
    def date_soumission(self, value):
        self.submitted_at = value

    @property
    def date_decision(self):
        return self.reviewed_at

    @date_decision.setter
    def date_decision(self, value):
        self.reviewed_at = value

    review_history = models.JSONField(
        default=list,
        blank=True,
        verbose_name="Decision history",
        help_text="Chronological history of reviews and submissions.",
    )
    score = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
        verbose_name="Score (1-10)",
        help_text="Score awarded by the organizer (1 = low, 10 = excellent).",
    )

    # Liens externes du projet
    repository_url = HTTPSURLField(
        blank=True,
        verbose_name="Code repository (GitHub/GitLab)",
        help_text="Public repository URL.",
    )
    demo_url = HTTPSURLField(
        blank=True,
        verbose_name="Demo link",
        help_text="URL of the deployed prototype or website.",
    )
    video_url = HTTPSURLField(
        blank=True,
        verbose_name="Pitch video",
        help_text="YouTube, Vimeo, or Loom link to the pitch.",
    )

    # Responsable et membres de l'équipe
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="owned_projects",
        verbose_name="Project lead (Creator)",
    )
    members = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        through="ProjectMember",
        related_name="joined_projects",
        verbose_name="Team members",
        blank=True,
    )

    # Horodatages
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Created at")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Last updated")

    class Meta:
        verbose_name = "Project"
        verbose_name_plural = "Projects"
        ordering = ("-created_at",)

    def __str__(self):
        return self.title

    MAX_SLUG_ATTEMPTS = 5

    def save(self, *args, **kwargs):
        """Save with a race-safe unique slug.

        The existence check below handles the sequential case (two projects
        called "Foo" get foo / foo-1). Two requests can still pass that check
        at the same time, so the insert is retried with a random suffix when
        the unique constraint rejects the first attempt.
        """
        auto_slug = not self.slug
        update_fields = kwargs.get("update_fields")
        if update_fields is not None and "slug" not in update_fields and not auto_slug:
            return super().save(*args, **kwargs)

        base_slug = slugify(self.title) or "project"
        for attempt in range(self.MAX_SLUG_ATTEMPTS):
            if auto_slug:
                if attempt == 0:
                    candidate = base_slug
                    counter = 1
                    while Project.objects.filter(slug=candidate).exclude(pk=self.pk).exists():
                        candidate = f"{base_slug}-{counter}"
                        counter += 1
                else:
                    candidate = f"{base_slug}-{uuid.uuid4().hex[:8]}"
                self.slug = candidate
                if update_fields is not None and "slug" not in update_fields:
                    kwargs["update_fields"] = list(update_fields) + ["slug"]

            try:
                with transaction.atomic():
                    return super().save(*args, **kwargs)
            except IntegrityError:
                if not auto_slug or attempt == self.MAX_SLUG_ATTEMPTS - 1:
                    raise
                self.slug = ""
                continue

        raise IntegrityError("Could not generate a unique project slug.")

    def get_absolute_url(self):
        return reverse("projects:project_detail", kwargs={"slug": self.slug})

    def is_lead(self, user):
        """Vérifie si l'utilisateur est le créateur/lead du projet."""
        if not user or not user.is_authenticated:
            return False
        return self.created_by == user

    def is_member(self, user):
        """Vérifie si l'utilisateur fait partie de l'équipe."""
        if not user or not user.is_authenticated:
            return False
        return self.created_by == user or self.members.filter(pk=user.pk).exists()

    def can_edit(self, user):
        """Autorisation de modification du projet (Admin ou Chef de projet)."""
        if not user or not user.is_authenticated:
            return False
        return user.is_superuser or self.created_by == user

    def can_review(self, user):
        """Autorisation de valider ou refuser les projets (Admin / Staff)."""
        if not user or not user.is_authenticated:
            return False
        return user.is_staff or user.is_superuser

    def accept(self, user):
        """Accepter le projet et enregistrer la décision dans l'historique."""
        self.status = self.Status.ACCEPTED
        self.reviewed_by = user
        self.reviewed_at = timezone.now()
        if not isinstance(self.review_history, list):
            self.review_history = []
        self.review_history.append(
            {
                "type": "decision",
                "decision": "accept",
                "decision_display": "Accepted",
                "reason": "",
                "reviewed_by": user.get_username() if user else "",
                "reviewed_at": self.reviewed_at.isoformat(),
                "reviewed_at_display": self.reviewed_at.strftime("%b %d, %Y at %H:%M"),
                "date": self.reviewed_at.isoformat(),
                "date_display": self.reviewed_at.strftime("%b %d, %Y at %H:%M"),
            }
        )
        self.save(
            update_fields=["status", "reviewed_by", "reviewed_at", "review_history", "updated_at"]
        )

    def reject(self, user, reason):
        """Refuser le projet avec un motif et enregistrer la décision dans l'historique."""
        self.status = self.Status.REJECTED
        self.rejection_reason = reason
        self.reviewed_by = user
        self.reviewed_at = timezone.now()
        if not isinstance(self.review_history, list):
            self.review_history = []
        self.review_history.append(
            {
                "type": "decision",
                "decision": "reject",
                "decision_display": "Rejected",
                "reason": reason,
                "reviewed_by": user.get_username() if user else "",
                "reviewed_at": self.reviewed_at.isoformat(),
                "reviewed_at_display": self.reviewed_at.strftime("%b %d, %Y at %H:%M"),
                "date": self.reviewed_at.isoformat(),
                "date_display": self.reviewed_at.strftime("%b %d, %Y at %H:%M"),
            }
        )
        self.save(
            update_fields=[
                "status",
                "rejection_reason",
                "reviewed_by",
                "reviewed_at",
                "review_history",
                "updated_at",
            ]
        )


class ProjectMember(models.Model):
    """
    Modèle d'association entre un Projet et un Utilisateur (Équipe).
    Précise le rôle de l'étudiant au sein de l'équipe.
    """

    class Role(models.TextChoices):
        CHEF_DE_PROJET = "chef_de_projet", "Project lead"
        DEVELOPPEUR = "developpeur", "Developer"
        DESIGNER = "designer", "Designer"

    # Backward compatibility alias
    Role.LEAD = Role.CHEF_DE_PROJET

    project = models.ForeignKey(
        Project,
        on_delete=models.CASCADE,
        related_name="team_memberships",
        verbose_name="Project",
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="project_roles",
        verbose_name="Student / Member",
    )
    role = models.CharField(
        max_length=25,
        choices=Role.choices,
        default=Role.DEVELOPPEUR,
        verbose_name="Team role",
    )
    is_accepted = models.BooleanField(
        default=True,
        verbose_name="Membership accepted",
        help_text="Approve or reject a request to join the team.",
    )
    joined_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name="Joined at",
    )

    class Meta:
        verbose_name = "Project member"
        verbose_name_plural = "Project members"
        ordering = ("joined_at",)
        constraints = [
            models.UniqueConstraint(
                fields=["project", "user"],
                name="unique_project_membership",
            )
        ]

    def __str__(self):
        return f"{self.user} - {self.get_role_display()} ({self.project.title})"


class ConseilMentor(models.Model):
    """
    Conseils et recommandations pédagogiques laissés par un mentor pour l'équipe d'un projet.
    """

    project = models.ForeignKey(
        Project,
        on_delete=models.CASCADE,
        related_name="conseils_mentor",
        verbose_name="Project",
    )
    mentor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="conseils_mentor_donnes",
        verbose_name="Mentor",
    )
    texte = models.TextField(
        verbose_name="Mentor advice",
    )
    date = models.DateTimeField(
        auto_now_add=True,
        verbose_name="Advice date",
    )

    class Meta:
        verbose_name = "Mentor advice"
        verbose_name_plural = "Mentor advice"
        ordering = ("-date",)

    def __str__(self):
        return f"Advice from {self.mentor} for {self.project.title} ({self.date.strftime('%b %d, %Y %H:%M')})"


class HistoriqueProjet(models.Model):
    """
    Immutable audit log — one row per significant project event.
    Records are created automatically by services.py; manual
    creation / update / deletion is intentionally forbidden.
    """

    class Action(models.TextChoices):
        SUBMITTED = "submitted", "Submitted"
        RESUBMITTED = "soumis_a_nouveau", "Resubmitted"
        REJECTED = "refuse", "Rejected"
        ACCEPTED = "accepte", "Accepted"
        UNDER_REVIEW = "en_evaluation", "Under Review"
        FINALIST = "finaliste", "Finalist"
        WINNER = "laureat", "Winner"

    project = models.ForeignKey(
        Project,
        on_delete=models.CASCADE,
        related_name="historique",
        verbose_name="Project",
    )
    action = models.CharField(
        max_length=25,
        choices=Action.choices,
        verbose_name="Action",
    )
    acteur = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="historique_actions",
        verbose_name="Actor",
    )
    commentaire = models.TextField(
        blank=True,
        default="",
        verbose_name="Comment (rejection reason)",
        help_text="Mandatory for rejections; optional for other actions.",
    )
    date = models.DateTimeField(
        default=timezone.now,
        verbose_name="Date",
    )

    class Meta:
        verbose_name = "Project History Entry"
        verbose_name_plural = "Project History"
        ordering = ("date",)  # chronological

    def __str__(self):
        actor = self.acteur.get_username() if self.acteur else "—"
        return f"[{self.date.strftime('%Y-%m-%d %H:%M')}] {self.project.title} — {self.get_action_display()} by {actor}"
