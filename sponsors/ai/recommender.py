"""
Système de recommandation vectorielle de sponsors pour les hackathons (Staff only).

Algorithme :
- Vectorisation TF-IDF (termes unigrammes et bigrammes).
- Calcul de similarité cosinus (cosine similarity) entre le profil du hackathon et chaque sponsor disponible.
- Bonus de fidélité de +10% pour les sponsors ayant déjà confirmé un partenariat lors d'une édition antérieure.
- Extraction des 3 mots-clés d'affinité les plus explicatifs (composantes du produit scalaire TF-IDF).
- Exclusion stricte des sponsors ayant déjà un partenariat pour ce hackathon.
- Aucun appel réseau externe ni clé API nécessaire.
"""

from typing import Any, Dict, List, Tuple

try:
    import numpy as np
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.metrics.pairwise import cosine_similarity
    SKLEARN_AVAILABLE = True
except ImportError:
    SKLEARN_AVAILABLE = False
    np = None
    TfidfVectorizer = None
    cosine_similarity = None

from django.core.cache import cache
from django.db.models import Q, QuerySet

from sponsors.models import Sponsor, Sponsorship, StatusChoices
from sponsors.permissions import sponsors_visible_to, sponsorships_visible_to

# Keep both language stopword sets to support legacy descriptions as well as English content.
FRENCH_STOPWORDS = [
    "de", "des", "du", "le", "la", "les", "un", "une", "et", "en", "pour", "par",
    "sur", "avec", "dans", "au", "aux", "ce", "cet", "cette", "ces", "qui", "que",
    "quoi", "dont", "ou", "mais", "donc", "or", "ni", "car", "plus", "moins", "tres",
    "très", "notre", "nos", "votre", "vos", "leur", "leurs", "son", "sa", "ses",
    "a", "à", "est", "sont", "être", "avoir", "faire", "tout", "tous", "toute", "toutes",
]
ENGLISH_STOPWORDS = [
    "a", "an", "and", "are", "as", "at", "be", "by", "for", "from", "has", "have",
    "in", "is", "it", "its", "of", "on", "or", "our", "that", "the", "their", "this",
    "to", "was", "were", "will", "with", "you", "your",
]


def get_hackathon_text(hackathon) -> str:
    """
    Extrait et normalise le contenu textuel d'un hackathon pour l'analyse vectorielle TF-IDF.
    Isole l'accès aux champs pour s'adapter automatiquement aux évolutions du modèle Hackathon.
    """
    if not hackathon:
        return ""

    parts = [getattr(hackathon, "title", "") or ""]
    for field in ("tagline", "category", "description"):
        value = getattr(hackathon, field, "")
        if value:
            parts.append(value)

    return " ".join(filter(None, parts)).strip()


def get_sponsor_text(sponsor: Sponsor) -> str:
    """
    Extrait et normalise le contenu textuel d'un sponsor : nom, secteur (libellé) et description.
    """
    if not sponsor:
        return ""

    sector_label = sponsor.get_sector_display() if hasattr(sponsor, "get_sector_display") else (sponsor.sector or "")
    parts = [
        sponsor.name or "",
        sector_label or "",
        sponsor.description or "",
    ]
    return " ".join(filter(None, parts)).strip()


def extract_top_keywords(
    hackathon_vec: Any,
    sponsor_vec: Any,
    feature_names: Any,
    top_k: int = 3,
) -> List[str]:
    """
    Extrait les mots-clés les plus contributifs au score de similarité cosinus.
    Calcule le produit terme à terme (dot-product weights).
    """
    # Produit élément par élément des poids TF-IDF
    contributions = hackathon_vec * sponsor_vec
    positive_indices = np.where(contributions > 0)[0]

    if len(positive_indices) > 0:
        # Trier par contribution décroissante
        sorted_indices = positive_indices[np.argsort(-contributions[positive_indices])]
        top_words = [feature_names[idx] for idx in sorted_indices[:top_k]]
        return top_words

    # Fallback : si aucun terme commun, extraire les termes les plus représentatifs du sponsor
    sponsor_indices = np.argsort(-sponsor_vec)
    fallback_words = [
        feature_names[idx] for idx in sponsor_indices if sponsor_vec[idx] > 0
    ][:top_k]
    return fallback_words or ["general match"]


