from django.conf import settings
from django.db import models
from django.urls import reverse
from django.utils import timezone
from django.utils.text import slugify


class Project(models.Model):
    """
    Modèle principal pour la gestion d'un projet soumis lors d'un hackathon.
    """

    class Status(models.TextChoices):
        DRAFT = "draft", "Brouillon"
        SUBMITTED = "submitted", "Soumis"
        UNDER_REVIEW = "under_review", "En cours d'évaluation"
        ACCEPTED = "accepted", "Accepté"
        REJECTED = "rejected", "Refusé"
        FINALIST = "finalist", "Finaliste"
        WINNER = "winner", "Lauréat / Gagnant"

    class Category(models.TextChoices):
        WEB = "web", "Développement Web"
        MOBILE = "mobile", "Application Mobile"
        AI = "ai", "Intelligence Artificielle & Data"
        IOT = "iot", "IoT & Systèmes Embarqués"
        CYBER = "cyber", "Cybersécurité"
        GREEN = "green", "GreenTech & Climat"
        OTHER = "other", "Autre Catégorie"

    title = models.CharField(
        max_length=200,
        verbose_name="Titre du projet",
        help_text="Nom accrocheur de votre projet ou produit",
    )
    slug = models.SlugField(
        max_length=220,
        unique=True,
        blank=True,
        verbose_name="Slug (URL)",
        help_text="Généré automatiquement à partir du titre si laissé vide",
    )
    tagline = models.CharField(
        max_length=250,
        verbose_name="Slogan / Pitch court",
        help_text="Une phrase pour résumer le problème et votre solution",
    )
    description = models.TextField(
        verbose_name="Description détaillée",
        help_text="Explication complète de votre solution, fonctionnalités et architecture",
    )
    category = models.CharField(
        max_length=30,
        choices=Category.choices,
        default=Category.WEB,
        verbose_name="Catégorie / Track",
    )
    hackathon = models.CharField(
        max_length=150,
        blank=True,
        default="HackFlow 2026",
        verbose_name="Hackathon",
        help_text="Nom ou édition du hackathon associé au projet",
    )
    status = models.CharField(
        max_length=25,
        choices=Status.choices,
        default=Status.DRAFT,
        verbose_name="Statut du projet",
    )
    deadline = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="Date limite de soumission",
        help_text="Deadline après laquelle le projet ne peut plus être modifié ou soumis",
    )

    # Suivi d'évaluation / Décisions Admin
    rejection_reason = models.TextField(
        blank=True,
        verbose_name="Motif de refus",
        help_text="Explication fournie à l'équipe en cas de refus du projet",
    )
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="reviewed_projects",
        verbose_name="Évalué par (Admin)",
    )
    reviewed_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="Date de décision",
    )
    submitted_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="Date de soumission",
        help_text="Date à laquelle le projet a été soumis ou resoumis",
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
        verbose_name="Historique des décisions",
        help_text="Historique chronologique des évaluations et soumissions",
    )
    score = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
        verbose_name="Score / Note (1-10)",
        help_text="Note attribuée par l'organisateur (1 = faible, 10 = excellent)",
    )

    # Liens externes du projet
    repository_url = models.URLField(
        blank=True,
        verbose_name="Dépôt de code (GitHub/GitLab)",
        help_text="URL publique du repository",
    )
    demo_url = models.URLField(
        blank=True,
        verbose_name="Lien de la démo",
        help_text="URL du prototype ou site déployé",
    )
    video_url = models.URLField(
        blank=True,
        verbose_name="Vidéo de présentation",
        help_text="Lien YouTube, Vimeo ou Loom du pitch",
    )

    # Responsable et membres de l'équipe
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="owned_projects",
        verbose_name="Chef de projet (Créateur)",
    )
    members = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        through="ProjectMember",
        related_name="joined_projects",
        verbose_name="Membres de l'équipe",
        blank=True,
    )

    # Horodatages
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Date de création")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Dernière modification")

    class Meta:
        verbose_name = "Projet"
        verbose_name_plural = "Projets"
        ordering = ("-created_at",)

    def __str__(self):
        return self.title

    def save(self, *args, **kwargs):
        if not self.slug:
            base_slug = slugify(self.title) or "projet"
            unique_slug = base_slug
            counter = 1
            while Project.objects.filter(slug=unique_slug).exclude(pk=self.pk).exists():
                unique_slug = f"{base_slug}-{counter}"
                counter += 1
            self.slug = unique_slug
        super().save(*args, **kwargs)

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
        self.review_history.append({
            "type": "decision",
            "decision": "accept",
            "decision_display": "Accepté",
            "reason": "",
            "reviewed_by": user.get_username() if user else "",
            "reviewed_at": self.reviewed_at.isoformat(),
            "reviewed_at_display": self.reviewed_at.strftime("%d/%m/%Y à %H:%M"),
            "date": self.reviewed_at.isoformat(),
            "date_display": self.reviewed_at.strftime("%d/%m/%Y à %H:%M"),
        })
        self.save(update_fields=["status", "reviewed_by", "reviewed_at", "review_history", "updated_at"])

    def reject(self, user, reason):
        """Refuser le projet avec un motif et enregistrer la décision dans l'historique."""
        self.status = self.Status.REJECTED
        self.rejection_reason = reason
        self.reviewed_by = user
        self.reviewed_at = timezone.now()
        if not isinstance(self.review_history, list):
            self.review_history = []
        self.review_history.append({
            "type": "decision",
            "decision": "reject",
            "decision_display": "Refusé",
            "reason": reason,
            "reviewed_by": user.get_username() if user else "",
            "reviewed_at": self.reviewed_at.isoformat(),
            "reviewed_at_display": self.reviewed_at.strftime("%d/%m/%Y à %H:%M"),
            "date": self.reviewed_at.isoformat(),
            "date_display": self.reviewed_at.strftime("%d/%m/%Y à %H:%M"),
        })
        self.save(update_fields=["status", "rejection_reason", "reviewed_by", "reviewed_at", "review_history", "updated_at"])


