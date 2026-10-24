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
    CONTACTE = "contacté", _("Contacté")
    NEGOCIATION = "négociation", _("Négociation")
    CONFIRME = "confirmé", _("Confirmé")
    REFUSE = "refusé", _("Refusé")


class ContributionTypeChoices(models.TextChoices):
    """Nature de la contribution apportée par le sponsor."""
    FINANCIER = "financier", _("Financier")
    MATERIEL = "matériel", _("Matériel")
    PRIX = "prix", _("Prix / Récompenses")
    MENTORS = "mentors", _("Mentors / Experts")


# ---------------------------------------------------------------------------
# Secteurs d'activité (utilisés pour le filtre et la recommandation IA)
# ---------------------------------------------------------------------------

SECTOR_CHOICES = [
    ("tech", _("Technologie / Informatique")),
    ("finance", _("Finance / Banque")),
    ("sante", _("Santé / Biotech")),
    ("education", _("Éducation / Formation")),
    ("energie", _("Énergie / Environnement")),
    ("industrie", _("Industrie / Manufacturing")),
    ("media", _("Médias / Communication")),
    ("retail", _("Commerce / Distribution")),
    ("autre", _("Autre")),
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
        verbose_name=_("Nom de l'entreprise"),
    )
    logo = models.ImageField(
        upload_to=logo_upload_path,
        blank=True,
        null=True,
        verbose_name=_("Logo"),
        help_text=_("Format recommandé : PNG/SVG, fond transparent, max 2 Mo."),
    )
    website = models.URLField(
        blank=True,
        verbose_name=_("Site web"),
    )
    sector = models.CharField(
        max_length=50,
        choices=SECTOR_CHOICES,
        default="tech",
        verbose_name=_("Secteur d'activité"),
    )
    description = models.TextField(
        blank=True,
        verbose_name=_("Description"),
        help_text=_("Présentation courte utilisée sur la page publique."),
    )
    contact_name = models.CharField(
        max_length=255,
        blank=True,
        verbose_name=_("Nom du contact"),
    )
    contact_email = models.EmailField(
        blank=True,
        verbose_name=_("Email du contact"),
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_("Créé le"))
    updated_at = models.DateTimeField(auto_now=True, verbose_name=_("Modifié le"))

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
        verbose_name=_("Niveau (tier)"),
    )
    amount = models.DecimalField(
        max_digits=12,
        decimal_places=3,
        default=0,
        validators=[MinValueValidator(0)],
        verbose_name=_("Montant (DT)"),
        help_text=_("Montant financier de la contribution en DT (ex: 2500.000 DT). 0 si non-financier."),
    )
    status = models.CharField(
        max_length=20,
        choices=StatusChoices.choices,
        default=StatusChoices.PROSPECT,
        verbose_name=_("Statut"),
    )
    contribution_type = models.CharField(
        max_length=20,
        choices=ContributionTypeChoices.choices,
        default=ContributionTypeChoices.FINANCIER,
        verbose_name=_("Type de contribution"),
    )
    notes = models.TextField(
        blank=True,
        verbose_name=_("Notes internes"),
        help_text=_("Remarques visibles uniquement par l'équipe organisatrice."),
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_("Créé le"))
    updated_at = models.DateTimeField(auto_now=True, verbose_name=_("Modifié le"))

    class Meta:
        verbose_name = _("Partenariat (Sponsorship)")
        verbose_name_plural = _("Partenariats (Sponsorships)")
        ordering = ["tier", "sponsor__name"]
        # Un sponsor ne peut être lié qu'une seule fois à un hackathon donné
        unique_together = [("sponsor", "hackathon")]

    def __str__(self):
        return f"{self.sponsor.name} → {self.hackathon.name} [{self.get_tier_display()}]"

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
        verbose_name=_("Partenariat"),
    )
    old_status = models.CharField(
        max_length=20,
        choices=StatusChoices.choices,
        verbose_name=_("Ancien statut"),
    )
    new_status = models.CharField(
        max_length=20,
        choices=StatusChoices.choices,
        verbose_name=_("Nouveau statut"),
    )
    changed_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        related_name="sponsorship_status_changes",
        verbose_name=_("Modifié par"),
    )
    changed_at = models.DateTimeField(
        default=timezone.now,
        verbose_name=_("Date du changement"),
    )

    class Meta:
        verbose_name = _("Historique de statut")
        verbose_name_plural = _("Historiques de statut")
        ordering = ["-changed_at"]

    def __str__(self):
        return (
            f"{self.sponsorship} : "
            f"{self.get_old_status_display()} → {self.get_new_status_display()} "
            f"({self.changed_at:%d/%m/%Y %H:%M})"
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
        verbose_name=_("Envoyé par"),
    )
    subject = models.CharField(
        max_length=255,
        verbose_name=_("Objet"),
    )
    body = models.TextField(
        verbose_name=_("Message"),
    )
    sent_at = models.DateTimeField(
        default=timezone.now,
        verbose_name=_("Date d'envoi"),
    )
    success = models.BooleanField(
        default=True,
        verbose_name=_("Succès"),
    )
    ai_generated = models.BooleanField(
        default=False,
        verbose_name=_("Généré par IA"),
    )
    error_message = models.TextField(
        blank=True,
        verbose_name=_("Erreur éventuelle"),
    )

    class Meta:
        verbose_name = _("Journal d'email sponsor")
        verbose_name_plural = _("Journaux d'emails sponsors")
        ordering = ["-sent_at"]

    def __str__(self):
        status_str = "OK" if self.success else "Échec"
        return f"[{status_str}] {self.sponsor.name} : {self.subject} ({self.sent_at:%d/%m/%Y %H:%M})"

