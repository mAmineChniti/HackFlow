"""
Administration Django pour le module Gestion des Sponsors.

Configuration de l'interface admin pour Sponsor, Sponsorship et StatusHistory.
"""

from django.contrib import admin
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _

from .models import Sponsor, Sponsorship, StatusChoices, StatusHistory, SponsorEmailLog


STATUS_BADGE_CLASSES = {
    StatusChoices.PROSPECT: "is-neutral",
    StatusChoices.CONTACTE: "is-info",
    StatusChoices.NEGOCIATION: "is-warning",
    StatusChoices.CONFIRME: "is-success",
    StatusChoices.REFUSE: "is-danger",
}


def status_badge(status, label):
    return format_html(
        '<span class="sponsor-admin-badge {}">{}</span>',
        STATUS_BADGE_CLASSES.get(status, "is-neutral"),
        label,
    )


# ---------------------------------------------------------------------------
# Inline : StatusHistory dans Sponsorship
# ---------------------------------------------------------------------------

class StatusHistoryInline(admin.TabularInline):
    """Affiche l'historique des statuts directement dans la page d'un Sponsorship."""

    model = StatusHistory
    extra = 0
    readonly_fields = ("old_status", "new_status", "changed_by", "changed_at")
    can_delete = False  # L'historique est immuable

    def has_add_permission(self, request, obj=None):
        # On n'ajoute pas manuellement : l'historique est créé via change_status()
        return False


# ---------------------------------------------------------------------------
# Inline : Sponsorship dans Sponsor
# ---------------------------------------------------------------------------

class SponsorshipInline(admin.TabularInline):
    """Affiche les partenariats d'un sponsor directement dans sa page admin."""

    model = Sponsorship
    extra = 0
    fields = ("hackathon", "tier", "status", "contribution_type", "amount")
    readonly_fields = ("status",)  # Le statut se change via la vue Kanban


# ---------------------------------------------------------------------------
# Admin : Sponsor
# ---------------------------------------------------------------------------

@admin.register(Sponsor)
class SponsorAdmin(admin.ModelAdmin):
    change_list_template = "admin/sponsors/change_list.html"
    change_form_template = "admin/sponsors/change_form.html"
    delete_confirmation_template = "admin/sponsors/delete_confirmation.html"
    delete_selected_confirmation_template = "admin/sponsors/delete_selected_confirmation.html"
    object_history_template = "admin/sponsors/object_history.html"

    list_display = ("name", "sector", "contact_email", "logo_preview", "created_at")
    list_filter = ("sector",)
    search_fields = ("name", "contact_name", "contact_email")
    readonly_fields = ("created_at", "updated_at", "logo_preview")
    inlines = [SponsorshipInline]

    fieldsets = (
        (None, {
            "fields": ("name", "logo", "logo_preview", "website", "sector", "description"),
        }),
        (_("Contact"), {
            "fields": ("contact_name", "contact_email"),
        }),
        (_("Métadonnées"), {
            "fields": ("created_at", "updated_at"),
            "classes": ("collapse",),
        }),
    )

    @admin.display(description=_("Logo"))
    def logo_preview(self, obj):
        """Affiche une miniature du logo dans l'admin."""
        if obj.logo:
            return format_html(
                '<img src="{}" style="max-height:40px; max-width:80px; object-fit:contain;" />',
                obj.logo.url,
            )
        return "—"


# ---------------------------------------------------------------------------
# Admin : Sponsorship
# ---------------------------------------------------------------------------

