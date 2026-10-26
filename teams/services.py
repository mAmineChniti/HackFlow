from django.db import transaction
from django.utils import timezone

from .models import Invitation, SkillProfile, Team, TeamMember


class TeamError(Exception):
    """Erreur métier affichable à l'utilisateur."""


@transaction.atomic
def create_team(*, leader, name, description, hackathon, max_members):
    if TeamMember.objects.filter(user=leader, team__hackathon=hackathon).exists():
        raise TeamError("You are already a member of a team for this hackathon.")
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
        raise TeamError("You are already a member of this team.")
    if TeamMember.objects.filter(user=user, team__hackathon=team.hackathon).exists():
        raise TeamError("You are already a member of a team for this hackathon.")
    if team.is_full:
        raise TeamError("This team is already full.")
    return TeamMember.objects.create(team=team, user=user, role=role, skills=skills)


@transaction.atomic
def leave_team(*, team, user):
    if team.leader_id == user.pk:
        raise TeamError("The team leader cannot leave the team: delete it instead.")
    deleted, _ = TeamMember.objects.filter(team=team, user=user).delete()
    if not deleted:
        raise TeamError("You are not a member of this team.")


# ----------------------------------------------------------- Matching IA
CORE_ROLES = ("backend", "frontend", "designer", "data")
MAX_SCORE = 8  # 5 (rôle manquant) + 3 (compétences nouvelles, plafonnées)


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
        p.user_id: p for p in SkillProfile.objects.filter(user_id__in=[m.user_id for m in members])
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
        candidate_skills = parse_skills(profile.skills)
        score, reasons = score_candidate(
            role=profile.main_role,
            skills=candidate_skills,
            missing_roles=analysis["missing_roles"],
            team_skills=team_skills,
        )
        if score > 0:
            results.append(
                {
                    "user": profile.user,
                    "role": profile.main_role,
                    "score": score,
                    "reasons": reasons,
                    "synergy": round(score / MAX_SCORE * 100),
                    "shared_skills": [s for s in candidate_skills if s in team_skills],
                    "new_skills": [s for s in candidate_skills if s not in team_skills],
                }
            )
    results.sort(key=lambda r: (-r["score"], r["user"].username))
    return analysis, results[:limit]


# ------------------------------------------------------------ Invitations
@transaction.atomic
def invite_user(*, team, invited_by, invitee, message=""):
    team = Team.objects.select_for_update().get(pk=team.pk)
    if team.leader_id != invited_by.pk:
        raise TeamError("Only the team leader can send invitations.")
    if invitee.pk == invited_by.pk:
        raise TeamError("You cannot invite yourself.")
    if team.is_full:
        raise TeamError("The team is already full.")
    if TeamMember.objects.filter(user=invitee, team__hackathon=team.hackathon).exists():
        raise TeamError("This user is already a member of a team for this hackathon.")
    if Invitation.objects.filter(
        team=team, invitee=invitee, status=Invitation.Status.PENDING
    ).exists():
        raise TeamError("An invitation is already pending for this user.")
    return Invitation.objects.create(
        team=team, invitee=invitee, invited_by=invited_by, message=message[:200]
    )


def _lock_invitation(invitation):
    return (
        Invitation.objects.select_for_update(of=("self",))
        .select_related("team")
        .get(pk=invitation.pk)
    )


@transaction.atomic
def accept_invitation(*, invitation, user):
    invitation = _lock_invitation(invitation)
    if invitation.invitee_id != user.pk:
        raise TeamError("This invitation was not sent to you.")
    if invitation.status != Invitation.Status.PENDING:
        raise TeamError("This invitation is no longer pending.")

    profile = SkillProfile.objects.filter(user=user).first()
    role = profile.main_role if profile else TeamMember.Role.OTHER
    skills = profile.skills if profile else ""
    join_team(team=invitation.team, user=user, role=role, skills=skills)

    now = timezone.now()
    invitation.status = Invitation.Status.ACCEPTED
    invitation.responded_at = now
    invitation.save(update_fields=["status", "responded_at"])
    # Ses autres invitations en attente pour ce hackathon n'ont plus de sens.
    Invitation.objects.filter(
        invitee=user,
        status=Invitation.Status.PENDING,
        team__hackathon=invitation.team.hackathon,
    ).exclude(pk=invitation.pk).update(status=Invitation.Status.CANCELLED, responded_at=now)
    return invitation


@transaction.atomic
def decline_invitation(*, invitation, user):
    invitation = _lock_invitation(invitation)
    if invitation.invitee_id != user.pk:
        raise TeamError("This invitation was not sent to you.")
    if invitation.status != Invitation.Status.PENDING:
        raise TeamError("This invitation is no longer pending.")
    invitation.status = Invitation.Status.DECLINED
    invitation.responded_at = timezone.now()
    invitation.save(update_fields=["status", "responded_at"])
    return invitation


@transaction.atomic
def cancel_invitation(*, invitation, user):
    invitation = _lock_invitation(invitation)
    if invitation.team.leader_id != user.pk:
        raise TeamError("Only the team leader can cancel an invitation.")
    if invitation.status != Invitation.Status.PENDING:
        raise TeamError("This invitation is no longer pending.")
    invitation.status = Invitation.Status.CANCELLED
    invitation.responded_at = timezone.now()
    invitation.save(update_fields=["status", "responded_at"])
    return invitation
