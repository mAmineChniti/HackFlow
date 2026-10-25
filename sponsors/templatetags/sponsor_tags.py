"""
Template tags pour le module Gestion des Sponsors.
"""

from django import template
from sponsors.models import Sponsorship, StatusChoices
from sponsors.permissions import (
    can_contact_sponsors,
    can_delete,
    can_export,
    can_manage_sponsors,
    can_view_confidential,
    sponsorships_visible_to,
    user_has_sponsor_permission,
)

register = template.Library()


@register.simple_tag
def get_confirmed_sponsors(limit=6, user=None):
    """
    Retourne jusqu'à 'limit' sponsorships confirmés dédoublonnés par sponsor.
    Un sponsor confirmé sur plusieurs hackathons n'apparaît qu'une seule fois.
    Utilise select_related('sponsor') pour éviter les requêtes N+1.
    """
    visible_sponsorships = sponsorships_visible_to(user)
    # The home page only displays confirmed public information, even when the
    # visitor cannot access confidential sponsor records.
    confirmed_qs = (
        (visible_sponsorships | Sponsorship.objects.filter(status=StatusChoices.CONFIRME))
        .filter(status=StatusChoices.CONFIRME)
        .select_related("sponsor")
        .order_by("-tier", "sponsor__name")
    )

    seen_sponsor_ids = set()
    deduped = []
    for sp in confirmed_qs:
        if sp.sponsor_id not in seen_sponsor_ids:
            seen_sponsor_ids.add(sp.sponsor_id)
            deduped.append(sp)
            if len(deduped) >= limit:
                break

    return deduped


@register.simple_tag
def has_sponsor_permission(user, permission):
    return user_has_sponsor_permission(user, permission)


@register.simple_tag(name="can_manage_sponsors")
def can_manage_sponsors_tag(user):
    return can_manage_sponsors(user)


@register.simple_tag(name="can_view_confidential")
def can_view_confidential_tag(user):
    return can_view_confidential(user)


@register.simple_tag(name="can_contact_sponsors")
def can_contact_sponsors_tag(user):
    return can_contact_sponsors(user)


@register.simple_tag(name="can_export")
def can_export_tag(user):
    return can_export(user)


@register.simple_tag(name="can_delete")
def can_delete_tag(user):
    return can_delete(user)


@register.simple_tag(name="can_manage_sponsorship")
def can_manage_sponsorship_tag(user, sponsorship):
    from sponsors.permissions import can_manage_sponsorship

    return can_manage_sponsorship(user, sponsorship)
