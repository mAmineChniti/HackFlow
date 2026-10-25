from django.db import transaction

from .models import Team, TeamMember


class TeamError(Exception):
    """Erreur métier affichable à l'utilisateur."""


@transaction.atomic
def create_team(*, leader, name, description, hackathon, max_members):
    if TeamMember.objects.filter(user=leader, team__hackathon=hackathon).exists():
        raise TeamError("Vous faites déjà partie d'une équipe pour ce hackathon.")
    team = Team.objects.create(
        name=name,
        description=description,
        hackathon=hackathon,
        leader=leader,
        max_members=max_members,
    )
    TeamMember.objects.create(team=team, user=leader, role=TeamMember.Role.LEADER)
    return team


@transaction.atomic
def join_team(*, team, user, role, skills=""):
    team = Team.objects.select_for_update().get(pk=team.pk)
    if TeamMember.objects.filter(team=team, user=user).exists():
        raise TeamError("Vous êtes déjà membre de cette équipe.")
    if TeamMember.objects.filter(user=user, team__hackathon=team.hackathon).exists():
        raise TeamError("Vous faites déjà partie d'une équipe pour ce hackathon.")
    if team.is_full:
        raise TeamError("Cette équipe est complète.")
    return TeamMember.objects.create(team=team, user=user, role=role, skills=skills)


@transaction.atomic
def leave_team(*, team, user):
    if team.leader_id == user.pk:
        raise TeamError("Le chef d'équipe ne peut pas quitter l'équipe : supprimez-la.")
    deleted, _ = TeamMember.objects.filter(team=team, user=user).delete()
    if not deleted:
        raise TeamError("Vous n'êtes pas membre de cette équipe.")