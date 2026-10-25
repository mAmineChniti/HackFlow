"""Administration Django pour le module Gestion des Sponsors."""

from decimal import Decimal

from django.contrib import admin
from django.contrib.admin.filters import DateFieldListFilter
from django.contrib.admin import SimpleListFilter
from django.db.models import Count, DecimalField, Q, Sum, Value
from django.db.models.functions import Coalesce
from django.template.response import TemplateResponse
from django.utils.formats import number_format
from django.utils.text import Truncator
from django.utils.translation import gettext_lazy as _

from .models import (
    Sponsor,
    SponsorEmailLog,
    Sponsorship,
    StatusChoices,
    StatusHistory,
    TierChoices,
)
from .permissions import (
    can_delete,
    can_manage_sponsors,
    can_view_confidential,
)
from .services import change_sponsorship_status


class SponsorAdminBase(admin.ModelAdmin):
    """Shared sponsor-role and Django-permission gates for these four models."""

    def has_module_permission(self, request):
        return (
            can_view_confidential(request.user)
            and super().has_module_permission(request)
        )

    def has_view_permission(self, request, obj=None):
        return (
            can_view_confidential(request.user)
            and super().has_view_permission(request, obj)
        )

    def has_add_permission(self, request):
        return (
            can_manage_sponsors(request.user)
            and super().has_add_permission(request)
        )

    def has_change_permission(self, request, obj=None):
        return (
            can_manage_sponsors(request.user)
            and super().has_change_permission(request, obj)
        )

    def has_delete_permission(self, request, obj=None):
        return (
            can_delete(request.user)
            and super().has_delete_permission(request, obj)
        )

    def get_queryset(self, request):
        queryset = super().get_queryset(request)
        if not can_view_confidential(request.user):
            return queryset.none()
        return queryset


class StatusHistoryInline(admin.TabularInline):
    model = StatusHistory
    extra = 0
    fields = ("old_status", "new_status", "changed_by", "changed_at")
    readonly_fields = fields
    can_delete = False
    show_change_link = False

    def has_add_permission(self, request, obj=None):
        return False

    def has_view_permission(self, request, obj=None):
        return (
            can_view_confidential(request.user)
            and (
                request.user.has_perm("sponsors.view_sponsorship")
                or request.user.has_perm("sponsors.change_sponsorship")
            )
        )

    def has_change_permission(self, request, obj=None):
        return self.has_view_permission(request, obj)


class SponsorshipInline(admin.TabularInline):
    model = Sponsorship
    extra = 0
    fields = ("hackathon", "tier", "status", "contribution_type", "amount")
    readonly_fields = ("status",)


class TierListFilter(SimpleListFilter):
    title = _("Tier")
    parameter_name = "tier"

    def lookups(self, request, model_admin):
        return (
            (TierChoices.PLATINUM, _("Platinum")),
            (TierChoices.GOLD, _("Gold")),
            (TierChoices.SILVER, _("Silver")),
            (TierChoices.BRONZE, _("Bronze")),
        )

    def queryset(self, request, queryset):
        if self.value():
            return queryset.filter(tier=self.value())
        return queryset


@admin.register(Sponsor)
class SponsorAdmin(SponsorAdminBase):
    list_display = (
        "name",
        "sector",
        "sponsorship_count",
        "confirmed_total",
        "created_at",
    )
    list_filter = ("sector",)
    search_fields = ("name", "sector")
    ordering = ("name",)
    list_per_page = 25
    readonly_fields = ("created_at", "updated_at")
    inlines = (SponsorshipInline,)

    fieldsets = (
        (_("Identity"), {
            "fields": ("name", "logo", "website", "sector", "description"),
            "description": _("Public information about the sponsor."),
        }),
        (_("Contact"), {
            "fields": ("contact_name", "contact_email"),
            "description": _("Confidential contact details for authorized roles only."),
        }),
        (_("Metadata"), {
            "fields": ("created_at", "updated_at"),
            "classes": ("collapse",),
        }),
    )

    @admin.display(description=_("Partnerships"), ordering="sponsorship_count")
    def sponsorship_count(self, obj):
        return obj.sponsorship_count

    @admin.display(
        description=_("Confirmed total (DT)"),
        ordering="confirmed_amount",
    )
    def confirmed_total(self, obj):
        return number_format(
            obj.confirmed_amount,
            decimal_pos=3,
            use_l10n=True,
            force_grouping=True,
        )

    def get_queryset(self, request):
        return super().get_queryset(request).annotate(
            sponsorship_count=Count("sponsorships"),
            confirmed_amount=Coalesce(
                Sum(
                    "sponsorships__amount",
                    filter=Q(sponsorships__status=StatusChoices.CONFIRME),
                ),
                Value(Decimal("0.000")),
                output_field=DecimalField(max_digits=15, decimal_places=3),
            ),
        )