def recommend_sponsors_for_hackathon(
    hackathon,
    top_n: int = 5,
    use_cache: bool = True,
    cache_timeout: int = 300,
    user=None,
) -> Dict[str, Any]:
    """
    Calcule et classe les sponsors les plus pertinents pour un hackathon donné.

    Règles :
    - Exclut les sponsors ayant déjà un partenariat sur ce hackathon.
    - Accorde un bonus de score (+10%) aux sponsors déjà confirmés sur un autre hackathon.
    - Fournit les 3 mots-clés explicatifs par sponsor.
    - Met en cache court (300 s) pour optimiser les performances.
    - Renvoie un message clair et gracieux en cas de données insuffisantes.
    """
    if not hackathon:
        return {
            "recommendations": [],
            "message": "No hackathon was specified.",
        }

    if not SKLEARN_AVAILABLE:
        return {
            "recommendations": [],
            "message": "The vector analysis module (scikit-learn) is unavailable in this environment.",
        }

    user_scope = getattr(user, "pk", "all") if user is not None else "all"
    cache_key = (
        f"sponsor_recommendations_hackathon_{hackathon.pk}_"
        f"top{top_n}_user{user_scope}"
    )
    if use_cache:
        cached_result = cache.get(cache_key)
        if cached_result is not None:
            return cached_result

    hackathon_text = get_hackathon_text(hackathon)
    if not hackathon_text.strip():
        return {
            "recommendations": [],
            "message": "The hackathon details (title, tagline and description) are insufficient to calculate matches.",
        }

    # 1. Exclure les sponsors déjà liés à ce hackathon (en cours, refusés, ou confirmés)
    visible_sponsorships = (
        sponsorships_visible_to(user)
        if user is not None
        else Sponsorship.objects.all()
    )
    existing_sponsor_ids = visible_sponsorships.filter(
        hackathon=hackathon
    ).values_list("sponsor_id", flat=True)

    sponsor_scope = (
        sponsors_visible_to(user)
        if user is not None
        else Sponsor.objects.filter(sponsorships__isnull=True)
    )
    eligible_sponsors = list(
        sponsor_scope.exclude(id__in=existing_sponsor_ids)
        .order_by("name")
        .distinct()
    )

    if len(eligible_sponsors) < 2:
        return {
            "recommendations": [],
            "message": "Not enough sponsors are available to generate recommendations (at least two sponsors not linked to this hackathon are required).",
        }

    # 2. Identifier les sponsors avec historique confirmé sur d'autres éditions (bonus fidélité)
    confirmed_other_editions = set(
        visible_sponsorships.filter(status=StatusChoices.CONFIRME)
        .exclude(hackathon=hackathon)
        .values_list("sponsor_id", flat=True)
    )

    # 3. Préparer les textes pour la vectorisation
    corpus = [hackathon_text] + [get_sponsor_text(sp) for sp in eligible_sponsors]

    vectorizer = TfidfVectorizer(
        stop_words=FRENCH_STOPWORDS + ENGLISH_STOPWORDS,
        ngram_range=(1, 2),
        min_df=1,
        lowercase=True,
    )

    try:
        tfidf_matrix = vectorizer.fit_transform(corpus)
    except Exception:
        return {
            "recommendations": [],
            "message": "An error occurred during TF-IDF text analysis.",
        }

    feature_names = np.array(vectorizer.get_feature_names_out())
    hackathon_dense = tfidf_matrix[0].toarray()[0]
    sponsors_dense = tfidf_matrix[1:].toarray()

    # Calcul des similarités cosinus
    cos_sims = cosine_similarity(tfidf_matrix[0:1], tfidf_matrix[1:])[0]

    results = []
    for idx, sponsor in enumerate(eligible_sponsors):
        raw_sim = float(cos_sims[idx])

        # Bonus de partenariat confirmé antérieur : +10%
        has_history_bonus = sponsor.id in confirmed_other_editions
        bonus = 0.10 if has_history_bonus else 0.0

        final_score = min(raw_sim + bonus, 1.0)
        percentage_score = int(round(final_score * 100))

        # Mots-clés explicatifs
        keywords = extract_top_keywords(
            hackathon_dense,
            sponsors_dense[idx],
            feature_names,
            top_k=3,
        )

        results.append({
            "sponsor": sponsor,
            "score": percentage_score,
            "raw_similarity": round(raw_sim * 100, 1),
            "has_history_bonus": has_history_bonus,
            "keywords": keywords,
        })

    # Trier par score décroissant, puis alphabétique
    results.sort(key=lambda item: (-item["score"], item["sponsor"].name))
    top_recommendations = results[:top_n]

    response_data = {
        "recommendations": top_recommendations,
        "message": "",
        "total_eligible": len(eligible_sponsors),
    }

    if use_cache:
        cache.set(cache_key, response_data, timeout=cache_timeout)

    return response_data
