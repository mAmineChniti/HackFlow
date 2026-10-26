import csv
import logging

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.cache import cache
from django.core.exceptions import PermissionDenied
from django.db.models import Count, Q
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from . import ai_service, services, tasks
from .forms import (
    ConseilMentorForm,
    ProjectForm,
    ProjectMemberForm,
    ProjectReviewDecisionForm,
    ProjectScoreForm,
)
from .models import ConseilMentor, Project, ProjectMember

logger = logging.getLogger(__name__)

AI_RATE_LIMIT_MESSAGE = "Too many AI requests. Please wait a moment before trying again."


def _ai_rate_limited(user) -> bool:
    """Fixed-window throttle for the AI endpoints.

    The AI calls cost real money per request, so they need a per-user limit,
    not just an authentication check. Uses the configured cache, so a shared
    cache (e.g. Redis) is required to enforce this across workers.
    """
    limit = getattr(settings, "AI_RATE_LIMIT_MAX", 0)
    if not user or not user.is_authenticated or limit <= 0:
        return False

    window = getattr(settings, "AI_RATE_LIMIT_WINDOW", 60)
    key = f"ai-requests:{user.pk}"
    cache.add(key, 0, window)
    try:
        count = cache.incr(key)
    except ValueError:
        # Key expired between add() and incr(); restart the window.
        cache.set(key, 1, window)
        count = 1
    return count > limit


def _csv_safe(value) -> str:
    """Neutralise spreadsheet formula injection in exported cell values."""
    if value is None:
        return ""
    text = str(value)
    if text and text[0] in ("=", "+", "-", "@", "\t", "\r"):
        return "'" + text
    return text


def project_list(request):
    """
    Liste des projets selon le rôle et les filtres :
    - Organizer / Admin : voient tous les projets.
    - Judge : uniquement les projets validés (status=accepted).
    - Mentor : projets qu'il accompagne + projets validés.
    - Student : projets de son équipe + projets validés.
    - Anonyme : projets validés uniquement.
    """
    query = request.GET.get("q", "").strip()
    category = request.GET.get("category", "").strip()

    user = request.user
    role = services.get_user_role(user)

    projects = Project.objects.select_related("created_by", "reviewed_by").prefetch_related(
        "members"
    )

    # Filtrage de visibilité selon les permissions
    if role in ("admin", "organizer"):
        pass  # Voit tous les projets
    elif role == "judge":
        projects = projects.filter(status=Project.Status.ACCEPTED)
    elif role == "mentor":
        projects = projects.filter(
            Q(status=Project.Status.ACCEPTED) | Q(members=user) | Q(created_by=user)
        ).distinct()
    elif user.is_authenticated:
        projects = projects.filter(
            Q(status=Project.Status.ACCEPTED) | Q(members=user) | Q(created_by=user)
        ).distinct()
    else:
        projects = projects.filter(status=Project.Status.ACCEPTED)

    # Recherche
    if query:
        projects = projects.filter(
            Q(title__icontains=query)
            | Q(tagline__icontains=query)
            | Q(description__icontains=query)
        )

    if category and category in Project.Category.values:
        projects = projects.filter(category=category)

    context = {
        "projects": projects,
        "query": query,
        "selected_category": category,
        "categories": Project.Category.choices,
        "user_role": role,
        "can_create": services.can_create_project(user),
    }
    return render(request, "projects/project_list.html", context)


