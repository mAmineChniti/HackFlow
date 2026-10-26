"""
Permission service layer for HackFlow.
Centralizes all access rules and authorization logic based on global role
and project team role.
"""

from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.utils import timezone
from accounts.models import Profile
from .models import HistoriqueProjet, Project, ProjectMember


def get_user_role(user) -> str:
    """
    Returns the effective role of a user.
    A superuser is always treated as 'admin'.
    """
    if not user or not user.is_authenticated:
        return "anonymous"
    if getattr(user, "is_superuser", False):
        return Profile.Role.ADMIN
    profile = getattr(user, "profile", None)
    if profile and profile.role:
        return profile.role
    return Profile.Role.STUDENT


def is_admin(user) -> bool:
    """Check if user has Admin role (or is superuser)."""
    return get_user_role(user) == Profile.Role.ADMIN


def is_organizer(user) -> bool:
    """Check if user is Organizer (or Admin)."""
    role = get_user_role(user)
    return role in (Profile.Role.ORGANIZER, Profile.Role.ADMIN)


def is_judge(user) -> bool:
    """Check if user is Judge."""
    return get_user_role(user) == Profile.Role.JUDGE


def is_mentor(user) -> bool:
    """Check if user is Mentor."""
    return get_user_role(user) == Profile.Role.MENTOR


def is_student(user) -> bool:
    """Check if user is Student."""
    return get_user_role(user) == Profile.Role.STUDENT


def get_team_membership(user, project):
    """Returns the ProjectMember membership for a user on a given project."""
    if not user or not user.is_authenticated or not project:
        return None
    return ProjectMember.objects.filter(project=project, user=user).first()


def is_team_member(user, project) -> bool:
    """Check if user is a member of the project team (or its creator)."""
    if not user or not user.is_authenticated or not project:
        return False
    if project.created_by_id == user.id:
        return True
    return ProjectMember.objects.filter(project=project, user=user).exists()


def is_project_lead(user, project) -> bool:
    """Check if the user is the Project Lead (creator or role chef_de_projet)."""
    if not user or not user.is_authenticated or not project:
        return False
    if project.created_by_id == user.id:
        return True
    membership = get_team_membership(user, project)
    return membership is not None and membership.role == ProjectMember.Role.CHEF_DE_PROJET


# ==============================================================================
# PERMISSION RULES BY ACTION
# ==============================================================================


def can_create_project(user) -> bool:
    """
    Students can create a project. Admins can too.
    """
    if not user or not user.is_authenticated:
        return False
    return is_student(user) or is_admin(user)


def can_view_project(user, project) -> bool:
    """
    Project view permissions:
    - Admin: sees everything.
    - Organizer: sees all projects (including drafts).
    - Judge: sees only accepted projects (status=accepted).
    - Mentor: sees projects they mentor (or accepted projects).
    - Student: sees their own project (even draft) or accepted projects of others.
    - Anonymous: sees only accepted projects.
    """
    if not project:
        return False

    # Accepted projects visible to everyone
    if project.status == Project.Status.ACCEPTED:
        return True

    if not user or not user.is_authenticated:
        return False

    role = get_user_role(user)
    if role in (Profile.Role.ADMIN, Profile.Role.ORGANIZER):
        return True

    if role == Profile.Role.JUDGE:
        # Judge sees ONLY accepted projects
        return project.status == Project.Status.ACCEPTED

    if role == Profile.Role.MENTOR:
        # Mentor sees projects they mentor or accepted projects
        return is_team_member(user, project) or project.status == Project.Status.ACCEPTED

    # Student: sees their team's projects
    return is_team_member(user, project)


def can_edit_project(user, project) -> bool:
    """
    Project editing permission:
    - Only project team members can edit their project when status is 'draft' or 'rejected', before deadline.
    - Organizers and admins CANNOT edit unless they are team members.
    - Projects in status 'submitted', 'under_review', 'accepted', 'finalist', 'winner' are locked.
    """
    if not user or not user.is_authenticated or not project:
        return False

    # Only project team members can edit (organizers and admins cannot edit unless they are members)
    if not is_team_member(user, project):
        return False

    # Draft or Rejected only
    if project.status not in (Project.Status.DRAFT, Project.Status.REJECTED):
        return False

    # Before deadline
    if project.deadline and timezone.now() > project.deadline:
        return False

    return True


