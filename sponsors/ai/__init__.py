"""
Module IA pour la Gestion des Sponsors — HackFlow ESPRIT.

Comprend :
1. Moteur de recommandation vectoriel (TF-IDF + Cosine Similarity) sans clé API.
2. Générateur de messages de prospection par IA (LLM optionnel avec fallback modèle).
"""

from .recommender import get_hackathon_text, get_sponsor_text, recommend_sponsors_for_hackathon
from .email_generator import generate_prospecting_email

__all__ = [
    "get_hackathon_text",
    "get_sponsor_text",
    "recommend_sponsors_for_hackathon",
    "generate_prospecting_email",
]