def project_detail(request, slug):
    """Détail d'un projet avec permissions granulaires calculées par services.py."""
    project = get_object_or_404(
        Project.objects.select_related("created_by", "reviewed_by").prefetch_related(
            "team_memberships__user"
        ),
        slug=slug,
    )

    user = request.user
    if not services.can_view_project(user, project):
        raise PermissionDenied("You do not have permission to view this project.")

    memberships = project.team_memberships.select_related("user")

    can_edit = services.can_edit_project(user, project)
    can_submit = services.can_submit_project(user, project)
    can_manage_members = services.can_manage_members(user, project)
    can_delete = services.can_delete_project(user, project)
    can_review = services.can_review_project(user, project)
    can_comment_mentor = services.can_comment_as_mentor(user, project)
    can_run_ai = services.can_run_ai_evaluation(user, project)
    can_view_mentor_advice = services.can_view_mentor_advice(user, project)
    can_add_mentor_advice = services.can_add_mentor_advice(user, project)

    member_form = ProjectMemberForm(project=project) if can_manage_members else None
    review_form = ProjectReviewDecisionForm() if can_review else None
    mentor_advices = (
        project.conseils_mentor.select_related("mentor").all() if can_view_mentor_advice else []
    )
    mentor_advice_form = ConseilMentorForm() if can_add_mentor_advice else None

    history = project.historique.select_related("acteur").order_by("date")

    context = {
        "project": project,
        "memberships": memberships,
        "user_role": services.get_user_role(user),
        "can_edit": can_edit,
        "can_submit": can_submit,
        "can_manage_members": can_manage_members,
        "can_delete": can_delete,
        "can_review": can_review,
        "can_comment_mentor": can_comment_mentor,
        "can_run_ai": can_run_ai,
        "can_view_mentor_advice": can_view_mentor_advice,
        "can_add_mentor_advice": can_add_mentor_advice,
        "mentor_advices": mentor_advices,
        "mentor_advice_form": mentor_advice_form,
        "is_lead": services.is_project_lead(user, project),
        "member_form": member_form,
        "review_form": review_form,
        "history": history,
    }
    return render(request, "projects/project_detail.html", context)


@login_required
def project_create(request):
    """Création d'un projet par un étudiant (ou admin)."""
    if not services.can_create_project(request.user):
        raise PermissionDenied("Only students can create and submit a project.")

    if request.method == "POST":
        # Vérification côté serveur : interdire à un étudiant d'envoyer un statut interdit
        if "status" in request.POST:
            services.validate_status_permission(request.user, request.POST.get("status"))

        form = ProjectForm(request.POST, user=request.user)
        if form.is_valid():
            project = form.save(commit=False)
            project.created_by = request.user
            project.status = Project.Status.DRAFT
            project.save()

            # Créateur devient automatiquement chef_de_projet
            ProjectMember.objects.create(
                project=project,
                user=request.user,
                role=ProjectMember.Role.CHEF_DE_PROJET,
                is_accepted=True,
            )

            messages.success(request, f"Project “{project.title}” was created successfully.")
            return redirect(project.get_absolute_url())
    else:
        form = ProjectForm(user=request.user)

    return render(request, "projects/project_form.html", {"form": form, "action": "Create"})


@login_required
def project_update(request, slug):
    """Modification d'un projet existant (étudiant de l'équipe, brouillon ou refusé, avant deadline)."""
    project = get_object_or_404(Project, slug=slug)

    services.validate_edit_permission(request.user, project)

    if request.method == "POST":
        # Vérification côté serveur : interdire à un étudiant d'envoyer un statut interdit
        if "status" in request.POST:
            services.validate_status_permission(request.user, request.POST.get("status"))

        form = ProjectForm(request.POST, instance=project, user=request.user)
        if form.is_valid():
            updated_project = form.save(commit=False)
            if not (services.is_organizer(request.user) or services.is_admin(request.user)):
                # Préserver le statut en cours (draft reste draft, rejected reste rejected tant qu'il n'est pas resoumis)
                updated_project.status = project.status
            updated_project.save()
            form.save_m2m()
            messages.success(request, "Project updated.")
            return redirect(project.get_absolute_url())
    else:
        form = ProjectForm(instance=project, user=request.user)

    return render(
        request,
        "projects/project_form.html",
        {"form": form, "project": project, "action": "Edit"},
    )