def validate_edit_permission(user, project):
    """
    Server-side verification for editing a project.
    Raises PermissionDenied (HTTP 403) if unauthorized or locked.
    """
    if not user or not user.is_authenticated:
        raise PermissionDenied("Authentication required.")

    if not project:
        raise PermissionDenied("Project not found.")

    if not is_team_member(user, project):
        raise PermissionDenied("Only project team members can edit this project.")

    if project.status not in (Project.Status.DRAFT, Project.Status.REJECTED):
        raise PermissionDenied(
            f"This project is locked in its current status ({project.get_status_display()}) and cannot be edited."
        )

    if project.deadline and timezone.now() > project.deadline:
        raise PermissionDenied("The submission deadline has passed.")


def can_submit_project(user, project) -> bool:
    """
    Project submission permission:
    - Only project team members can submit (or resubmit) their project.
    - Status must be 'draft' or 'rejected', before deadline.
    - Organizers and admins CANNOT submit unless they are team members.
    """
    if not user or not user.is_authenticated or not project:
        return False

    # Only project team members can submit
    if not is_team_member(user, project):
        return False

    # Draft or Rejected only
    if project.status not in (Project.Status.DRAFT, Project.Status.REJECTED):
        return False

    if project.deadline and timezone.now() > project.deadline:
        return False

    return True


def validate_submit_permission(user, project):
    """
    Server-side verification for submitting or resubmitting a project.
    Raises PermissionDenied (HTTP 403) if unauthorized or locked.
    """
    if not user or not user.is_authenticated:
        raise PermissionDenied("Authentication required.")

    if not project:
        raise PermissionDenied("Project not found.")

    if not is_team_member(user, project):
        raise PermissionDenied("Only project team members can submit this project.")

    if project.status not in (Project.Status.DRAFT, Project.Status.REJECTED):
        raise PermissionDenied(
            f"This project cannot be submitted in its current status ({project.get_status_display()})."
        )

    if project.deadline and timezone.now() > project.deadline:
        raise PermissionDenied("The submission deadline has passed.")


TEAM_MANAGEABLE_STATUSES = {
    Project.Status.DRAFT,
    Project.Status.REJECTED,
}


def can_manage_members(user, project) -> bool:
    """
    Team management permission (adding and removing members):
    - Authorized ONLY for the project lead who is a team member.
    - Organizers and admins CANNOT manage members unless they are project lead.
    - Status condition: ONLY when project status is 'draft' or 'rejected'.
    - Locked for 'submitted', 'under_review', 'accepted', 'finalist', 'winner'.
    """
    if not user or not user.is_authenticated or not project:
        return False

    # Status locking
    if project.status not in TEAM_MANAGEABLE_STATUSES:
        return False

    if not is_team_member(user, project):
        return False

    return is_project_lead(user, project)


def validate_manage_members_permission(user, project):
    """
    Server-side verification for managing team members.
    Raises PermissionDenied (HTTP 403) if unauthorized or locked.
    """
    if not user or not user.is_authenticated:
        raise PermissionDenied("Authentication required.")

    if not project:
        raise PermissionDenied("Project not found.")

    if not is_team_member(user, project):
        raise PermissionDenied("Only project team members can manage the team.")

    if project.status not in TEAM_MANAGEABLE_STATUSES:
        raise PermissionDenied(
            f"Team management is locked for a project with status '{project.get_status_display()}'."
        )

    if not is_project_lead(user, project):
        raise PermissionDenied("Only the project lead can manage team members.")


PROJECT_DELETABLE_STATUSES = {
    Project.Status.DRAFT,
    Project.Status.REJECTED,
}


