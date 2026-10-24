"""
Générateur de messages de prospection par Intelligence Artificielle (Staff only).

Règles de sécurité et RGPD :
- Données transmises au LLM : STRICTEMENT nom, secteur, description publique, et infos publiques du hackathon.
- Données STRICTEMENT EXCLUES : amount, notes, contact_name, contact_email (aucun secret ni donnée sensible).
- En l'absence de clé API (ANTHROPIC_API_KEY vide), ou en cas d'erreur/timeout (15s) :
  repli transparent sur le modèle standard via compose_email() avec notification explicite.
- Aucun envoi direct : le texte est injecté dans le formulaire pour relecture et édition par l'organisateur.
"""

import json
import logging
import os
import urllib.error
import urllib.request
from typing import Any, Dict, Optional, Tuple

from django.conf import settings
from sponsors.models import Sponsor
from sponsors.services import check_and_increment_email_rate_limit, compose_email

logger = logging.getLogger(__name__)

# Modèle et prompt système lisibles et configurables
DEFAULT_AI_MODEL = "claude-haiku-5-5"
API_TIMEOUT_SECONDS = 15

PROMPT_SYSTEM_EMAIL = (
    "Tu es le responsable des partenariats et du sponsoring de l'école d'ingénieurs ESPRIT (HackFlow). "
    "Tu rédiges des propositions de sponsoring courtes, professionnelles, percutantes et bienveillantes. "
    "CONSIGNES STRICTES :\n"
    "- Reste concis (100 à 150 mots maximum).\n"
    "- N'invente AUCUN chiffre financier, pack monétaire ou promesse commerciale non vérifiée.\n"
    "- Mets en valeur l'affinité entre le domaine d'activité de l'entreprise et les défis du hackathon.\n"
    "- Propose un court échange téléphonique ou visio pour présenter le dossier de partenariat.\n"
    "- Réponds EXACTEMENT selon ce format :\n"
    "OBJET: [Ton objet d'email accrocheur]\n\n"
    "[Corps du message]"
)


def get_ai_config() -> tuple:
    """Récupère la clé API et le modèle depuis l'environnement ou les settings Django."""
    api_key = os.getenv("ANTHROPIC_API_KEY", getattr(settings, "ANTHROPIC_API_KEY", "")).strip()
    model = os.getenv("AI_MODEL", getattr(settings, "AI_MODEL", DEFAULT_AI_MODEL)).strip() or DEFAULT_AI_MODEL
    return api_key, model


def build_sanitized_ai_payload(
    sponsor: Sponsor,
    hackathon=None,
    tone: str = "professionnel",
) -> Dict[str, Any]:
    """
    Construit le payload destiné au LLM en garantissant l'exclusion totale
    des données sensibles ou confidentielles (montants, notes internes, contacts).
    """
    hackathon_name = getattr(hackathon, "name", "") or "notre prochain Hackathon d'innovation"
    hackathon_theme = getattr(hackathon, "theme", "") or "Innovation technologique et ingénierie logicielle"

    dates = ""
    start_date = getattr(hackathon, "start_date", None)
    end_date = getattr(hackathon, "end_date", None)
    if start_date and end_date:
        dates = f"du {start_date} au {end_date}"

    sector_label = sponsor.get_sector_display() if hasattr(sponsor, "get_sector_display") else sponsor.sector

    user_instructions = (
        f"Rédige une invitation de partenariat personnalisée avec un ton {tone}.\n\n"
        f"Informations sur l'entreprise sponsor :\n"
        f"- Nom : {sponsor.name}\n"
        f"- Secteur : {sector_label}\n"
        f"- Description publique : {sponsor.description or 'Entreprise leader de son secteur'}\n\n"
        f"Informations sur l'événement :\n"
        f"- Hackathon : {hackathon_name}\n"
        f"- Thème : {hackathon_theme}\n"
    )
    if dates:
        user_instructions += f"- Dates : {dates}\n"

    return {
        "sponsor_name": sponsor.name,
        "sector": sector_label,
        "description": sponsor.description or "",
        "hackathon_name": hackathon_name,
        "hackathon_theme": hackathon_theme,
        "user_instructions": user_instructions,
    }