@login_required
def project_submit(request, slug):
    """Submit or resubmit a project for evaluation."""
    project = get_object_or_404(Project, slug=slug)

    if request.method == "POST":
        is_resubmission = project.status == Project.Status.REJECTED
        services.submit_project(project, request.user)  # validates + atomic save + history
        if is_resubmission:
            messages.success(
                request,
                f"Your project \u00ab {project.title} \u00bb has been resubmitted for review!",
            )
        else:
            messages.success(
                request,
                f"Your project \u00ab {project.title} \u00bb has been submitted for evaluation!",
            )

    return redirect(project.get_absolute_url())


@login_required
def project_delete(request, slug):
    """Suppression d'un projet réservée au chef de projet quand le projet est en brouillon ou refusé.
    Renvoie 403 côté serveur si le projet est soumis, en cours d'évaluation, accepté, finaliste ou lauréat.
    """
    project = get_object_or_404(Project, slug=slug)

    # Vérification stricte côté serveur : statut + rôle chef de projet
    services.validate_delete_permission(request.user, project)

    if request.method == "POST":
        title = project.title
        project.delete()
        messages.success(request, f"Project “{title}” was deleted.")
        return redirect("projects:project_list")

    return render(request, "projects/project_confirm_delete.html", {"project": project})


@login_required
def member_add(request, slug):
    """Ajouter un membre à l'équipe du projet (réservé au chef de projet sur projet brouillon ou refusé)."""
    project = get_object_or_404(Project, slug=slug)
    services.validate_manage_members_permission(request.user, project)

    if request.method == "POST":
        form = ProjectMemberForm(request.POST, project=project)
        if form.is_valid():
            member = form.save(commit=False)
            member.project = project
            if ProjectMember.objects.filter(project=project, user=member.user).exists():
                messages.warning(
                    request, f"{member.user.get_username()} is already a member of this team."
                )
            else:
                member.save()
                messages.success(request, f"{member.user.get_username()} joined the team.")
        else:
            messages.error(request, "Invalid data. The team member could not be added.")

    return redirect(project.get_absolute_url())


@login_required
def member_remove(request, slug, member_id):
    """Retirer un membre de l'équipe (réservé au chef de projet sur projet brouillon ou refusé)."""
    project = get_object_or_404(Project, slug=slug)
    membership = get_object_or_404(ProjectMember, id=member_id, project=project)

    services.validate_manage_members_permission(request.user, project)

    if request.method == "POST":
        user_name = membership.user.get_username()
        membership.delete()
        messages.success(request, f"{user_name} was removed from the team.")

    return redirect(project.get_absolute_url())