def can_delete_project(user, project) -> bool:
    """
    Project deletion permission:
    - Authorized ONLY for the project lead who is a team member.
    - Organizers and admins CANNOT delete unless they are project lead.
    - Status condition: ONLY when project status is 'draft' or 'rejected'.
    - Locked for 'submitted', 'under_review', 'accepted', 'finalist', 'winner'.
    """
    if not user or not user.is_authenticated or not project:
        return False

    # Status locking
    if project.status not in PROJECT_DELETABLE_STATUSES:
        return False

    if not is_team_member(user, project):
        return False

    return is_project_lead(user, project)


def validate_delete_permission(user, project):
    """
    Server-side verification for deleting a project.
    Raises PermissionDenied (HTTP 403) if unauthorized or locked.
    """
    if not user or not user.is_authenticated:
        raise PermissionDenied("Authentication required.")

    if not project:
        raise PermissionDenied("Project not found.")

    if not is_team_member(user, project):
        raise PermissionDenied("Only project team members can delete this project.")

    if project.status not in PROJECT_DELETABLE_STATUSES:
        raise PermissionDenied(
            f"Project deletion is locked for a project with status '{project.get_status_display()}'."
        )

    if not can_delete_project(user, project):
        raise PermissionDenied("Only the project lead can delete this project.")


REVIEWABLE_STATUSES = {
    Project.Status.SUBMITTED,
    Project.Status.UNDER_REVIEW,
}


def can_review_project(user, project) -> bool:
    """
    Organizers and Admins can accept or reject a project.
    Strict rule:
    - Review action (accept/reject) is allowed ONLY for projects
      with status 'submitted' or 'under_review'.
    - Never for projects in 'draft' status, nor for already accepted/rejected projects.
    """
    if not user or not user.is_authenticated or not project:
        return False
    if not is_organizer(user):
        return False
    return project.status in REVIEWABLE_STATUSES


def validate_review_permission(user, project):
    """
    Server-side check if the project can be reviewed by the user.
    Raises PermissionDenied (HTTP 403) if user is not authorized
    or if the project is in draft status or not reviewable.
    """
    if not user or not user.is_authenticated:
        raise PermissionDenied("Authentication required.")

    if not is_organizer(user):
        raise PermissionDenied("Action reserved for organizers and administrators.")

    if not project or project.status not in REVIEWABLE_STATUSES:
        if project and project.status == Project.Status.DRAFT:
            raise PermissionDenied("Cannot evaluate a project in draft status.")
        raise PermissionDenied("This project cannot be evaluated in its current status.")


def can_comment_as_mentor(user, project) -> bool:
    """
    Mentor: can leave advisory comments on mentored projects.
    """
    if not user or not user.is_authenticated or not project:
        return False
    return is_mentor(user) and is_team_member(user, project)


# Statuses whose assignment is restricted to Organizers and Administrators
ORGANIZER_ADMIN_STATUSES = {
    Project.Status.UNDER_REVIEW,
    Project.Status.ACCEPTED,
    Project.Status.REJECTED,
    Project.Status.FINALIST,
    Project.Status.WINNER,
}


def can_set_status(user, target_status: str) -> bool:
    """
    Checks if a user has permission to set a specific project status.
    - Only Organizer and Admin can assign:
      'under_review', 'accepted', 'rejected', 'finalist', 'winner'.
    - Transition to 'submitted' is done exclusively via 'Submit project'.
    - Students cannot set these statuses via form (only 'draft' is valid).
    """
    if not user or not user.is_authenticated:
        return False

    if is_admin(user) or is_organizer(user):
        return target_status in Project.Status.values

    # For students or any non-admin/organizer user:
    # Only 'draft' is allowed in create/update payloads
    if target_status == Project.Status.DRAFT:
        return True

    return False


def validate_status_permission(user, target_status: str):
    """
    Validates requested status on server-side.
    Raises PermissionDenied (HTTP 403) if unauthorized.
    """
    if target_status and not can_set_status(user, target_status):
        raise PermissionDenied("You do not have permission to set this status.")


