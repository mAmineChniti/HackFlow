"""
Service IA pour HackFlow — Analyse et catégorisation de projets avec Google Gemini (avec fallback intelligent).
Deux fonctionnalités d'évaluation IA à forte valeur ajoutée :
  1. analyse_project()     -> Score prédictif /10, avis du jury IA, points forts et axes d'amélioration.
  2. detect_category()     -> Détection automatique et intelligente de la catégorie selon le pitch et la description.
"""

import json
import logging
import os
import re

logger = logging.getLogger(__name__)

# Récupération de la clé API
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "").strip()

CATEGORY_CHOICES = {
    "web": "Développement Web",
    "mobile": "Application Mobile",
    "ai": "Intelligence Artificielle & Data",
    "iot": "IoT & Systèmes Embarqués",
    "cyber": "Cybersécurité",
    "green": "GreenTech & Climat",
    "other": "Autre Catégorie",
}


def _get_gemini_model():
    """Initialise et retourne le modèle Gemini si une clé valide est disponible."""
    api_key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not api_key or "your_gemini_api_key" in api_key:
        return None
    try:
        import google.generativeai as genai
        genai.configure(api_key=api_key)
        return genai.GenerativeModel("gemini-1.5-flash")
    except Exception as e:
        logger.warning(f"Erreur initialisation Gemini: {e}")
        return None


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
        strengths.append("Description détaillée et structurée.")
    else:
        weaknesses.append("La description est concise, gagne à être étoffée.")

    if any(k in words for k in ["api", "django", "react", "ia", "base de données", "architecture", "docker"]):
        score += 1
        strengths.append("Technologies et stack technique bien explicitées.")

    if any(k in words for k in ["problème", "besoin", "utilisateurs", "impact", "solution"]):
        score += 1
        strengths.append("Bonne identification du problème et de la proposition de valeur.")
    else:
        weaknesses.append("Préciser l'impact direct et la cible d'utilisateurs visée.")

    if not weaknesses:
        weaknesses.append("Prévoir une démonstration vidéo ou un prototype interactif.")

    score = min(10, max(5, score))

    comment = (
        f"Projet prometteur dans la catégorie {category}. "
        f"L'idée générale est claire et répond à une problématique identifiable. "
        f"Pour maximiser la note finale du jury, insistez sur la faisabilité technique et la démonstration en direct."
    )

    return {
        "score": score,
        "comment": comment,
        "strengths": strengths,
        "weaknesses": weaknesses,
        "source": "moteur IA heuristique (configurez GEMINI_API_KEY dans .env pour le modèle distant)",
        "source_key": "heuristic",
    }


def analyse_project(title: str, tagline: str, description: str, category: str) -> dict:
    """
    Évalue un projet étudiant avec Google Gemini.
    Retourne :
      - score       : int (1-10)
      - comment     : str (évaluation globale du jury IA)
      - strengths   : list[str] (points forts)
      - weaknesses  : list[str] (pistes d'amélioration)
      - source      : 'Google Gemini 1.5 Flash' ou 'IA Locale'
    """
    model = _get_gemini_model()
    if not model:
        return _fallback_analyse(title, tagline, description, category)

    prompt = f"""Tu es un jury expert d'un hackathon tech d'élite.
Évalue objectivement ce projet étudiant soumis pour le hackathon.

**Fiche Projet :**
- Titre : {title}
- Slogan : {tagline}
- Catégorie : {category}
- Description : {description[:1600]}

**Critères :** Innovation, faisabilité technique, impact/utilité, clarté.

Réponds UNIQUEMENT sous forme de JSON strict et valide :
{{
  "score": <entier de 1 à 10>,
  "comment": "<commentaire d'évaluation constructif en français, 2-3 phrases>",
  "strengths": ["<point fort 1>", "<point fort 2>"],
  "weaknesses": ["<axe d'amélioration 1>", "<axe d'amélioration 2>"]
}}
"""

    try:
        response = model.generate_content(prompt)
        text = response.text.strip()
        if "```" in text:
            match = re.search(r"```(?:json)?(.*?)```", text, re.DOTALL)
            if match:
                text = match.group(1).strip()
        data = json.loads(text)
        return {
            "score": max(1, min(10, int(data.get("score", 7)))),
            "comment": data.get("comment", "Évaluation générée avec succès."),
            "strengths": data.get("strengths", [])[:3],
            "weaknesses": data.get("weaknesses", [])[:3],
            "source": "Google Gemini 1.5 Flash",
            "source_key": "remote",
        }
    except Exception as e:
        # Log the detail server-side only: returning str(e) to the browser can
        # expose endpoint URLs, project ids and credential-related messages.
        logger.warning("Erreur appel Gemini analyse_project: %s", e)
        fallback = _fallback_analyse(title, tagline, description, category)
        fallback["failed"] = True
        return fallback