@login_required
def project_admin_dashboard(request):
    """Tableau de bord pour Organizer et Admin."""
    if not services.is_organizer(request.user):
        raise PermissionDenied("Access restricted to organizers and administrators.")

    query = request.GET.get("q", "").strip()
    team_query = request.GET.get("team", "").strip()
    hackathon_filter = request.GET.get("hackathon", "").strip()
    category_filter = request.GET.get("category", "").strip()
    status_filter = request.GET.get("status", "").strip()

    projects_qs = (
        Project.objects.select_related("created_by", "reviewed_by")
        .prefetch_related("team_memberships__user", "members")
        .all()
    )

    total_projects = Project.objects.count()
    submitted_count = Project.objects.filter(status=Project.Status.SUBMITTED).count()
    accepted_count = Project.objects.filter(status=Project.Status.ACCEPTED).count()
    rejected_count = Project.objects.filter(status=Project.Status.REJECTED).count()
    under_review_count = Project.objects.filter(status=Project.Status.UNDER_REVIEW).count()
    draft_count = Project.objects.filter(status=Project.Status.DRAFT).count()
    finalist_count = Project.objects.filter(status=Project.Status.FINALIST).count()
    winner_count = Project.objects.filter(status=Project.Status.WINNER).count()
    total_members = ProjectMember.objects.values("user").distinct().count()

    category_counts = {
        row["category"]: row["total"]
        for row in Project.objects.values("category").annotate(total=Count("id"))
    }
    category_stats = []
    for code, label in Project.Category.choices:
        cnt = category_counts.get(code, 0)
        pct = round((cnt / total_projects * 100), 1) if total_projects > 0 else 0.0
        category_stats.append(
            {
                "code": code,
                "label": label,
                "count": cnt,
                "percentage": pct,
            }
        )
    category_stats.sort(key=lambda c: (-c["count"], c["label"]))

    if query:
        projects_qs = projects_qs.filter(
            Q(title__icontains=query)
            | Q(tagline__icontains=query)
            | Q(description__icontains=query)
        )
    if team_query:
        projects_qs = projects_qs.filter(
            Q(created_by__username__icontains=team_query)
            | Q(members__username__icontains=team_query)
        ).distinct()
    if hackathon_filter:
        projects_qs = projects_qs.filter(hackathon__icontains=hackathon_filter)
    if category_filter and category_filter in Project.Category.values:
        projects_qs = projects_qs.filter(category=category_filter)
    if status_filter and status_filter in Project.Status.values:
        projects_qs = projects_qs.filter(status=status_filter)

    available_hackathons = (
        Project.objects.exclude(hackathon="").values_list("hackathon", flat=True).distinct()
    )

    review_form = ProjectReviewDecisionForm()

    context = {
        "projects": projects_qs,
        "filtered_count": projects_qs.count(),
        "query": query,
        "team_query": team_query,
        "hackathon_filter": hackathon_filter,
        "category_filter": category_filter,
        "status_filter": status_filter,
        "categories": Project.Category.choices,
        "statuses": Project.Status.choices,
        "available_hackathons": available_hackathons,
        "review_form": review_form,
        "score_range": range(1, 11),
        "stats": {
            "total": total_projects,
            "submitted": submitted_count,
            "accepted": accepted_count,
            "rejected": rejected_count,
            "under_review": under_review_count,
            "draft": draft_count,
            "finalist": finalist_count,
            "winner": winner_count,
            "total_members": total_members,
            "categories": category_stats,
        },
    }
    return render(request, "projects/admin_dashboard.html", context)


@login_required
def project_admin_review(request, slug):
    """Accept or reject a project — Organizer/Admin only."""
    project = get_object_or_404(Project, slug=slug)

    # Permission check (also done inside services.review_project)
    services.validate_review_permission(request.user, project)

    if request.method == "POST":
        form = ProjectReviewDecisionForm(request.POST)
        if form.is_valid():
            decision = form.cleaned_data["decision"]
            reason = form.cleaned_data.get("rejection_reason", "").strip()
            try:
                services.review_project(project, request.user, decision, reason)
            except ValueError as exc:
                messages.error(request, str(exc))
                return redirect("projects:admin_dashboard")

            if decision == "accept":
                messages.success(
                    request, f"Project \u00ab {project.title} \u00bb has been accepted!"
                )
            else:
                messages.warning(
                    request,
                    f"Project \u00ab {project.title} \u00bb has been rejected. Reason: {reason}",
                )
            return redirect(request.POST.get("next") or "projects:admin_dashboard")
        else:
            for error in form.errors.values():
                messages.error(request, error)

    return redirect("projects:admin_dashboard")


@login_required
def project_score(request, slug):
    """Attribuer une note/score (1-10) à un projet — réservé aux Organisateurs et Admins."""
    if not services.is_organizer(request.user):
        raise PermissionDenied("Action reserved for organizers and administrators.")

    project = get_object_or_404(Project, slug=slug)

    if request.method == "POST":
        form = ProjectScoreForm(request.POST)
        if form.is_valid():
            score_val = int(form.cleaned_data["score"])
            if 1 <= score_val <= 10:
                project.score = score_val
                project.save(update_fields=["score", "updated_at"])
                messages.success(
                    request, f"Score {score_val}/10 awarded to project '{project.title}'."
                )
            else:
                messages.error(request, "The score must be between 1 and 10.")
        else:
            messages.error(request, "Invalid scoring form.")

    return redirect(request.POST.get("next") or "projects:admin_dashboard")


