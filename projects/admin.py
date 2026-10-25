from django.contrib import admin
from .models import ConseilMentor, HistoriqueProjet, Project, ProjectMember


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
        from django.utils import timezone
        updated = queryset.update(
            status=Project.Status.ACCEPTED,
            rejection_reason="",
            reviewed_by=request.user,
            reviewed_at=timezone.now(),
        )
        self.message_user(request, f"{updated} projet(s) accepté(s) avec succès.")

    @admin.action(description="❌ Refuser les projets sélectionnés")
    def reject_selected_projects(self, request, queryset):
        from django.utils import timezone
        updated = queryset.update(
            status=Project.Status.REJECTED,
            rejection_reason="Refusé depuis l'administration Django.",
            reviewed_by=request.user,
            reviewed_at=timezone.now(),
        )
        self.message_user(request, f"{updated} projet(s) refusé(s).")

    @admin.action(description="⏳ Marquer en cours d'évaluation (Under Review)")
    def mark_under_review(self, request, queryset):
        updated = queryset.update(status=Project.Status.UNDER_REVIEW)
        self.message_user(request, f"{updated} projet(s) passé(s) en cours d'évaluation.")

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
