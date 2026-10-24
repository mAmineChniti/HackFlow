"""
Services métier pour le module Gestion des Sponsors — HackFlow ESPRIT.

Contient :
1. L'unique implémentation de transition des statuts avec verrouillage transactionnel (select_for_update).
2. La composition et l'envoi d'emails aux sponsors avec gestion d'erreurs, audit trail et rate limiting.
"""

import logging
from typing import Optional, Union, Tuple
from django.conf import settings
from django.contrib.auth.models import User
from django.core.cache import cache
from django.core.mail import send_mail
from django.db import transaction
from .models import Sponsor, Sponsorship, StatusHistory, StatusChoices, SponsorEmailLog

logger = logging.getLogger(__name__)

EMAIL_RATE_LIMIT_MAX = 5  # Max 5 emails par minute
EMAIL_RATE_LIMIT_WINDOW = 60  # Fenêtre en secondes


# ==============================================================================
# GESTION DES STATUTS (Unique source de vérité)
# ==============================================================================

def change_sponsorship_status(
    sponsorship: Union[Sponsorship, int],
    new_status: str,
    changed_by: Optional[User] = None,
) -> Optional[StatusHistory]:
    """
    Unique implémentation du changement de statut d'un partenariat dans l'application.

    Garanties :
    1. Validation stricte du statut parmi StatusChoices.
    2. Concurrence : verrouillage pessimiste via select_for_update() dans transaction.atomic().
    3. Idempotence : si le nouveau statut est identique au statut actuel, aucune écriture
       n'est effectuée et la fonction retourne None (pas de doublon dans StatusHistory).
    4. Traçabilité : création d'une entrée StatusHistory atomiquement liée à la mise à jour.
    """
    valid_statuses = dict(StatusChoices.choices)
    if new_status not in valid_statuses:
        raise ValueError(
            f"Statut « {new_status} » non valide. Choix possibles : {list(valid_statuses.keys())}"
        )

    sponsorship_id = sponsorship.pk if isinstance(sponsorship, Sponsorship) else sponsorship

    with transaction.atomic():
        # Verrouillage pessimiste de la ligne en base de données
        locked_sponsorship = Sponsorship.objects.select_for_update().get(pk=sponsorship_id)

        # Si le statut est identique, aucune modification ni historique
        if locked_sponsorship.status == new_status:
            return None

        old_status = locked_sponsorship.status
        locked_sponsorship.status = new_status
        locked_sponsorship.save(update_fields=["status", "updated_at"])

        history = StatusHistory.objects.create(
            sponsorship=locked_sponsorship,
            old_status=old_status,
            new_status=new_status,
            changed_by=changed_by,
        )

        # Mettre à jour l'instance en mémoire si elle a été fournie
        if isinstance(sponsorship, Sponsorship):
            sponsorship.status = new_status

        return history


# ==============================================================================
# COMPOSITION ET ENVOI D'EMAILS AUX SPONSORS
# ==============================================================================

EMAIL_TEMPLATES = {
    "invitation": {
        "label": "Invitation à devenir sponsor",
        "subject": "Invitation à soutenir le hackathon {hackathon_name} — HackFlow ESPRIT",
        "body": (
            "Bonjour {contact_salutation},\n\n"
            "Au nom du comité d'organisation du hackathon {hackathon_name}, nous serions très honorés "
            "de compter {sponsor_name} parmi nos partenaires et sponsors officiels.\n\n"
            "Cet événement réunira les talents les plus prometteurs d'ESPRIT autour de défis techniques d'envergure. "
            "Plusieurs packs de sponsoring (Platinum, Gold, Silver, Bronze) sont à votre disposition pour vous offrir une visibilité "
            "maximale et un accès privilégié à nos étudiants ingénieurs.\n\n"
            "Seriez-vous disponible pour un court échange afin de vous présenter le dossier de partenariat ?\n\n"
            "Bien cordialement,\n"
            "L'équipe organisatrice HackFlow ESPRIT"
        ),
    },
    "relance": {
        "label": "Relance de proposition de partenariat",
        "subject": "Suivi de notre proposition de partenariat pour {hackathon_name}",
        "body": (
            "Bonjour {contact_salutation},\n\n"
            "Nous nous permettons de vous relancer suite à notre précédente communication concernant le hackathon {hackathon_name}.\n\n"
            "Les inscriptions avancent à grand pas et nous finalisons actuellement la liste des entreprises partenaires. "
            "Nous serions ravis de concrétiser la participation de {sponsor_name}.\n\n"
            "Restant à votre entière disposition pour tout complément d'information,\n\n"
            "Excellente journée,\n"
            "L'équipe HackFlow ESPRIT"
        ),
    },
    "remerciement": {
        "label": "Remerciement pour le partenariat",
        "subject": "Remerciements chaleureux pour votre soutien à {hackathon_name} !",
        "body": (
            "Bonjour {contact_salutation},\n\n"
            "Toute l'équipe de HackFlow tient à adresser ses plus vifs remerciements à {sponsor_name} "
            "pour votre précieux soutien lors du hackathon {hackathon_name}.\n\n"
            "Grâce à votre contribution, nos étudiants ont pu relever des défis formidables et donner vie à des projets innovants. "
            "Nous espérons avoir le plaisir de renouveler ce partenariat lors de nos prochaines éditions !\n\n"
            "Très sincèrement,\n"
            "L'équipe HackFlow ESPRIT"
        ),
    },
}