@login_required
def export_projects_csv(request):
    """Export all (filtered) projects to CSV — restricted to Organizers and Admins."""
    if not services.is_organizer(request.user):
        raise PermissionDenied("CSV export reserved for organizers and administrators.")

    # Appliquer les mêmes filtres que le dashboard
    status_filter = request.GET.get("status", "").strip()
    category_filter = request.GET.get("category", "").strip()
    query = request.GET.get("q", "").strip()

    projects_qs = Project.objects.select_related("created_by", "reviewed_by").all()

    if status_filter and status_filter in Project.Status.values:
        projects_qs = projects_qs.filter(status=status_filter)
    if category_filter and category_filter in Project.Category.values:
        projects_qs = projects_qs.filter(category=category_filter)
    if query:
        projects_qs = projects_qs.filter(Q(title__icontains=query) | Q(tagline__icontains=query))

    # Préparer la réponse HTTP CSV
    filename = f"hackflow_projects_{timezone.now().strftime('%Y%m%d_%H%M')}.csv"
    response = HttpResponse(content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = f'attachment; filename="{filename}"'

    # BOM UTF-8 pour Excel
    response.write("\ufeff")

    writer = csv.writer(response, delimiter=";")

    # En-tête CSV
    writer.writerow(
        [
            "Title",
            "Tagline",
            "Category",
            "Hackathon",
            "Status",
            "Score (1-10)",
            "Creator",
            "Reviewed By",
            "Review Date",
            "Rejection Reason",
            "GitHub",
            "Demo",
            "Created At",
        ]
    )

    # Lignes de données
    for p in projects_qs:
        writer.writerow(
            [
                _csv_safe(p.title),
                _csv_safe(p.tagline),
                p.get_category_display(),
                _csv_safe(p.hackathon or "HackFlow 2026"),
                p.get_status_display(),
                p.score if p.score else "",
                _csv_safe(p.created_by.get_username() if p.created_by else ""),
                _csv_safe(p.reviewed_by.get_username() if p.reviewed_by else ""),
                p.reviewed_at.strftime("%b %d, %Y %H:%M") if p.reviewed_at else "",
                _csv_safe(p.rejection_reason or ""),
                _csv_safe(p.repository_url or ""),
                _csv_safe(p.demo_url or ""),
                p.created_at.strftime("%b %d, %Y %H:%M"),
            ]
        )

    return response


@login_required
def export_projects_pdf(request):
    """Export projects to PDF — restricted to Organizers and Admins."""
    if not services.is_organizer(request.user):
        raise PermissionDenied("PDF export reserved for organizers and administrators.")

    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib import colors
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import cm
    from reportlab.platypus import (
        SimpleDocTemplate,
        Table,
        TableStyle,
        Paragraph,
        Spacer,
        HRFlowable,
    )
    from reportlab.lib.enums import TA_CENTER
    import io

    # Filtres
    status_filter = request.GET.get("status", "").strip()
    category_filter = request.GET.get("category", "").strip()
    query = request.GET.get("q", "").strip()

    projects_qs = Project.objects.select_related("created_by", "reviewed_by").all()
    if status_filter and status_filter in Project.Status.values:
        projects_qs = projects_qs.filter(status=status_filter)
    if category_filter and category_filter in Project.Category.values:
        projects_qs = projects_qs.filter(category=category_filter)
    if query:
        projects_qs = projects_qs.filter(Q(title__icontains=query) | Q(tagline__icontains=query))

    # Couleurs HackFlow
    COLOR_PRIMARY = colors.HexColor("#6366f1")  # Indigo
    COLOR_HEADER = colors.HexColor("#1e293b")  # Slate 800
    COLOR_ROW_ODD = colors.HexColor("#f8fafc")
    COLOR_ROW_EVEN = colors.white
    COLOR_ACCEPT = colors.HexColor("#d1fae5")
    COLOR_REJECT = colors.HexColor("#fee2e2")
    COLOR_SUBMIT = colors.HexColor("#fef3c7")
    COLOR_REVIEW = colors.HexColor("#dbeafe")

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=landscape(A4),
        rightMargin=1.5 * cm,
        leftMargin=1.5 * cm,
        topMargin=1.5 * cm,
        bottomMargin=1.5 * cm,
    )

    story = []

    # ── En-tête du document ──────────────────────────────────
    title_style = ParagraphStyle(
        "HFTitle",
        fontSize=18,
        fontName="Helvetica-Bold",
        textColor=COLOR_PRIMARY,
        alignment=TA_CENTER,
        spaceAfter=4,
    )
    sub_style = ParagraphStyle(
        "HFSub",
        fontSize=9,
        fontName="Helvetica",
        textColor=colors.HexColor("#64748b"),
        alignment=TA_CENTER,
        spaceAfter=2,
    )

    story.append(Paragraph("HackFlow — Projects Report", title_style))
    story.append(
        Paragraph(
            f"Generated on {timezone.now().strftime('%Y-%m-%d at %H:%M')}  •  "
            f"By {request.user.get_username()}  •  "
            f"{projects_qs.count()} project(s)",
            sub_style,
        )
    )
    story.append(HRFlowable(width="100%", thickness=1.5, color=COLOR_PRIMARY, spaceAfter=10))

    # ── Statistiques rapides ──────────────────────────────────
    total = projects_qs.count()
    accepted = projects_qs.filter(status="accepted").count()
    rejected = projects_qs.filter(status="rejected").count()
    submitted = projects_qs.filter(status="submitted").count()
    scored = projects_qs.exclude(score__isnull=True).count()

    stat_data = [
        ["Total", "Accepted", "Rejected", "Submitted", "Scored"],
        [str(total), str(accepted), str(rejected), str(submitted), str(scored)],
    ]
    stat_table = Table(stat_data, colWidths=[4 * cm] * 5)
    stat_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), COLOR_HEADER),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, 0), 8),
                ("FONTNAME", (0, 1), (-1, 1), "Helvetica-Bold"),
                ("FONTSIZE", (0, 1), (-1, 1), 14),
                ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("ROWBACKGROUNDS", (0, 1), (-1, 1), [colors.HexColor("#f1f5f9")]),
                ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#cbd5e1")),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                ("ROUNDEDCORNERS", [4]),
            ]
        )
    )
    story.append(stat_table)
    story.append(Spacer(1, 0.5 * cm))

    # ── Tableau principal des projets ─────────────────────────
    col_headers = [
        "Project Title",
        "Category",
        "Status",
        "Score",
        "Creator",
        "Reviewed By",
        "Decision Date",
    ]
    col_widths = [6.5 * cm, 3.5 * cm, 2.8 * cm, 1.8 * cm, 3 * cm, 3 * cm, 3.5 * cm]

    cell_style = ParagraphStyle(
        "Cell",
        fontSize=7,
        fontName="Helvetica",
        leading=9,
    )
    bold_cell = ParagraphStyle(
        "BoldCell",
        fontSize=7.5,
        fontName="Helvetica-Bold",
        leading=9,
    )

    table_data = [col_headers]

    for p in projects_qs:
        table_data.append(
            [
                Paragraph(
                    f"<b>{p.title}</b><br/><font size='6' color='#64748b'>{p.tagline[:60]}{'…' if len(p.tagline) > 60 else ''}</font>",
                    cell_style,
                ),
                Paragraph(p.get_category_display(), cell_style),
                Paragraph(p.get_status_display(), bold_cell),
                Paragraph(f"{p.score}/10" if p.score else "—", bold_cell),
                Paragraph(p.created_by.get_username() if p.created_by else "—", cell_style),
                Paragraph(p.reviewed_by.get_username() if p.reviewed_by else "—", cell_style),
                Paragraph(
                    p.reviewed_at.strftime("%b %d, %Y") if p.reviewed_at else "—", cell_style
                ),
            ]
        )

    main_table = Table(table_data, colWidths=col_widths, repeatRows=1)

    # Construire les styles de base du tableau
    table_style_cmds = [
        # En-tête
        ("BACKGROUND", (0, 0), (-1, 0), COLOR_HEADER),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, 0), 8),
        ("ALIGN", (0, 0), (-1, 0), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#e2e8f0")),
        ("LINEBELOW", (0, 0), (-1, 0), 1.5, COLOR_PRIMARY),
    ]

    # Coloration par statut
    for i, p in enumerate(projects_qs, start=1):
        if p.status == "accepted":
            bg = COLOR_ACCEPT
        elif p.status == "rejected":
            bg = COLOR_REJECT
        elif p.status == "submitted":
            bg = COLOR_SUBMIT
        elif p.status == "under_review":
            bg = COLOR_REVIEW
        else:
            bg = COLOR_ROW_ODD if i % 2 else COLOR_ROW_EVEN
        table_style_cmds.append(("BACKGROUND", (0, i), (-1, i), bg))

    main_table.setStyle(TableStyle(table_style_cmds))
    story.append(main_table)

    # ── Pied de page ─────────────────────────────────────────
    story.append(Spacer(1, 0.4 * cm))
    story.append(HRFlowable(width="100%", thickness=0.5, color=colors.HexColor("#cbd5e1")))
    story.append(
        Paragraph(
            "Confidential Document — HackFlow Platform — hackflow.com",
            ParagraphStyle(
                "Footer",
                fontSize=7,
                textColor=colors.HexColor("#94a3b8"),
                alignment=TA_CENTER,
                spaceBefore=4,
            ),
        )
    )

    doc.build(story)
    buffer.seek(0)

    filename = f"hackflow_projects_{timezone.now().strftime('%Y%m%d_%H%M')}.pdf"
    response = HttpResponse(buffer, content_type="application/pdf")
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response


