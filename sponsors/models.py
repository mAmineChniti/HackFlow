"""
Modèles du module Gestion des Sponsors — HackFlow ESPRIT.

Trois modèles principaux :
  - Sponsor        : entreprise ou entité sponsor
  - Sponsorship    : relation entre un Sponsor et un Hackathon (avec tier, statut, etc.)
  - StatusHistory  : historique de chaque changement de statut d'un Sponsorship
"""

from django.contrib.auth.models import User
from django.core.validators import MinValueValidator
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from core.fields import HTTPSURLField


# ---------------------------------------------------------------------------
# Constantes de choix (réutilisées dans forms.py et views.py)
# ---------------------------------------------------------------------------


class TierChoices(models.TextChoices):
    """Niveau de partenariat d'un sponsor pour un hackathon donné."""

    PLATINUM = "platinum", _("Platinum")
    GOLD = "gold", _("Gold")
    SILVER = "silver", _("Silver")
    BRONZE = "bronze", _("Bronze")


class StatusChoices(models.TextChoices):
    """Étapes du pipeline de prospection d'un sponsor."""

    PROSPECT = "prospect", _("Prospect")
    CONTACTE = "contacté", _("Contacted")
    NEGOCIATION = "négociation", _("Negotiating")
    CONFIRME = "confirmé", _("Confirmed")
    REFUSE = "refusé", _("Declined")


class ContributionTypeChoices(models.TextChoices):
    """Nature de la contribution apportée par le sponsor."""

    FINANCIER = "financier", _("Financial")
    MATERIEL = "matériel", _("Equipment")
    PRIX = "prix", _("Prizes / Rewards")
    MENTORS = "mentors", _("Mentors / Experts")


# ---------------------------------------------------------------------------
# Secteurs d'activité (utilisés pour le filtre et la recommandation IA)
# ---------------------------------------------------------------------------

SECTOR_CHOICES = [
    ("tech", _("Technology / IT")),
    ("finance", _("Finance / Banking")),
    ("sante", _("Healthcare / Biotech")),
    ("education", _("Education / Training")),
    ("energie", _("Energy / Environment")),
    ("industrie", _("Industry / Manufacturing")),
    ("media", _("Media / Communications")),
    ("retail", _("Retail / Distribution")),
    ("autre", _("Other")),
]


# ---------------------------------------------------------------------------
# Modèle Sponsor
# ---------------------------------------------------------------------------


def logo_upload_path(instance, filename):
    """Chemin d'upload du logo : media/sponsors/logos/<nom_slug>/<fichier>."""
    import re

    slug = re.sub(r"[^\w-]", "_", instance.name.lower())
    return f"sponsors/logos/{slug}/{filename}"


class Sponsor(models.Model):
    """
    Représente une entreprise ou organisation pouvant sponsoriser des hackathons.

    Un sponsor peut être associé à plusieurs hackathons via le modèle Sponsorship.
    """

    name = models.CharField(
        max_length=255,
        unique=True,
        verbose_name=_("Company name"),
    )
    logo = models.ImageField(
        upload_to=logo_upload_path,
        blank=True,
        null=True,
        verbose_name=_("Logo"),
        help_text=_("Recommended format: PNG or SVG with a transparent background, max 2 MB."),
    )
    website = HTTPSURLField(
        blank=True,
        verbose_name=_("Website"),
    )
    sector = models.CharField(
        max_length=50,
        choices=SECTOR_CHOICES,
        default="tech",
        verbose_name=_("Industry"),
    )
    description = models.TextField(
        blank=True,
        verbose_name=_("Description"),
        help_text=_("A short description shown on the public page."),
    )
    contact_name = models.CharField(
        max_length=255,
        blank=True,
        verbose_name=_("Contact name"),
    )
    contact_email = models.EmailField(
        blank=True,
        verbose_name=_("Contact email"),
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_("Created at"))
    updated_at = models.DateTimeField(auto_now=True, verbose_name=_("Updated at"))

    class Meta:
        verbose_name = _("Sponsor")
        verbose_name_plural = _("Sponsors")
        ordering = ["name"]

    def __str__(self):
        return self.name

    @property
    def active_sponsorships_count(self):
        """Nombre de hackathons pour lesquels ce sponsor est confirmé."""
        return self.sponsorships.filter(status=StatusChoices.CONFIRME).count()


# ---------------------------------------------------------------------------
# Modèle Sponsorship (relation Sponsor <-> Hackathon)
# ---------------------------------------------------------------------------