@admin.register(Sponsorship)
class SponsorshipAdmin(admin.ModelAdmin):
    change_list_template = "admin/sponsors/change_list.html"
    change_form_template = "admin/sponsors/change_form.html"
    delete_confirmation_template = "admin/sponsors/delete_confirmation.html"
    delete_selected_confirmation_template = "admin/sponsors/delete_selected_confirmation.html"
    object_history_template = "admin/sponsors/object_history.html"

    list_display = (
        "sponsor", "hackathon", "tier", "status_badge",
        "contribution_type", "amount", "updated_at",
    )
    list_filter = ("tier", "status", "contribution_type", "hackathon")
    search_fields = ("sponsor__name", "hackathon__name", "notes")
    readonly_fields = ("created_at", "updated_at")
    inlines = [StatusHistoryInline]

    fieldsets = (
        (None, {
            "fields": ("sponsor", "hackathon", "tier", "status"),
        }),
        (_("Contribution"), {
            "fields": ("contribution_type", "amount"),
        }),
        (_("Notes"), {
            "fields": ("notes",),
        }),
        (_("Métadonnées"), {
            "fields": ("created_at", "updated_at"),
            "classes": ("collapse",),
        }),
    )

    actions = ["marquer_confirme", "marquer_refuse"]

    @admin.display(description=_("Status"), ordering="status")
    def status_badge(self, obj):
        return status_badge(obj.status, obj.get_status_display())

    @admin.action(description=_("Marquer comme Confirmé"))
    def marquer_confirme(self, request, queryset):
        from .models import StatusChoices
        for sp in queryset:
            if sp.status != StatusChoices.CONFIRME:
                sp.change_status(StatusChoices.CONFIRME, request.user)
        self.message_user(request, _("Partenariats marqués comme confirmés."))

    @admin.action(description=_("Marquer comme Refusé"))
    def marquer_refuse(self, request, queryset):
        from .models import StatusChoices
        for sp in queryset:
            if sp.status != StatusChoices.REFUSE:
                sp.change_status(StatusChoices.REFUSE, request.user)
        self.message_user(request, _("Partenariats marqués comme refusés."))


# ---------------------------------------------------------------------------
# Admin : StatusHistory
# ---------------------------------------------------------------------------

@admin.register(StatusHistory)
class StatusHistoryAdmin(admin.ModelAdmin):
    change_list_template = "admin/sponsors/change_list.html"
    object_history_template = "admin/sponsors/object_history.html"

    list_display = (
        "sponsorship", "old_status_badge", "new_status_badge", "changed_by", "changed_at"
    )
    list_filter = ("new_status", "old_status")
    search_fields = ("sponsorship__sponsor__name", "changed_by__username")
    readonly_fields = ("sponsorship", "old_status", "new_status", "changed_by", "changed_at")

    @admin.display(description=_("Previous status"), ordering="old_status")
    def old_status_badge(self, obj):
        return status_badge(obj.old_status, obj.get_old_status_display())

    @admin.display(description=_("New status"), ordering="new_status")
    def new_status_badge(self, obj):
        return status_badge(obj.new_status, obj.get_new_status_display())

    def has_add_permission(self, request):
        # L'historique est créé automatiquement via change_status()
        return False

    def has_change_permission(self, request, obj=None):
        # L'historique est immuable
        return False

    def has_delete_permission(self, request, obj=None):
        # L'historique ne peut pas être supprimé
        return False


# ---------------------------------------------------------------------------
# Admin : SponsorEmailLog
# ---------------------------------------------------------------------------

@admin.register(SponsorEmailLog)
class SponsorEmailLogAdmin(admin.ModelAdmin):
    change_list_template = "admin/sponsors/change_list.html"
    object_history_template = "admin/sponsors/object_history.html"

    list_display = (
        "sponsor", "subject", "sent_by", "sent_at", "ai_generated", "delivery_badge"
    )
    list_filter = ("success", "ai_generated", "sent_at")
    search_fields = ("sponsor__name", "subject", "body", "sent_by__username")
    readonly_fields = ("sponsor", "sent_by", "subject", "body", "sent_at", "ai_generated", "success", "error_message")

    @admin.display(description=_("Delivery"), ordering="success")
    def delivery_badge(self, obj):
        badge_class = "is-success" if obj.success else "is-danger"
        label = _("Sent") if obj.success else _("Failed")
        return format_html('<span class="sponsor-admin-badge {}">{}</span>', badge_class, label)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