class ProjectMember(models.Model):
    """
    Modèle d'association entre un Projet et un Utilisateur (Équipe).
    Précise le rôle de l'étudiant au sein de l'équipe.
    """

    class Role(models.TextChoices):
        CHEF_DE_PROJET = "chef_de_projet", "Chef de projet"
        DEVELOPPEUR = "developpeur", "Développeur"
        DESIGNER = "designer", "Designer"

    # Backward compatibility alias
    Role.LEAD = Role.CHEF_DE_PROJET

    project = models.ForeignKey(
        Project,
        on_delete=models.CASCADE,
        related_name="team_memberships",
        verbose_name="Projet",
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="project_roles",
        verbose_name="Étudiant / Membre",
    )
    role = models.CharField(
        max_length=25,
        choices=Role.choices,
        default=Role.DEVELOPPEUR,
        verbose_name="Rôle dans l'équipe",
    )
    is_accepted = models.BooleanField(
        default=True,
        verbose_name="Adhésion acceptée",
        help_text="Permet de valider ou rejeter une demande d'adhésion à l'équipe",
    )
    joined_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name="Date d'intégration",
    )

    class Meta:
        verbose_name = "Membre du projet"
        verbose_name_plural = "Membres du projet"
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
        verbose_name="Projet",
    )
    mentor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="conseils_mentor_donnes",
        verbose_name="Mentor",
    )
    texte = models.TextField(
        verbose_name="Conseil du mentor",
    )
    date = models.DateTimeField(
        auto_now_add=True,
        verbose_name="Date du conseil",
    )

    class Meta:
        verbose_name = "Conseil du mentor"
        verbose_name_plural = "Conseils du mentor"
        ordering = ("-date",)

    def __str__(self):
        return f"Conseil de {self.mentor} pour {self.project.title} ({self.date.strftime('%d/%m/%Y %H:%M')})"


class HistoriqueProjet(models.Model):
    """
    Immutable audit log — one row per significant project event.
    Records are created automatically by services.py; manual
    creation / update / deletion is intentionally forbidden.
    """

    class Action(models.TextChoices):
        SUBMITTED      = "submitted",       "Submitted"
        RESUBMITTED    = "soumis_a_nouveau", "Resubmitted"
        REJECTED       = "refuse",           "Rejected"
        ACCEPTED       = "accepte",          "Accepted"
        UNDER_REVIEW   = "en_evaluation",    "Under Review"
        FINALIST       = "finaliste",        "Finalist"
        WINNER         = "laureat",          "Winner"

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
        ordering = ("date",)   # chronological

    def __str__(self):
        actor = self.acteur.get_username() if self.acteur else "—"
        return f"[{self.date.strftime('%Y-%m-%d %H:%M')}] {self.project.title} — {self.get_action_display()} by {actor}"