@admin.register(Sponsorship)
class SponsorshipAdmin(SponsorAdminBase):
    list_display = (
        "sponsor",
        "hackathon",
        "tier_display",
        "status_display",
        "contribution_type",
        "formatted_amount",
        "updated_at",
    )
    list_filter = ("status", TierListFilter, "hackathon", "contribution_type")
    search_fields = ("sponsor__name", "hackathon__name")
    date_hierarchy = "updated_at"
    ordering = ("-updated_at", "sponsor__name")
    list_per_page = 25
    readonly_fields = ("current_status", "created_at", "updated_at")
    inlines = (StatusHistoryInline,)
    actions = (
        "mark_contacted",
        "mark_negotiation",
        "mark_confirmed",
        "mark_refused",
    )

    fieldsets = (
        (_("Identity"), {
            "fields": ("sponsor", "hackathon"),
            "description": _("Choose the sponsor and the relevant hackathon."),
        }),
        (_("Contract"), {
            "fields": ("tier", "contribution_type", "amount", "current_status"),
            "description": _("Change the status using the actions on the list."),
        }),
        (_("Internal notes"), {
            "fields": ("notes",),
            "description": _("Confidential notes visible only to authorized roles."),
        }),
        (_("Metadata"), {
            "fields": ("created_at", "updated_at"),
            "classes": ("collapse",),
        }),
    )

    def get_queryset(self, request):
        return super().get_queryset(request).select_related("sponsor", "hackathon")

    def get_form(self, request, obj=None, **kwargs):
        form = super().get_form(request, obj, **kwargs)
        form.base_fields["tier"].choices = (
            (TierChoices.PLATINUM, _("Platinum")),
            (TierChoices.GOLD, _("Gold")),
            (TierChoices.SILVER, _("Silver")),
            (TierChoices.BRONZE, _("Bronze")),
        )
        form.base_fields["tier"].label = _("Tier")
        return form

    @admin.display(description=_("Tier"), ordering="tier")
    def tier_display(self, obj):
        return {
            TierChoices.PLATINUM: _("Platinum"),
            TierChoices.GOLD: _("Gold"),
            TierChoices.SILVER: _("Silver"),
            TierChoices.BRONZE: _("Bronze"),
        }[obj.tier]

    def changelist_view(self, request, extra_context=None):
        response = super().changelist_view(request, extra_context=extra_context)
        if isinstance(response, TemplateResponse) and response.context_data:
            total = response.context_data["cl"].queryset.aggregate(
                amount=Coalesce(
                    Sum("amount"),
                    Value(Decimal("0.000")),
                    output_field=DecimalField(max_digits=15, decimal_places=3),
                )
            )["amount"]
            response.context_data["sponsorship_totals"] = {
                "amount": total,
                "amount_display": number_format(
                    total,
                    decimal_pos=3,
                    use_l10n=True,
                    force_grouping=True,
                ),
            }
        return response

    @admin.display(description=_("Status"), ordering="status")
    def status_display(self, obj):
        return obj.get_status_display()

    @admin.display(description=_("Amount (DT)"), ordering="amount")
    def formatted_amount(self, obj):
        amount = number_format(
            obj.amount,
            decimal_pos=3,
            use_l10n=True,
            force_grouping=True,
        )
        return f"{amount} DT"

    @admin.display(description=_("Current status"))
    def current_status(self, obj):
        if obj is None:
            return StatusChoices.PROSPECT.label
        return obj.get_status_display()

    def _apply_status(self, request, queryset, new_status, label):
        changed = 0
        for sponsorship_id in queryset.values_list("pk", flat=True):
            if change_sponsorship_status(
                sponsorship_id,
                new_status,
                request.user,
            ) is not None:
                changed += 1
        self.message_user(
            request,
            _("Applied status “%(status)s” to %(count)d partnership(s).")
            % {"status": label, "count": changed},
        )

    @admin.action(description=_("Mark as contacted"))
    def mark_contacted(self, request, queryset):
        self._apply_status(
            request, queryset, StatusChoices.CONTACTE, StatusChoices.CONTACTE.label
        )

    @admin.action(description=_("Mark as negotiating"))
    def mark_negotiation(self, request, queryset):
        self._apply_status(
            request,
            queryset,
            StatusChoices.NEGOCIATION,
            StatusChoices.NEGOCIATION.label,
        )

    @admin.action(description=_("Mark as confirmed"))
    def mark_confirmed(self, request, queryset):
        self._apply_status(
            request, queryset, StatusChoices.CONFIRME, StatusChoices.CONFIRME.label
        )

    @admin.action(description=_("Mark as declined"))
    def mark_refused(self, request, queryset):
        self._apply_status(
            request, queryset, StatusChoices.REFUSE, StatusChoices.REFUSE.label
        )