@login_required
def project_ai_analyze(request, slug):
    """
    Évaluation IA du projet (score /10, avis d'expert, forces, axes d'amélioration).
    Vérifie côté serveur que l'utilisateur a l'autorisation (403 pour jurys et mentors).
    Mise en cache intelligente (10 min) pour optimiser les performances.

    Asynchrone (AI_ASYNC_ENABLED + Redis/Celery) : l'appel Groq (jusqu'à 15s)
    est délégué à un worker — la requête répond immédiatement en 202 avec un
    task_id que le client fait poller sur ``ai_analyze_status``. Si le broker
    est indisponible ou si l'async est désactivé, on retombe sur l'appel
    synchrone actuel (aucune régression, aucun blocage de la démo).
    """
    project = get_object_or_404(Project, slug=slug)
    services.validate_ai_evaluation_permission(request.user, project)

    if _ai_rate_limited(request.user):
        return JsonResponse({"error": AI_RATE_LIMIT_MESSAGE}, status=429)

    cache_key = f"ai_eval_{project.id}_{int(project.updated_at.timestamp())}"
    data = cache.get(cache_key)

    if data:
        return JsonResponse({**data, "source_key": "cache"})

    category = project.get_category_display() or project.category

    if getattr(settings, "AI_ASYNC_ENABLED", False):
        task_id = tasks.new_task_id()
        tasks.set_task_state(
            task_id,
            {
                "status": tasks.STATUS_PENDING,
                "user_id": request.user.pk,
                "project_id": project.pk,
            },
        )
        try:
            tasks.run_ai_evaluation.apply_async(
                kwargs={
                    "task_id": task_id,
                    "user_id": request.user.pk,
                    "project_id": project.pk,
                    "title": project.title,
                    "tagline": project.tagline,
                    "description": project.description,
                    "category": category,
                    "result_cache_key": cache_key,
                },
                task_id=task_id,
            )
        except Exception:
            # Broker down: log, discard the stale state and fall back to the
            # synchronous call so the endpoint keeps working (robustness).
            logger.exception("Failed to enqueue AI evaluation for project %s", project.pk)
            tasks.discard_task_state(task_id)
        else:
            return JsonResponse(
                {
                    "status": "queued",
                    "task_id": task_id,
                    "status_url": reverse(
                        "projects:ai_analyze_status", args=[project.slug, task_id]
                    ),
                },
                status=202,
            )

    data = ai_service.analyse_project(
        title=project.title,
        tagline=project.tagline,
        description=project.description,
        category=category,
    )
    # Never persist or return the raw exception text: it can leak
    # endpoint/credential details to the client.
    data.pop("error", None)
    if not data.get("failed"):
        cache.set(cache_key, data, timeout=600)

    return JsonResponse(data)


