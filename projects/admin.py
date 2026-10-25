from django.contrib import admin
from django.core.exceptions import PermissionDenied

from . import services
from .models import ConseilMentor, HistoriqueProjet, Project, ProjectMember

# Status changes performed through the admin must reach the immutable audit log,
# otherwise HistoriqueProjet stops being a complete record of decisions.
STATUS_TO_HISTORY_ACTION = {
    Project.Status.SUBMITTED: HistoriqueProjet.Action.SUBMITTED,
    Project.Status.UNDER_REVIEW: HistoriqueProjet.Action.UNDER_REVIEW,
    Project.Status.ACCEPTED: HistoriqueProjet.Action.ACCEPTED,
    Project.Status.REJECTED: HistoriqueProjet.Action.REJECTED,
    Project.Status.FINALIST: HistoriqueProjet.Action.FINALIST,
    Project.Status.WINNER: HistoriqueProjet.Action.WINNER,
}


class HistoriqueProjetInline(admin.TabularInline):
    """Read-only inline showing project history inside the Project admin page."""
    model = HistoriqueProjet
    extra = 0
    can_delete = False
    fields = ("date", "action", "acteur", "commentaire")
    readonly_fields = ("date", "action", "acteur", "commentaire")
    ordering = ("date",)
    show_change_link = False

    def has_add_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return False



class ProjectMemberInline(admin.TabularInline):
    model = ProjectMember
    extra = 1
    autocomplete_fields = ["user"]
    fields = ("user", "role", "is_accepted", "joined_at")
    readonly_fields = ("joined_at",)


@admin.register(Project)
class ProjectAdmin(admin.ModelAdmin):
    list_display = (
        "title",
        "category",
        "hackathon",
        "status",
        "score",
        "created_by",
        "reviewed_by",
        "reviewed_at",
        "members_count",
        "created_at",
    )
    list_editable = ("status",)
    list_filter = ("status", "category", "hackathon", "created_at", "reviewed_at")
    search_fields = (
        "title",
        "tagline",
        "description",
        "hackathon",
        "created_by__username",
        "created_by__email",
        "members__username",
    )
    prepopulated_fields = {"slug": ("title",)}
    date_hierarchy = "created_at"
    readonly_fields = ("reviewed_at",)
    inlines = [ProjectMemberInline, HistoriqueProjetInline]
    actions = [
        "accept_selected_projects",
        "reject_selected_projects",
        "mark_under_review",
    ]

    fieldsets = (
        (
            "Informations Générales",
            {
                "fields": (
                    "title",
                    "slug",
                    "tagline",
                    "description",
                    "category",
                    "hackathon",
                    "status",
                    "deadline",
                )
            },
        ),
        (
            "Évaluation & Décision Admin",
            {
                "fields": (
                    "score",
                    "rejection_reason",
                    "reviewed_by",
                    "reviewed_at",
                )
            },
        ),
        (
            "Ressources & Liens",
            {
                "fields": (
                    "repository_url",
                    "demo_url",
                    "video_url",
                )
            },
        ),
        (
            "Responsable",
            {
                "fields": ("created_by",),
            },
        ),
    )

    @admin.action(description="✅ Valider / Accepter les projets sélectionnés")
    def accept_selected_projects(self, request, queryset):
        # Goes through services.review_project so each decision is written to
        # HistoriqueProjet and invalid statuses are skipped instead of forced.
        accepted = skipped = 0
        for project in queryset:
            try:
                services.review_project(project, request.user, "accept")
            except (PermissionDenied, ValueError):
                skipped += 1
                continue
            accepted += 1
        self._report_action(
            request, accepted, skipped, "accepté(s) avec succès"
        )

    @admin.action(description="❌ Refuser les projets sélectionnés")
    def reject_selected_projects(self, request, queryset):
        rejected = skipped = 0
        for project in queryset:
            try:
                services.review_project(
                    project,
                    request.user,
                    "reject",
                    "Refusé depuis l'administration Django.",
                )
            except (PermissionDenied, ValueError):
                skipped += 1
                continue
            rejected += 1
        self._report_action(request, rejected, skipped, "refusé(s)")

    @admin.action(description="⏳ Marquer en cours d'évaluation (Under Review)")
    def mark_under_review(self, request, queryset):
        updated = skipped = 0
        for project in queryset:
            try:
                services.change_project_status(
                    project, request.user, Project.Status.UNDER_REVIEW
                )
            except (PermissionDenied, ValueError):
                skipped += 1
                continue
            updated += 1
        self._report_action(
            request, updated, skipped, "passé(s) en cours d'évaluation"
        )

    def _report_action(self, request, done: int, skipped: int, label: str):
        message = f"{done} projet(s) {label}."
        if skipped:
            message += (
                f" {skipped} ignoré(s) : statut non évaluable ou décision déjà appliquée."
            )
        self.message_user(request, message)

    def save_model(self, request, obj, form, change):
        """Record admin status edits (change form and list_editable) in history."""
        previous_status = None
        if change and obj.pk:
            previous_status = (
                Project.objects.filter(pk=obj.pk)
                .values_list("status", flat=True)
                .first()
            )

        super().save_model(request, obj, form, change)

        if previous_status and previous_status != obj.status:
            action = STATUS_TO_HISTORY_ACTION.get(obj.status)
            if action:
                services.create_history_entry(
                    obj,
                    action,
                    request.user,
                    commentaire=obj.rejection_reason
                    if obj.status == Project.Status.REJECTED
                    else "",
                )

    @admin.display(description="Nb Membres")
    def members_count(self, obj):
        return obj.members.count()