def parse_llm_response(text: str) -> Tuple[str, str]:
    """Extrait l'objet et le corps du message à partir de la réponse du LLM."""
    subject = "Proposition de partenariat officiel — HackFlow ESPRIT"
    body = text.strip()

    lines = body.splitlines()
    for i, line in enumerate(lines):
        clean_line = line.strip()
        if clean_line.upper().startswith("OBJET:") or clean_line.upper().startswith("SUBJECT:"):
            subject = clean_line.split(":", 1)[1].strip()
            # Le reste des lignes constitue le corps
            body = "\n".join(lines[i + 1:]).strip()
            break

    return subject, body


def generate_prospecting_email(
    sponsor: Sponsor,
    hackathon=None,
    tone: str = "professionnel",
    template_key: str = "invitation",
    user=None,
) -> Dict[str, Any]:
    """
    Génère un email de prospection contextualisé.
    Si l'IA est indisponible ou non configurée, bascule automatiquement sur les modèles standard.
    """
    # 1. Vérification de la limite anti-abus si un utilisateur est fourni
    if user and hasattr(user, "pk") and not check_and_increment_email_rate_limit(user.pk):
        fallback = compose_email(sponsor=sponsor, hackathon=hackathon, template_key=template_key)
        return {
            "subject": fallback["subject"],
            "body": fallback["body"],
            "ai_generated": False,
            "notice": "Limite d'appels atteinte (max 5/min) — modèle standard utilisé.",
        }

    api_key, model = get_ai_config()

    # 2. Repli immédiat si aucune clé API n'est renseignée
    if not api_key:
        fallback = compose_email(sponsor=sponsor, hackathon=hackathon, template_key=template_key)
        return {
            "subject": fallback["subject"],
            "body": fallback["body"],
            "ai_generated": False,
            "notice": "IA indisponible (clé API non configurée) — modèle standard utilisé.",
        }

    # 3. Préparation du payload filtré (RGPD / Confidentialité)
    sanitized_data = build_sanitized_ai_payload(sponsor, hackathon, tone=tone)

    headers = {
        "x-api-key": api_key,
        "anthropic-version": "2023-06-01",
        "content-type": "application/json",
    }
    request_body = json.dumps({
        "model": model,
        "max_tokens": 600,
        "system": PROMPT_SYSTEM_EMAIL,
        "messages": [
            {
                "role": "user",
                "content": sanitized_data["user_instructions"],
            }
        ],
    }).encode("utf-8")

    # 4. Appel avec timeout court (15 secondes) et repli transparent en cas d'erreur
    try:
        req = urllib.request.Request(
            "https://api.anthropic.com/v1/messages",
            data=request_body,
            headers=headers,
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=API_TIMEOUT_SECONDS) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            content_blocks = data.get("content", [])
            raw_text = content_blocks[0].get("text", "") if content_blocks else ""

            if raw_text:
                subject, body = parse_llm_response(raw_text)
                return {
                    "subject": subject,
                    "body": body,
                    "ai_generated": True,
                    "notice": f"Message généré avec succès par l'IA ({model}). Vous pouvez l'éditer avant l'envoi.",
                }
    except Exception as exc:
        err_msg = str(exc)
        if api_key and api_key in err_msg:
            err_msg = err_msg.replace(api_key, "[REDACTED_API_KEY]")
        logger.warning("Échec de la génération IA pour le sponsor %s: %s", sponsor.pk, err_msg)

    # Repli en cas d'exception ou timeout
    fallback = compose_email(sponsor=sponsor, hackathon=hackathon, template_key=template_key)
    return {
        "subject": fallback["subject"],
        "body": fallback["body"],
        "ai_generated": False,
        "notice": "IA indisponible (service momentanément injoignable) — modèle standard utilisé.",
    }
