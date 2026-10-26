"""Role-based permission helpers for the sponsors app."""

from django.conf import settings
from django.db.models import Q, QuerySet

SPONSOR_PERMISSIONS = {
    "manage",
    "view_confidential",
    "contact",
    "export",
    "delete",
}

ROLE_PERMISSIONS = {
    "admin": SPONSOR_PERMISSIONS.copy(),
    "organizer": {"manage", "view_confidential", "contact", "export"},
    "student": set(),
    "judge": set(),
    "mentor": set(),
    "visitor": set(),
}


def _role_permissions():
    configured = getattr(settings, "SPONSORS_ROLE_PERMISSIONS", None)
    if configured is None:
        return ROLE_PERMISSIONS
    return {**ROLE_PERMISSIONS, **configured}


def get_user_roles(user) -> set[str]:
    """Return the user's roles; integrate future role sources here."""
    if not getattr(user, "is_authenticated", False):
        return {"visitor"}

    if getattr(user, "is_superuser", False):
        return {"admin"}

    # Use profile role if available
    profile = getattr(user, "profile", None)
    profile_role = getattr(profile, "role", None)
    if profile_role:
        normalized_role = str(profile_role).strip().lower()
        if normalized_role in ROLE_PERMISSIONS:
            return {normalized_role}

    # Enable SPONSORS_USE_GROUP_ROLES when Django groups become the role source.
    if getattr(settings, "SPONSORS_USE_GROUP_ROLES", False):
        group_roles = set(user.groups.values_list("name", flat=True))
        normalized_roles = {
            normalized
            for role in group_roles
            if role
            for normalized in (str(role).strip().lower(),)
            if normalized
        }
        if normalized_roles:
            return normalized_roles

    if getattr(user, "is_staff", False):
        return {"organizer"}
    return {"student"}


def user_has_sponsor_permission(user, perm: str) -> bool:
    if perm not in SPONSOR_PERMISSIONS:
        return False

    role_permissions = _role_permissions()
    return any(perm in role_permissions.get(role, ()) for role in get_user_roles(user))


def can_manage_sponsors(user) -> bool:
    return user_has_sponsor_permission(user, "manage")


def can_view_confidential(user) -> bool:
    return user_has_sponsor_permission(user, "view_confidential")


def can_contact_sponsors(user) -> bool:
    return user_has_sponsor_permission(user, "contact")


def can_export(user) -> bool:
    return user_has_sponsor_permission(user, "export")


def can_delete(user) -> bool:
    return user_has_sponsor_permission(user, "delete")


def sponsorships_visible_to(user) -> QuerySet:
    """Return sponsorship records visible to the user."""
    from sponsors.models import Sponsorship

    if can_view_confidential(user):
        # Add organizer/owner filtering here when the project defines ownership.
        return Sponsorship.objects.all()
    return Sponsorship.objects.none()


def sponsors_visible_to(user) -> QuerySet:
    from sponsors.models import Sponsor

    if not can_view_confidential(user):
        return Sponsor.objects.none()

    visible_sponsorships = sponsorships_visible_to(user)
    return Sponsor.objects.filter(
        Q(sponsorships__in=visible_sponsorships) | Q(sponsorships__isnull=True)
    ).distinct()


def can_manage_sponsorship(user, sponsorship) -> bool:
    if not can_manage_sponsors(user):
        return False
    if sponsorship is None or not getattr(sponsorship, "pk", None):
        return False
    # Add organizer ownership filtering here when the project defines ownership.
    return sponsorships_visible_to(user).filter(pk=sponsorship.pk).exists()