def compose_email(
    sponsor: Sponsor,
    hackathon=None,
    template_key: str = "invitation",
) -> dict:
    """
    Génère un objet et un corps de message préremplis selon le modèle choisi.
    Cette fonction est conçue pour être branchée sur le service IA ultérieurement.
    """
    hackathon_name = hackathon.name if hackathon else "notre prochain Hackathon"
    contact_salutation = sponsor.contact_name or sponsor.name

    template_data = EMAIL_TEMPLATES.get(template_key, EMAIL_TEMPLATES["invitation"])

    subject = template_data["subject"].format(
        sponsor_name=sponsor.name,
        hackathon_name=hackathon_name,
    )
    body = template_data["body"].format(
        contact_salutation=contact_salutation,
        sponsor_name=sponsor.name,
        hackathon_name=hackathon_name,
    )

    return {
        "subject": subject,
        "body": body,
        "recipient": sponsor.contact_email,
    }


def check_and_increment_email_rate_limit(user_id: int) -> bool:
    """
    Vérifie et applique la limite anti-abus : max 5 emails par minute par utilisateur.
    Retourne True si l'envoi est autorisé, False si la limite est dépassée.
    """
    cache_key = f"sponsor_email_throttle_{user_id}"
    current_count = cache.get(cache_key, 0)

    if current_count >= EMAIL_RATE_LIMIT_MAX:
        return False

    cache.set(cache_key, current_count + 1, timeout=EMAIL_RATE_LIMIT_WINDOW)
    return True


def send_sponsor_contact_email(
    sponsor: Sponsor,
    sent_by: User,
    subject: str,
    body: str,
    ai_generated: bool = False,
) -> Tuple[SponsorEmailLog, bool]:
    """
    Envoie un email au contact_email du sponsor et enregistre le journal d'audit SponsorEmailLog.

    Sécurité et résilience :
    - Le destinataire est STRICTEMENT sponsor.contact_email.
    - Application de la limite de 5 emails par minute.
    - Capture des exceptions sans crash : success=False enregistré dans le log.
    - Traçabilité du flag ai_generated dans SponsorEmailLog.
    - Retourne le tuple (log, success).
    """
    recipient = (sponsor.contact_email or "").strip()
    if not recipient:
        log = SponsorEmailLog.objects.create(
            sponsor=sponsor,
            sent_by=sent_by,
            subject=subject,
            body=body,
            ai_generated=ai_generated,
            success=False,
            error_message="Aucune adresse email de contact renseignée pour ce sponsor.",
        )
        return log, False

    # Vérification de la limite anti-abus (5/min)
    if not check_and_increment_email_rate_limit(sent_by.pk):
        log = SponsorEmailLog.objects.create(
            sponsor=sponsor,
            sent_by=sent_by,
            subject=subject,
            body=body,
            ai_generated=ai_generated,
            success=False,
            error_message="Limite anti-abus dépassée (maximum 5 emails par minute).",
        )
        return log, False

    from_email = getattr(settings, "DEFAULT_FROM_EMAIL", "HackFlow <hello@hackflow.dev>")

    try:
        send_mail(
            subject=subject,
            message=body,
            from_email=from_email,
            recipient_list=[recipient],
            fail_silently=False,
        )
        log = SponsorEmailLog.objects.create(
            sponsor=sponsor,
            sent_by=sent_by,
            subject=subject,
            body=body,
            ai_generated=ai_generated,
            success=True,
            error_message="",
        )
        return log, True
    except Exception as exc:
        logger.exception("Échec d'envoi d'email au sponsor %s (%s)", sponsor.pk, recipient)
        log = SponsorEmailLog.objects.create(
            sponsor=sponsor,
            sent_by=sent_by,
            subject=subject,
            body=body,
            ai_generated=ai_generated,
            success=False,
            error_message=str(exc),
        )
        return log, False
