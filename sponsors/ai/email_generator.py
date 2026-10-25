"""
Générateur de messages de prospection par Intelligence Artificielle (Staff only).

Règles de sécurité et RGPD :
- Données transmises au LLM : STRICTEMENT nom, secteur, description publique, et infos publiques du hackathon.
- Données STRICTEMENT EXCLUES : amount, notes, contact_name, contact_email (aucun secret ni donnée sensible).
- En l'absence de clé API (GROQ_API_KEY vide), ou en cas d'erreur/timeout (15s) :
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
DEFAULT_AI_MODEL = "openai/gpt-oss-120b"
API_TIMEOUT_SECONDS = 15

PROMPT_SYSTEM_EMAIL = (
    "You are responsible for partnerships and sponsorships at ESPRIT engineering school (HackFlow). "
    "Write concise, professional, compelling, and considerate sponsorship proposals. "
    "STRICT GUIDELINES:\n"
    "- Keep the message concise (100–150 words maximum).\n"
    "- Do not invent financial figures, package details, or unverified commercial promises.\n"
    "- Highlight the fit between the company's industry and the hackathon challenges.\n"
    "- Suggest a brief call or video meeting to present the partnership proposal.\n"
    "- Respond in EXACTLY this format:\n"
    "SUBJECT: [A compelling email subject]\n\n"
    "[Message body]"
)


def get_ai_config() -> tuple:
    """Get the API key and model from the environment or Django settings."""
    api_key = os.getenv("GROQ_API_KEY", getattr(settings, "GROQ_API_KEY", "")).strip()
    model = os.getenv("AI_MODEL", getattr(settings, "AI_MODEL", DEFAULT_AI_MODEL)).strip() or DEFAULT_AI_MODEL
    # Reject placeholder or empty keys
    if not api_key or api_key.lower() in ("", "none", "null") or "your_api_key" in api_key.lower() or "gsk_" not in api_key:
        logger.warning("GROQ_API_KEY not configured or contains placeholder - using fallback")
        return "", model
    return api_key, model


def build_sanitized_ai_payload(
    sponsor: Sponsor,
    hackathon=None,
    tone: str = "professionnel",
) -> Dict[str, Any]:
    """Build an LLM payload that excludes sensitive or confidential data."""
    hackathon_name = getattr(hackathon, "name", "") or "our next innovation hackathon"
    hackathon_theme = getattr(hackathon, "theme", "") or "Technology innovation and software engineering"

    dates = ""
    start_date = getattr(hackathon, "start_date", None)
    end_date = getattr(hackathon, "end_date", None)
    if start_date and end_date:
        dates = f"from {start_date} to {end_date}"

    sector_label = sponsor.get_sector_display() if hasattr(sponsor, "get_sector_display") else sponsor.sector

    tone_labels = {
        "professionnel": "formal and professional",
        "amical": "friendly and energetic",
    }
    tone_description = tone_labels.get(tone, tone)
    user_instructions = (
        f"Write a personalized sponsorship invitation in a {tone_description} tone.\n\n"
        f"Sponsor company information:\n"
        f"- Name: {sponsor.name}\n"
        f"- Industry: {sector_label}\n"
        f"- Public description: {sponsor.description or 'A leading company in its industry'}\n\n"
        f"Event information:\n"
        f"- Hackathon: {hackathon_name}\n"
        f"- Theme: {hackathon_theme}\n"
    )
    if dates:
        user_instructions += f"- Dates: {dates}\n"

    return {
        "sponsor_name": sponsor.name,
        "sector": sector_label,
        "description": sponsor.description or "",
        "hackathon_name": hackathon_name,
        "hackathon_theme": hackathon_theme,
        "user_instructions": user_instructions,
    }


def parse_llm_response(text: str) -> Tuple[str, str]:
    """Extract the subject and body from an LLM response."""
    subject = "Official sponsorship proposal — HackFlow ESPRIT"
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
            "notice": "AI request limit reached (maximum 5 per minute); using the standard template.",
        }

    api_key, model = get_ai_config()

    # 2. Repli immédiat si aucune clé API n'est renseignée
    if not api_key:
        fallback = compose_email(sponsor=sponsor, hackathon=hackathon, template_key=template_key)
        return {
            "subject": fallback["subject"],
            "body": fallback["body"],
            "ai_generated": False,
            "notice": "AI is unavailable (API key is not configured); using the standard template.",
        }

    # 3. Préparation du payload filtré (RGPD / Confidentialité)
    sanitized_data = build_sanitized_ai_payload(sponsor, hackathon, tone=tone)

    headers = {
        "Authorization": f"Bearer {api_key}",
        "content-type": "application/json",
    }
    request_body = json.dumps({
        "model": model,
        "max_tokens": 600,
        "messages": [
            {
                "role": "system",
                "content": PROMPT_SYSTEM_EMAIL,
            },
            {
                "role": "user",
                "content": sanitized_data["user_instructions"],
            }
        ],
    }).encode("utf-8")

    # 4. Appel avec timeout court (15 secondes) et repli transparent en cas d'erreur
    try:
        req = urllib.request.Request(
            "https://api.groq.com/openai/v1/chat/completions",
            data=request_body,
            headers=headers,
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=API_TIMEOUT_SECONDS) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            choices = data.get("choices", [])
            raw_text = choices[0].get("message", {}).get("content", "") if choices else ""

            if raw_text:
                subject, body = parse_llm_response(raw_text)
                return {
                    "subject": subject,
                    "body": body,
                    "ai_generated": True,
                    "notice": f"Message generated with AI ({model}). You can edit it before sending.",
                }
    except Exception as exc:
        err_msg = str(exc)
        if api_key and api_key in err_msg:
            err_msg = err_msg.replace(api_key, "[REDACTED_API_KEY]")
        logger.warning("AI email generation failed for sponsor %s: %s", sponsor.pk, err_msg)

    # Repli en cas d'exception ou timeout
    fallback = compose_email(sponsor=sponsor, hackathon=hackathon, template_key=template_key)
    return {
        "subject": fallback["subject"],
        "body": fallback["body"],
        "ai_generated": False,
        "notice": "AI is temporarily unavailable; using the standard template.",
    }