class Sponsorship(models.Model):
    """
    Représente la relation entre un Sponsor et un Hackathon.

    Chaque combinaison (sponsor, hackathon) est unique.
    Le champ 'status' pilote le pipeline Kanban.
    """

    sponsor = models.ForeignKey(
        Sponsor,
        on_delete=models.CASCADE,
        related_name="sponsorships",
        verbose_name=_("Sponsor"),
    )
    hackathon = models.ForeignKey(
        # Référence en string pour ne pas bloquer si l'app hackathons n'est pas encore migrée
        "hackathons.Hackathon",
        on_delete=models.CASCADE,
        related_name="sponsorships",
        verbose_name=_("Hackathon"),
    )
    tier = models.CharField(
        max_length=20,
        choices=TierChoices.choices,
        default=TierChoices.BRONZE,
        verbose_name=_("Tier"),
    )
    amount = models.DecimalField(
        max_digits=12,
        decimal_places=3,
        default=0,
        validators=[MinValueValidator(0)],
        verbose_name=_("Amount (DT)"),
        help_text=_(
            "Financial contribution amount in DT (e.g. 2500.000 DT). Use 0 for non-financial contributions."
        ),
    )
    status = models.CharField(
        max_length=20,
        choices=StatusChoices.choices,
        default=StatusChoices.PROSPECT,
        verbose_name=_("Status"),
    )
    contribution_type = models.CharField(
        max_length=20,
        choices=ContributionTypeChoices.choices,
        default=ContributionTypeChoices.FINANCIER,
        verbose_name=_("Contribution type"),
    )
    notes = models.TextField(
        blank=True,
        verbose_name=_("Internal notes"),
        help_text=_("Notes visible only to authorized organizers."),
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_("Created at"))
    updated_at = models.DateTimeField(auto_now=True, verbose_name=_("Updated at"))

    class Meta:
        verbose_name = _("Partnership")
        verbose_name_plural = _("Partnerships")
        ordering = ["tier", "sponsor__name"]
        # Un sponsor ne peut être lié qu'une seule fois à un hackathon donné
        unique_together = [("sponsor", "hackathon")]

    def __str__(self):
        return f"{self.sponsor.name} → {self.hackathon.title} [{self.get_tier_display()}]"

    def change_status(self, new_status: str, changed_by: User) -> "StatusHistory | None":
        """
        Délègue exclusivement à l'unique implémentation métier change_sponsorship_status (services.py).
        """
        from .services import change_sponsorship_status

        return change_sponsorship_status(self, new_status, changed_by)


# ---------------------------------------------------------------------------
# Modèle StatusHistory (historique des changements de statut)
# ---------------------------------------------------------------------------


class StatusHistory(models.Model):
    """
    Trace chaque changement de statut d'un Sponsorship.

    Alimenté automatiquement via Sponsorship.change_status().
    Jamais modifié manuellement : les entrées sont immuables.
    """

    sponsorship = models.ForeignKey(
        Sponsorship,
        on_delete=models.CASCADE,
        related_name="history",
        verbose_name=_("Partnership"),
    )
    old_status = models.CharField(
        max_length=20,
        choices=StatusChoices.choices,
        verbose_name=_("Previous status"),
    )
    new_status = models.CharField(
        max_length=20,
        choices=StatusChoices.choices,
        verbose_name=_("New status"),
    )
    changed_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        related_name="sponsorship_status_changes",
        verbose_name=_("Changed by"),
    )
    changed_at = models.DateTimeField(
        default=timezone.now,
        verbose_name=_("Changed at"),
    )

    class Meta:
        verbose_name = _("Status history")
        verbose_name_plural = _("Status history")
        ordering = ["-changed_at"]

    def __str__(self):
        return (
            f"{self.sponsorship}: "
            f"{self.get_old_status_display()} → {self.get_new_status_display()} "
            f"({self.changed_at:%b %d, %Y %H:%M})"
        )


# ---------------------------------------------------------------------------
# Modèle SponsorEmailLog (journal d'audit des emails envoyés aux sponsors)
# ---------------------------------------------------------------------------


class SponsorEmailLog(models.Model):
    """
    Consigne chaque email envoyé à un contact sponsor par un organisateur.
    Enregistre le statut de remise (success=True/False) et l'erreur en cas d'échec.
    """

    sponsor = models.ForeignKey(
        Sponsor,
        on_delete=models.CASCADE,
        related_name="email_logs",
        verbose_name=_("Sponsor"),
    )
    sent_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        related_name="sponsor_emails_sent",
        verbose_name=_("Sent by"),
    )
    subject = models.CharField(
        max_length=255,
        verbose_name=_("Subject"),
    )
    body = models.TextField(
        verbose_name=_("Message"),
    )
    sent_at = models.DateTimeField(
        default=timezone.now,
        verbose_name=_("Sent at"),
    )
    success = models.BooleanField(
        default=True,
        verbose_name=_("Successful"),
    )
    ai_generated = models.BooleanField(
        default=False,
        verbose_name=_("AI generated"),
    )
    error_message = models.TextField(
        blank=True,
        verbose_name=_("Error message"),
    )

    class Meta:
        verbose_name = _("Sponsor email log")
        verbose_name_plural = _("Sponsor email logs")
        ordering = ["-sent_at"]

    def __str__(self):
        status_str = "Sent" if self.success else "Failed"
        return (
            f"[{status_str}] {self.sponsor.name} : {self.subject} ({self.sent_at:%b %d, %Y %H:%M})"
        )