def can_run_ai_evaluation(user, project) -> bool:
    """
    Checks if a user has permission to run AI evaluation on a project:
    - Hidden and forbidden for 'judge' and 'mentor' roles.
    - Allowed for student members of the project team.
    - Allowed for organizers and administrators.
    """
    if not user or not user.is_authenticated or not project:
        return False

    role = get_user_role(user)
    if role in (Profile.Role.JUDGE, Profile.Role.MENTOR):
        return False

    if is_organizer(user):
        return True

    if role == Profile.Role.STUDENT and is_team_member(user, project):
        return True

    return False


def validate_ai_evaluation_permission(user, project):
    """
    Validates AI evaluation permission on server-side.
    Raises PermissionDenied (HTTP 403) if unauthorized.
    """
    if not user or not user.is_authenticated:
        raise PermissionDenied("Authentication required.")

    if not can_run_ai_evaluation(user, project):
        role = get_user_role(user)
        if role in (Profile.Role.JUDGE, Profile.Role.MENTOR):
            raise PermissionDenied("AI evaluation is not permitted for judges and mentors.")
        raise PermissionDenied("You do not have permission to evaluate this project with AI.")


def can_view_mentor_advice(user, project) -> bool:
    """
    The 'Mentor Advice' section is visible only for:
    - Mentor role (can post advice)
    - Team members of the project (can read advice)
    - Administrators (superusers)
    """
    if not user or not user.is_authenticated or not project:
        return False
    if is_mentor(user):
        return True
    if is_team_member(user, project):
        return True
    if is_admin(user):
        return True
    return False


def can_add_mentor_advice(user, project) -> bool:
    """
    Only mentors are authorized to draft and submit mentor advice.
    """
    if not user or not user.is_authenticated or not project:
        return False
    return is_mentor(user)


def validate_add_mentor_advice_permission(user, project):
    """
    Server-side validation for mentor advice submission.
    Raises PermissionDenied (HTTP 403) if user does not have mentor role.
    """
    if not user or not user.is_authenticated:
        raise PermissionDenied("Authentication required.")

    if not can_add_mentor_advice(user, project):
        raise PermissionDenied("Only mentors can submit advice.")


def score_project(project, user, score) -> None:
    """Set an organizer score (1-10) with audit history."""
    if not is_organizer(user):
        raise PermissionDenied("Only organizers and admins can score projects.")
    if project.status not in (Project.Status.ACCEPTED, Project.Status.FINALIST, Project.Status.WINNER, Project.Status.UNDER_REVIEW):
        raise PermissionDenied("Project must be reviewed before scoring.")
    now = timezone.now()
    with transaction.atomic():
        project.score = score
        project.save(update_fields=["score", "updated_at"])
        create_history_entry(project, HistoriqueProjet.Action.UNDER_REVIEW, user, commentaire=f"Score set to {score}/10", date=now)
# ─────────────────────────────────────────────────────────────────────────────


def create_history_entry(
    project, action: str, actor, commentaire: str = "", date=None
) -> HistoriqueProjet:
    """
    Creates and persists a single HistoriqueProjet row.
    Uses the provided real event date, or timezone.now() at execution time.
    Should always be called inside a transaction.atomic() block so the
    project state change and the audit row are committed together.
    """
    event_date = date or timezone.now()
    return HistoriqueProjet.objects.create(
        project=project,
        action=action,
        acteur=actor,
        commentaire=commentaire,
        date=event_date,
    )


# ─────────────────────────────────────────────────────────────────────────────
# High-level project actions (status change + history in one transaction)
# ─────────────────────────────────────────────────────────────────────────────