# ─────────────────────────────────────────────────────────────────────────────
# 2. DÉTECTION AUTOMATIQUE DE CATÉGORIE VIA IA
# ─────────────────────────────────────────────────────────────────────────────

def _fallback_detect_category(title: str, description: str) -> dict:
    """Détection heuristique de secours par analyse de mots-clés sémantiques."""
    text = f"{title} {description}".lower()

    keywords = {
        "ai": ["ia", "intelligence artificielle", "machine learning", "deep learning", "nlp", "llm", "chat", "modèle", "data", "vision"],
        "cyber": ["sécurité", "cyber", "pentest", "chiffrement", "vulnerability", "auth", "authentification", "firewall"],
        "iot": ["iot", "arduino", "raspberry", "capteur", "embarqué", "hardware", "bluetooth", "robot"],
        "green": ["vert", "écologie", "climat", "carbone", "recyclage", "énergie", "green", "durable", "déchet"],
        "mobile": ["mobile", "android", "ios", "react native", "flutter", "smartphone", "application mobile"],
        "web": ["web", "site", "plateforme", "django", "react", "html", "portail", "saas", "dashboard"],
    }

    best_cat = "other"
    max_matches = 0
    for cat, words in keywords.items():
        matches = sum(1 for w in words if re.search(r"\b" + re.escape(w) + r"\b", text))
        if matches > max_matches:
            max_matches = matches
            best_cat = cat

    confidence = "haute" if max_matches >= 3 else ("moyenne" if max_matches >= 1 else "faible")
    return {
        "category": best_cat,
        "category_label": CATEGORY_CHOICES.get(best_cat, "Autre Catégorie"),
        "confidence": confidence,
        "reason": f"Mots-clés pertinents détectés pour la catégorie {CATEGORY_CHOICES.get(best_cat, 'Autre')}.",
        "source": "Analyse sémantique locale",
        "source_key": "heuristic",
    }


def detect_category(title: str, description: str) -> dict:
    """
    Analyse le titre et la description et suggère automatiquement la catégorie idoine.
    """
    model = _get_gemini_model()
    if not model:
        return _fallback_detect_category(title, description)

    categories_list = "\n".join([f'- "{k}": {v}' for k, v in CATEGORY_CHOICES.items()])

    prompt = f"""Tu es un assistant IA pour un hackathon tech.
Analyse ce projet et détermine la catégorie la plus adaptée parmi la liste fournie.

**Projet :**
- Titre : {title}
- Description : {description[:800]}

**Catégories acceptées :**
{categories_list}

Réponds UNIQUEMENT sous forme de JSON strict :
{{
  "category": "<clé exacte parmi : web, mobile, ai, iot, cyber, green, other>",
  "confidence": "<haute | moyenne | faible>",
  "reason": "<explication courte en 1 phrase>"
}}
"""

    try:
        response = model.generate_content(prompt)
        text = response.text.strip()
        if "```" in text:
            match = re.search(r"```(?:json)?(.*?)```", text, re.DOTALL)
            if match:
                text = match.group(1).strip()
        data = json.loads(text)
        cat_key = data.get("category", "other")
        if cat_key not in CATEGORY_CHOICES:
            cat_key = "other"
        return {
            "category": cat_key,
            "category_label": CATEGORY_CHOICES[cat_key],
            "confidence": data.get("confidence", "moyenne"),
            "reason": data.get("reason", "Catégorie déterminée par analyse sémantique Gemini."),
            "source": "Google Gemini 1.5 Flash",
            "source_key": "remote",
        }
    except Exception as e:
        logger.warning("Erreur appel Gemini detect_category: %s", e)
        fallback = _fallback_detect_category(title, description)
        fallback["failed"] = True
        return fallback
