"""
Service IA pour HackFlow — Analyse et catégorisation de projets avec Groq (avec fallback intelligent).
Deux fonctionnalités d'évaluation IA à forte valeur ajoutée :
  1. analyse_project()     -> Score prédictif /10, avis du jury IA, points forts et axes d'amélioration.
  2. detect_category()     -> Détection automatique et intelligente de la catégorie selon le pitch et la description.
"""

import json
import logging
import re
from time import perf_counter

from core.ai_metrics import record_ai_run
from core.groq import DEFAULT_AI_MODEL, call_groq, get_api_key, get_model

logger = logging.getLogger(__name__)

# Kept as a module-level alias for backwards compatibility; actual calls go
# through core.groq and read AI_MODEL dynamically.
DEFAULT_MODEL = DEFAULT_AI_MODEL

CATEGORY_CHOICES = {
    "web": "Web Development",
    "mobile": "Mobile Application",
    "ai": "Artificial Intelligence & Data",
    "iot": "IoT & Embedded Systems",
    "cyber": "Cybersecurity",
    "green": "GreenTech & Climate",
    "other": "Other",
}


def _get_groq_client():
    """Return the configured Groq key, or ``None`` when the fallback should run."""
    api_key = get_api_key()
    if not api_key:
        logger.warning("GROQ_API_KEY not configured or contains placeholder - using fallback")
        return None
    return api_key


def _call_groq_api(prompt: str) -> str | None:
    """Call the shared Groq client (kept as a test/mocking seam)."""
    return call_groq(prompt, max_tokens=600)


# ─────────────────────────────────────────────────────────────────────────────
# 1. ÉVALUATION IA & FEEDBACK DU PROJET (Score /10 + Forces + Faiblesses)
# ─────────────────────────────────────────────────────────────────────────────


def _fallback_analyse(title: str, tagline: str, description: str, category: str) -> dict:
    """Analyse heuristique de secours si l'API externe n'a pas encore de clé renseignée."""
    desc_len = len(description.strip()) if description else 0
    words = (title + " " + tagline + " " + description).lower()

    # Calcul de score heuristique basé sur la complétude et clarté
    score = 6
    strengths = []
    weaknesses = []

    if desc_len > 300:
        score += 1
        strengths.append("The description is detailed and well structured.")
    else:
        weaknesses.append("The description is concise and could be expanded.")

    if any(
        k in words
        for k in ["api", "django", "react", "ia", "base de données", "architecture", "docker"]
    ):
        score += 1
        strengths.append("The technology stack is clearly explained.")

    if any(k in words for k in ["problème", "besoin", "utilisateurs", "impact", "solution"]):
        score += 1
        strengths.append("The problem and value proposition are clearly identified.")
    else:
        weaknesses.append("Clarify the direct impact and target user group.")

    if not weaknesses:
        weaknesses.append("Consider adding a video demo or an interactive prototype.")

    score = min(10, max(5, score))

    comment = (
        f"A promising project in the {category} category. "
        f"The overall idea is clear and addresses an identifiable problem. "
        f"To maximize the final jury score, emphasize technical feasibility and a live demonstration."
    )

    return {
        "score": score,
        "comment": comment,
        "strengths": strengths,
        "weaknesses": weaknesses,
        "source": "Heuristic AI engine (set GROQ_API_KEY in .env to use the remote model)",
        "source_key": "heuristic",
    }


def analyse_project(
    title: str,
    tagline: str,
    description: str,
    category: str,
    *,
    mode: str = "sync",
) -> dict:
    """
    Évalue un projet étudiant avec Groq.
    Retourne :
      - score       : int (1-10)
      - comment     : str (évaluation globale du jury IA)
      - strengths   : list[str] (points forts)
      - weaknesses  : list[str] (pistes d'amélioration)
      - source      : 'Groq' ou 'IA Locale'
    """
    started = perf_counter()

    def finish(result: dict) -> dict:
        record_ai_run(
            "project_evaluation",
            result.get("source_key", "unknown"),
            (perf_counter() - started) * 1000,
            mode=mode,
            success=not result.get("failed", False),
        )
        return result

    prompt = f"""You are an expert jury member for an elite tech hackathon.
Objectively evaluate this student project submitted for the hackathon.

**Project details:**
- Title: {title}
- Tagline: {tagline}
- Category: {category}
- Description: {description[:1600]}

**Criteria:** Innovation, technical feasibility, impact/usefulness, clarity.

Respond ONLY with strict, valid JSON:
{{
  "score": <integer from 1 to 10>,
  "comment": "<constructive evaluation comment in English, 2-3 sentences>",
  "strengths": ["<strength 1>", "<strength 2>"],
  "weaknesses": ["<improvement area 1>", "<improvement area 2>"]
}}
"""

    raw_text = _call_groq_api(prompt)
    if not raw_text:
        return finish(_fallback_analyse(title, tagline, description, category))

    try:
        if "```" in raw_text:
            match = re.search(r"```(?:json)?(.*?)```", raw_text, re.DOTALL)
            if match:
                raw_text = match.group(1).strip()
        data = json.loads(raw_text)
        return finish(
            {
                "score": max(1, min(10, int(data.get("score", 7)))),
                "comment": data.get("comment", "Evaluation generated successfully."),
                "strengths": data.get("strengths", [])[:3],
                "weaknesses": data.get("weaknesses", [])[:3],
                "source": f"Groq ({get_model()})",
                "source_key": "remote",
            }
        )
    except Exception as e:
        # Log the detail server-side only: returning str(e) to the browser can
        # expose endpoint URLs, project ids and credential-related messages.
        logger.warning("Error parsing Groq response in analyse_project: %s", e)
        fallback = _fallback_analyse(title, tagline, description, category)
        fallback["failed"] = True
        return finish(fallback)