@login_required
def project_ai_analyze_status(request, slug, task_id):
    """Poll l'état d'une évaluation IA différée (mode asynchrone).

    Répond 200 avec ``status`` ∈ pending/done/failed, ou 404 si la tâche est
    inconnue ou expirée — y compris pour une tâche lancée par un autre
    utilisateur : les task_id ne doivent pas être énumérables entre comptes.
    """
    project = get_object_or_404(Project, slug=slug)
    services.validate_ai_evaluation_permission(request.user, project)

    state = tasks.get_task_state(task_id)
    if (
        state is None
        or state.get("project_id") != project.pk
        or state.get("user_id") != request.user.pk
    ):
        return JsonResponse({"error": "Unknown or expired AI task."}, status=404)

    status = state.get("status")
    if status == tasks.STATUS_DONE:
        payload = dict(state.get("payload") or {})
        payload.pop("error", None)
        return JsonResponse({"status": tasks.STATUS_DONE, **payload})
    if status == tasks.STATUS_FAILED:
        return JsonResponse(
            {
                "status": tasks.STATUS_FAILED,
                "error": "The AI evaluation failed. Please try again.",
            }
        )
    return JsonResponse({"status": tasks.STATUS_PENDING})


@login_required
@require_POST
def project_ai_detect_category(request):
    """
    Suggestion IA de catégorie :
    Analyse le titre et la description fournis et propose la catégorie la plus adaptée.

    POST-only: a GET variant would let any third-party page trigger paid AI
    calls with an <img> tag or a link preview.
    """
    if _ai_rate_limited(request.user):
        return JsonResponse({"error": AI_RATE_LIMIT_MESSAGE}, status=429)

    title = request.POST.get("title", "").strip()
    description = request.POST.get("description", "").strip()

    data = ai_service.detect_category(title=title, description=description)
    data.pop("error", None)
    return JsonResponse(data)


@login_required
@require_POST
def project_add_mentor_advice(request, slug):
    """
    Permet à un mentor de publier un conseil pédagogique pour l'équipe du projet.
    Vérification stricte côté serveur : 403 Forbidden si l'utilisateur n'est pas mentor.
    """
    project = get_object_or_404(Project, slug=slug)
    services.validate_add_mentor_advice_permission(request.user, project)

    form = ConseilMentorForm(request.POST)
    if form.is_valid():
        conseil = form.save(commit=False)
        conseil.project = project
        conseil.mentor = request.user
        conseil.save()
        messages.success(request, "Your advice was sent successfully to the team!")
    else:
        messages.error(request, "Advice content cannot be empty.")

    return redirect(project.get_absolute_url())