@admin.register(ProjectMember)
class ProjectMemberAdmin(admin.ModelAdmin):
    list_display = ("project", "user", "role", "is_accepted", "joined_at")
    list_editable = ("role", "is_accepted")
    list_filter = ("role", "is_accepted", "joined_at")
    search_fields = ("project__title", "user__username", "user__email")
    autocomplete_fields = ["project", "user"]


@admin.register(ConseilMentor)
class ConseilMentorAdmin(admin.ModelAdmin):
    list_display = ("project", "mentor", "texte_short", "date")
    list_filter = ("date", "mentor")
    search_fields = ("project__title", "mentor__username", "texte")
    autocomplete_fields = ["project", "mentor"]

    @admin.display(description="Conseil")
    def texte_short(self, obj):
        return obj.texte[:80] + "..." if len(obj.texte) > 80 else obj.texte


@admin.register(HistoriqueProjet)
class HistoriqueProjetAdmin(admin.ModelAdmin):
    """
    Audit log admin — fully read-only to preserve traceability.
    No record can be manually added, modified or deleted.
    """
    list_display = ("project", "action", "acteur", "date", "commentaire_short")
    list_filter = ("action", "date", "project__status")
    search_fields = ("project__title", "acteur__username")
    date_hierarchy = "date"
    ordering = ("-date",)
    readonly_fields = ("project", "action", "acteur", "commentaire", "date")

    def get_fields(self, request, obj=None):
        return ["project", "action", "acteur", "date", "commentaire"]

    @admin.display(description="Comment")
    def commentaire_short(self, obj):
        if not obj.commentaire:
            return "—"
        return obj.commentaire[:60] + "..." if len(obj.commentaire) > 60 else obj.commentaire

    # ── Deny all write operations ──────────────────────────────────────────────

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def change_view(self, request, object_id, form_url="", extra_context=None):
        """Redirect any attempt to open the change/detail view back to the list."""
        from django.contrib import messages as dj_messages
        from django.http import HttpResponseRedirect
        from django.urls import reverse
        dj_messages.warning(request, "Project history entries are read-only and cannot be modified.")
        return HttpResponseRedirect(
            reverse("admin:projects_historiqueprojet_changelist")
        )
