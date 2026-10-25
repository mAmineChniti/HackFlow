from django.db import transaction

from .models import SkillProfile, Team, TeamMember


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


# ----------------------------------------------------------- Matching IA
CORE_ROLES = ("backend", "frontend", "designer", "data")


def parse_skills(text):
    """'Python, Django ,python' -> ['python', 'django']"""
    skills = []
    for raw in (text or "").split(","):
        skill = raw.strip().lower()
        if skill and skill not in skills:
            skills.append(skill)
    return skills


def score_candidate(*, role, skills, missing_roles, team_skills):
    """Fonction pure : facile à tester et à évaluer sans base de données."""
    score = 0
    reasons = []
    if role in missing_roles:
        score += 5
        reasons.append(f"comble le rôle manquant : {role}")
    new_skills = [s for s in skills if s not in team_skills]
    if new_skills:
        score += min(len(new_skills), 3)
        reasons.append("apporte : " + ", ".join(new_skills[:3]))
    return score, reasons


def analyze_team(team):
    members = list(team.members.select_related("user"))
    profiles = {
        p.user_id: p
        for p in SkillProfile.objects.filter(user_id__in=[m.user_id for m in members])
    }
    roles, skills = set(), set()
    for member in members:
        profile = profiles.get(member.user_id)
        role = member.role
        if role == TeamMember.Role.LEADER:
            role = profile.main_role if profile else None
        if role:
            roles.add(role)
        skills.update(parse_skills(member.skills))
        if profile:
            skills.update(parse_skills(profile.skills))
    return {
        "roles": sorted(roles),
        "skills": sorted(skills),
        "missing_roles": [r for r in CORE_ROLES if r not in roles],
    }


def suggest_candidates(team, limit=3):
    analysis = analyze_team(team)
    team_skills = set(analysis["skills"])
    candidates = (
        SkillProfile.objects.filter(looking_for_team=True)
        .exclude(user__team_memberships__team__hackathon=team.hackathon)
        .select_related("user")
    )
    results = []
    for profile in candidates:
        score, reasons = score_candidate(
            role=profile.main_role,
            skills=parse_skills(profile.skills),
            missing_roles=analysis["missing_roles"],
            team_skills=team_skills,
        )
        if score > 0:
            results.append(
                {"user": profile.user, "role": profile.main_role, "score": score, "reasons": reasons}
            )
    results.sort(key=lambda r: (-r["score"], r["user"].username))
    return analysis, results[:limit]