def submit_project(project, user) -> None:
    """
    Transitions a project from DRAFT or REJECTED to SUBMITTED.
    Validates permissions, then atomically:
      - updates the project status and submitted_at timestamp
      - appends a JSON entry to review_history (backward compat)
      - creates a HistoriqueProjet row with the submission timestamp
    Raises PermissionDenied when the caller is not authorised.
    """
    validate_submit_permission(user, project)

    is_resubmission = project.status == Project.Status.REJECTED
    action = (
        HistoriqueProjet.Action.RESUBMITTED
        if is_resubmission
        else HistoriqueProjet.Action.SUBMITTED
    )
    now = timezone.now()

    with transaction.atomic():
        project.status = Project.Status.SUBMITTED
        project.submitted_at = now

        if not isinstance(project.review_history, list):
            project.review_history = []

        if is_resubmission:
            project.review_history.append(
                {
                    "type": "resubmission",
                    "action": "Project resubmitted",
                    "user": user.get_username(),
                    "date": now.isoformat(),
                    "date_display": now.strftime("%b %d, %Y at %H:%M"),
                    "reviewed_at": now.isoformat(),
                    "reviewed_at_display": now.strftime("%b %d, %Y at %H:%M"),
                }
            )
        else:
            project.review_history.append(
                {
                    "type": "submission",
                    "action": "First project submission",
                    "user": user.get_username(),
                    "date": now.isoformat(),
                    "date_display": now.strftime("%b %d, %Y at %H:%M"),
                    "reviewed_at": now.isoformat(),
                    "reviewed_at_display": now.strftime("%b %d, %Y at %H:%M"),
                }
            )

        project.save(update_fields=["status", "submitted_at", "review_history", "updated_at"])
        create_history_entry(project, action, user, date=now)


def review_project(project, user, decision: str, reason: str = "") -> None:
    """
    Accepts or rejects a project (decision = 'accept' | 'reject').
    Validates permissions, then atomically:
      - calls project.accept() or project.reject() (which update JSON history and reviewed_at)
      - creates a HistoriqueProjet row with the decision timestamp
    Raises PermissionDenied when the caller is not authorised.
    Raises ValueError when decision is 'reject' but no reason is provided.
    """
    validate_review_permission(user, project)

    if decision == "reject" and not reason.strip():
        raise ValueError("A rejection reason is required.")

    with transaction.atomic():
        if decision == "accept":
            project.accept(user)
            decision_date = project.reviewed_at or timezone.now()
            create_history_entry(
                project, HistoriqueProjet.Action.ACCEPTED, user, date=decision_date
            )
        elif decision == "reject":
            project.reject(user, reason)
            decision_date = project.reviewed_at or timezone.now()
            create_history_entry(
                project,
                HistoriqueProjet.Action.REJECTED,
                user,
                commentaire=reason,
                date=decision_date,
            )
        else:
            raise ValueError(f"Unknown decision: {decision!r}")


def change_project_status(project, user, new_status: str) -> None:
    """
    Generic status change by an organizer/admin (under_review, finalist, winner).
    Atomically saves the new status and writes a HistoriqueProjet row.
    Raises PermissionDenied if the caller is not an organizer/admin.
    """
    if not is_organizer(user):
        raise PermissionDenied("Only organizers and admins can change project status.")

    STATUS_TO_ACTION = {
        Project.Status.UNDER_REVIEW: HistoriqueProjet.Action.UNDER_REVIEW,
        Project.Status.FINALIST: HistoriqueProjet.Action.FINALIST,
        Project.Status.WINNER: HistoriqueProjet.Action.WINNER,
    }
    action = STATUS_TO_ACTION.get(new_status)
    if action is None:
        raise ValueError(f"Use submit_project() or review_project() for status '{new_status}'.")

    # Allowed source statuses for each target (enforces lifecycle order).
    ALLOWED_SOURCES = {
        Project.Status.UNDER_REVIEW: {Project.Status.SUBMITTED, Project.Status.UNDER_REVIEW},
        Project.Status.FINALIST: {Project.Status.ACCEPTED, Project.Status.UNDER_REVIEW},
        Project.Status.WINNER: {Project.Status.FINALIST, Project.Status.ACCEPTED},
    }
    if new_status in ALLOWED_SOURCES and project.status not in ALLOWED_SOURCES[new_status]:
        raise PermissionDenied(
            f"Cannot move a project from '{project.get_status_display()}' to "
            f"'{dict(Project.Status.choices).get(new_status, new_status)}'."
        )

    now = timezone.now()
    with transaction.atomic():
        project.status = new_status
        project.save(update_fields=["status", "updated_at"])
        create_history_entry(project, action, user, date=now)
