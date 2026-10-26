from django.core.exceptions import PermissionDenied

from accounts.models import Profile
from projects.services import get_user_role, is_admin, is_organizer


def is_challenge_organizer(user, challenge=None) -> bool:
    if not user or not user.is_authenticated:
        return False
    if is_admin(user) or is_organizer(user):
        if challenge is None:
            return True
        return challenge.organizer_id == user.id or is_admin(user)
    return False


def can_create_challenge(user) -> bool:
    return is_admin(user) or is_organizer(user)


def can_edit_challenge(user, challenge) -> bool:
    return is_admin(user) or (is_organizer(user) and challenge.organizer_id == user.id)


def can_delete_challenge(user, challenge) -> bool:
    return is_admin(user) or (is_organizer(user) and challenge.organizer_id == user.id)


def can_view_challenge(user, challenge) -> bool:
    if challenge.status == "active":
        return True
    return is_challenge_organizer(user, challenge)


def can_submit_challenge(user, challenge) -> bool:
    if not user or not user.is_authenticated:
        return False
    role = get_user_role(user)
    if role in (Profile.Role.STUDENT, Profile.Role.ADMIN, Profile.Role.ORGANIZER):
        return challenge.status == "active"
    return False


def validate_submit_permission(user, challenge):
    if not user or not user.is_authenticated:
        raise PermissionDenied("Authentication required.")
    if not can_submit_challenge(user, challenge):
        raise PermissionDenied("You cannot submit a solution to this challenge.")