@admin.register(StatusHistory)
class StatusHistoryAdmin(SponsorAdminBase):
    list_display = ("sponsorship", "status_transition", "changed_by", "changed_at")
    list_filter = ("new_status", "old_status", ("changed_at", DateFieldListFilter))
    search_fields = ("sponsorship__sponsor__name", "changed_by__username")
    date_hierarchy = "changed_at"
    ordering = ("-changed_at",)
    list_per_page = 25
    list_display_links = None
    readonly_fields = (
        "sponsorship",
        "old_status",
        "new_status",
        "changed_by",
        "changed_at",
    )

    def get_queryset(self, request):
        return super().get_queryset(request).select_related(
            "sponsorship__sponsor",
            "sponsorship__hackathon",
            "changed_by",
        )

    @admin.display(description=_("Status change"))
    def status_transition(self, obj):
        if not obj.old_status or obj.old_status == obj.new_status:
            return _("Created")
        return f"{obj.get_old_status_display()} → {obj.get_new_status_display()}"

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(SponsorEmailLog)
class SponsorEmailLogAdmin(SponsorAdminBase):
    list_display = (
        "sponsor",
        "subject",
        "sent_by",
        "sent_at",
        "ai_generated_badge",
        "delivery_badge",
        "error_summary",
    )
    list_filter = (
        ("sent_at", DateFieldListFilter),
        "sent_by",
        "success",
        "ai_generated",
    )
    search_fields = ("sponsor__name", "subject", "sent_by__username")
    date_hierarchy = "sent_at"
    ordering = ("-sent_at",)
    list_per_page = 25
    list_display_links = None
    readonly_fields = (
        "sponsor",
        "sent_by",
        "subject",
        "body",
        "sent_at",
        "ai_generated",
        "success",
        "error_message",
    )

    def get_queryset(self, request):
        return super().get_queryset(request).select_related("sponsor", "sent_by")

    @admin.display(description=_("AI generated"), ordering="ai_generated")
    def ai_generated_badge(self, obj):
        return _("AI generated") if obj.ai_generated else _("Written manually")

    @admin.display(description=_("Delivery"), ordering="success")
    def delivery_badge(self, obj):
        return _("Sent") if obj.success else _("Failed")

    @admin.display(description=_("Error"))
    def error_summary(self, obj):
        if not obj.error_message:
            return "—"
        return Truncator(obj.error_message).chars(100)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