# ─────────────────────────────────────────────────────────────────────────────
# 2. DÉTECTION AUTOMATIQUE DE CATÉGORIE VIA IA
# ─────────────────────────────────────────────────────────────────────────────


def _fallback_detect_category(title: str, description: str) -> dict:
    """Détection heuristique de secours par analyse de mots-clés sémantiques."""
    text = f"{title} {description}".lower()

    keywords = {
        "ai": [
            "ia",
            "artificial intelligence",
            "intelligence artificielle",
            "machine learning",
            "deep learning",
            "nlp",
            "llm",
            "chat",
            "classifier",
            "generative",
            "neural",
            "modèle",
            "data",
            "vision",
        ],
        "cyber": [
            "sécurité",
            "cyber",
            "cybersecurity",
            "security",
            "phishing",
            "encryption",
            "malware",
            "pentest",
            "chiffrement",
            "vulnerability",
            "threat",
            "auth",
            "authentification",
            "firewall",
        ],
        "iot": [
            "iot",
            "arduino",
            "raspberry",
            "capteur",
            "sensor",
            "sensors",
            "embedded",
            "embarqué",
            "microcontroller",
            "hardware",
            "bluetooth",
            "robot",
            "drone",
        ],
        "green": [
            "vert",
            "écologie",
            "climat",
            "carbon",
            "carbone",
            "recycling",
            "recyclage",
            "energy",
            "énergie",
            "green",
            "durable",
            "sustainability",
            "sustainable",
            "waste",
            "déchet",
        ],
        "mobile": [
            "mobile",
            "android",
            "ios",
            "react native",
            "flutter",
            "smartphone",
            "application mobile",
        ],
        "web": [
            "web",
            "website",
            "site",
            "plateforme",
            "django",
            "react",
            "html",
            "portail",
            "portal",
            "saas",
            "dashboard",
        ],
    }

    best_cat = "other"
    max_matches = 0
    for cat, words in keywords.items():
        matches = sum(1 for w in words if re.search(r"\b" + re.escape(w) + r"\b", text))
        if matches > max_matches:
            max_matches = matches
            best_cat = cat

    confidence = "high" if max_matches >= 3 else ("medium" if max_matches >= 1 else "low")
    return {
        "category": best_cat,
        "category_label": CATEGORY_CHOICES.get(best_cat, "Other"),
        "confidence": confidence,
        "reason": f"Relevant keywords detected for the {CATEGORY_CHOICES.get(best_cat, 'Other')} category.",
        "source": "Local semantic analysis",
        "source_key": "heuristic",
    }


def detect_category(title: str, description: str) -> dict:
    """
    Analyse le titre et la description et suggère automatiquement la catégorie idoine.
    """
    started = perf_counter()

    def finish(result: dict) -> dict:
        record_ai_run(
            "category_detection",
            result.get("source_key", "unknown"),
            (perf_counter() - started) * 1000,
            success=not result.get("failed", False),
        )
        return result

    categories_list = "\n".join([f'- "{k}": {v}' for k, v in CATEGORY_CHOICES.items()])

    prompt = f"""You are an AI assistant for a tech hackathon.
Analyze this project and determine the most suitable category from the list provided.

**Project:**
- Title: {title}
- Description: {description[:800]}

**Accepted categories:**
{categories_list}

Respond ONLY with strict JSON:
{{
  "category": "<exact key among: web, mobile, ai, iot, cyber, green, other>",
  "confidence": "<high | medium | low>",
  "reason": "<short one-sentence explanation>"
}}
"""

    raw_text = _call_groq_api(prompt)
    if not raw_text:
        return finish(_fallback_detect_category(title, description))

    try:
        if "```" in raw_text:
            match = re.search(r"```(?:json)?(.*?)```", raw_text, re.DOTALL)
            if match:
                raw_text = match.group(1).strip()
        data = json.loads(raw_text)
        cat_key = data.get("category", "other")
        if cat_key not in CATEGORY_CHOICES:
            cat_key = "other"
        return finish(
            {
                "category": cat_key,
                "category_label": CATEGORY_CHOICES[cat_key],
                "confidence": data.get("confidence", "medium"),
                "reason": data.get("reason", "Category determined by Groq semantic analysis."),
                "source": f"Groq ({get_model()})",
                "source_key": "remote",
            }
        )
    except Exception as e:
        # Server-side log only; the browser never sees the exception text.
        logger.warning("Error parsing Groq response in detect_category: %s", e)
        fallback = _fallback_detect_category(title, description)
        fallback["failed"] = True
        return finish(fallback)
