"""
Vues du module Gestion des Sponsors — HackFlow ESPRIT.

Contient :
- La page publique "Nos Sponsors" (accessible à tous)
- Staff-facing dashboard protected by the sponsor permission mixin
- Le CRUD complet pour Sponsor et Sponsorship
- L'action HTMX de changement rapide de statut avec historique
"""

from django.contrib import messages
from django.db.models import Count, Sum, Q
from django.http import Http404, HttpResponse, HttpResponseRedirect
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse, reverse_lazy
from django.views import View
from django.views.generic import (
    CreateView,
    DeleteView,
    DetailView,
    ListView,
    TemplateView,
    UpdateView,
)

from django.utils import timezone
from .forms import QuickStatusChangeForm, SponsorContactForm, SponsorForm, SponsorshipForm
from .mixins import SponsorPermissionRequiredMixin
from .models import (
    SECTOR_CHOICES,
    Sponsor,
    SponsorEmailLog,
    Sponsorship,
    StatusChoices,
    StatusHistory,
    TierChoices,
)
from .permissions import (
    can_manage_sponsorship,
    sponsors_visible_to,
    sponsorships_visible_to,
)
from .services import compose_email, send_sponsor_contact_email
from .ai import generate_prospecting_email, recommend_sponsors_for_hackathon
from .reports import export_sponsorships_to_excel

try:
    from hackathons.models import Hackathon
except ImportError:
    Hackathon = None


# ==============================================================================
# Public sponsor pages
# ==============================================================================

class PublicSponsorListView(TemplateView):
    """
    Public showcase of confirmed HackFlow sponsors, grouped by sponsorship tier.
    """

    template_name = "sponsors/public_list.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        # Liste des hackathons disponibles pour filtrage
        hackathons = Hackathon.objects.all().order_by("-start_date") if Hackathon else []
        selected_hackathon_id = self.request.GET.get("hackathon")

        # Filtrer uniquement les sponsorships confirmés pour l'affichage public
        # Confirmed sponsor details are public; confidential listings use the
        # role-scoped queryset below in staff-facing views.
        visible_sponsorships = sponsorships_visible_to(self.request.user)
        public_confirmed = Sponsorship.objects.filter(status=StatusChoices.CONFIRME)
        confirmed_sponsorships = (visible_sponsorships | public_confirmed).filter(
            status=StatusChoices.CONFIRME
        ).select_related("sponsor", "hackathon")

        selected_hackathon = None
        if selected_hackathon_id and Hackathon:
            try:
                selected_hackathon = Hackathon.objects.get(pk=selected_hackathon_id)
                confirmed_sponsorships = confirmed_sponsorships.filter(hackathon=selected_hackathon)
            except Hackathon.DoesNotExist:
                pass

        # Regrouper par niveau (Tier)
        context["platinum_sponsorships"] = confirmed_sponsorships.filter(tier=TierChoices.PLATINUM)
        context["gold_sponsorships"] = confirmed_sponsorships.filter(tier=TierChoices.GOLD)
        context["silver_sponsorships"] = confirmed_sponsorships.filter(tier=TierChoices.SILVER)
        context["bronze_sponsorships"] = confirmed_sponsorships.filter(tier=TierChoices.BRONZE)

        context["hackathons"] = hackathons
        context["selected_hackathon"] = selected_hackathon
        context["total_confirmed"] = confirmed_sponsorships.count()

        return context


# ==============================================================================
# Staff dashboard
# ==============================================================================

class SponsorDashboardView(SponsorPermissionRequiredMixin, TemplateView):
    """
    Organizer dashboard with financial KPIs, prospecting pipeline, and recent history.
    """

    template_name = "sponsors/dashboard.html"
    required_permission = "view_confidential"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        # Récupération des hackathons pour le filtre
        hackathons = Hackathon.objects.all().order_by("-start_date") if Hackathon else []
        hackathon_filter = self.request.GET.get("hackathon")

        sponsorships = sponsorships_visible_to(self.request.user).select_related(
            "sponsor", "hackathon"
        )
        selected_hackathon = None

        if hackathon_filter and Hackathon:
            try:
                selected_hackathon = Hackathon.objects.get(pk=hackathon_filter)
                sponsorships = sponsorships.filter(hackathon=selected_hackathon)
            except Hackathon.DoesNotExist:
                pass

        # KPIs financiers et quantitatifs
        total_sponsors_count = Sponsor.objects.filter(
            sponsorships__in=sponsorships
        ).distinct().count()
        total_partnerships_count = sponsorships.count()

        confirmed_qs = sponsorships.filter(status=StatusChoices.CONFIRME)
        confirmed_count = confirmed_qs.count()
        total_funds_confirmed = confirmed_qs.aggregate(total=Sum("amount"))["total"] or 0

        negotiating_count = sponsorships.filter(status=StatusChoices.NEGOCIATION).count()
        potential_funds = sponsorships.filter(
            status__in=[StatusChoices.PROSPECT, StatusChoices.CONTACTE, StatusChoices.NEGOCIATION]
        ).aggregate(total=Sum("amount"))["total"] or 0

        # Répartition par statut dans le pipeline
        pipeline_stats = {}
        for choice_key, choice_label in StatusChoices.choices:
            qs_status = sponsorships.filter(status=choice_key)
            pipeline_stats[choice_key] = {
                "label": choice_label,
                "count": qs_status.count(),
                "sum": qs_status.aggregate(s=Sum("amount"))["s"] or 0,
            }

        # Derniers partenariats et historiques récents
        recent_sponsorships = sponsorships.order_by("-updated_at")[:12]
        recent_history = StatusHistory.objects.select_related(
            "sponsorship__sponsor", "sponsorship__hackathon", "changed_by"
        ).filter(sponsorship__in=sponsorships).order_by("-changed_at")[:10]

        # Recommandations vectorielles IA (TF-IDF + Cosine Similarity) pour le hackathon actif
        target_hackathon = selected_hackathon or (hackathons[0] if hackathons else None)
        ai_recs_data = (
            recommend_sponsors_for_hackathon(
                target_hackathon,
                top_n=5,
                user=self.request.user,
            )
            if target_hackathon
            else {"recommendations": [], "message": "No hackathons are available to calculate matches."}
        )

        context.update({
            "hackathons": hackathons,
            "selected_hackathon": selected_hackathon,
            "target_hackathon": target_hackathon,
            "ai_recommendations": ai_recs_data.get("recommendations", []),
            "ai_recommendations_message": ai_recs_data.get("message", ""),
            "total_sponsors_count": total_sponsors_count,
            "total_partnerships_count": total_partnerships_count,
            "confirmed_count": confirmed_count,
            "total_funds_confirmed": total_funds_confirmed,
            "negotiating_count": negotiating_count,
            "potential_funds": potential_funds,
            "pipeline_stats": pipeline_stats,
            "recent_sponsorships": recent_sponsorships,
            "recent_history": recent_history,
            "status_choices": StatusChoices.choices,
        })
        return context


# ==============================================================================
# GESTION DES ENTREPRISES SPONSORS (Directory CRUD)
# ==============================================================================

def filter_sponsorships_queryset(params, user=None) -> "QuerySet[Sponsorship]":
    """
    Applique les filtres multicritères sur les partenariats :
    recherche textuelle (nom, contact, description), secteur, tier, statut, hackathon.
    Réutilisé à la fois par la liste HTMX et l'export Excel.
    """
    qs = (
        sponsorships_visible_to(user)
        .select_related("sponsor", "hackathon")
        .order_by("-updated_at", "-created_at")
    )
    query = params.get("q", "").strip()
    sector = params.get("sector", "").strip()
    tier = params.get("tier", "").strip()
    status = params.get("status", "").strip()
    hackathon_id = params.get("hackathon", "").strip()

    if query:
        qs = qs.filter(
            Q(sponsor__name__icontains=query)
            | Q(sponsor__contact_name__icontains=query)
            | Q(sponsor__description__icontains=query)
        )

    if sector:
        qs = qs.filter(sponsor__sector=sector)

    if tier:
        qs = qs.filter(tier=tier)

    if status:
        qs = qs.filter(status=status)

    if hackathon_id:
        qs = qs.filter(hackathon_id=hackathon_id)

    return qs


class SponsorDirectoryView(SponsorPermissionRequiredMixin, ListView):
    """
    Gestion des partenariats et sponsors (Staff only) avec recherche live,
    filtres multicritères (secteur, tier, statut, hackathon) et pagination HTMX (10 par page).
    """

    model = Sponsorship
    context_object_name = "sponsorships"
    paginate_by = 10
    required_permission = "view_confidential"

    def get_template_names(self):
        # Si la requête provient d'HTMX, on ne renvoie que le partial du tableau + pagination
        if getattr(self.request, "htmx", False) or self.request.headers.get("HX-Request"):
            return ["sponsors/partials/sponsors_table.html"]
        return ["sponsors/sponsor_list.html"]

    def get_queryset(self):
        return filter_sponsorships_queryset(self.request.GET, self.request.user)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["sectors"] = SECTOR_CHOICES
        context["tiers"] = TierChoices.choices
        context["statuses"] = StatusChoices.choices
        context["hackathons"] = (
            Hackathon.objects.all().order_by("-start_date") if Hackathon else []
        )
        context["query"] = self.request.GET.get("q", "")
        context["selected_sector"] = self.request.GET.get("sector", "")
        context["selected_tier"] = self.request.GET.get("tier", "")
        context["selected_status"] = self.request.GET.get("status", "")
        context["selected_hackathon"] = self.request.GET.get("hackathon", "")
        return context


class SponsorDetailView(SponsorPermissionRequiredMixin, DetailView):
    """Fiche détaillée d'un sponsor avec l'historique complet de ses partenariats."""

    model = Sponsor
    template_name = "sponsors/sponsor_detail.html"
    context_object_name = "sponsor"
    required_permission = "view_confidential"

    def get_queryset(self):
        return sponsors_visible_to(self.request.user)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["sponsorships"] = (
            sponsorships_visible_to(self.request.user)
            .filter(sponsor=self.object)
            .select_related("hackathon")
            .prefetch_related("history")
            .order_by("-created_at")
        )
        context["email_logs"] = (
            self.object.email_logs.select_related("sent_by").order_by("-sent_at")[:10]
        )
        return context


class SponsorCreateView(SponsorPermissionRequiredMixin, CreateView):
    """Création d'un nouveau profil d'entreprise sponsor."""

    model = Sponsor
    form_class = SponsorForm
    template_name = "sponsors/sponsor_form.html"
    required_permission = "manage"

    def form_valid(self, form):
        messages.success(self.request, f'Sponsor "{form.instance.name}" was created successfully.')
        return super().form_valid(form)

    def get_success_url(self):
        return reverse("sponsors:sponsor_detail", kwargs={"pk": self.object.pk})


class SponsorUpdateView(SponsorPermissionRequiredMixin, UpdateView):
    """Modification d'un sponsor existant."""

    model = Sponsor
    form_class = SponsorForm
    template_name = "sponsors/sponsor_form.html"
    required_permission = "manage"

    def get_queryset(self):
        return sponsors_visible_to(self.request.user)

    def form_valid(self, form):
        messages.success(self.request, f'Sponsor "{form.instance.name}" was updated.')
        return super().form_valid(form)

    def get_success_url(self):
        return reverse("sponsors:sponsor_detail", kwargs={"pk": self.object.pk})


class SponsorDeleteView(SponsorPermissionRequiredMixin, DeleteView):
    """Suppression d'un sponsor et de ses partenariats associés."""

    model = Sponsor
    template_name = "sponsors/confirm_delete.html"
    success_url = reverse_lazy("sponsors:sponsor_list")
    required_permission = "delete"

    def get_queryset(self):
        return sponsors_visible_to(self.request.user)

    def get_object(self, queryset=None):
        sponsor = super().get_object(queryset)
        all_sponsorships = sponsor.sponsorships.all()
        visible_sponsorships = sponsorships_visible_to(self.request.user).filter(
            sponsor=sponsor
        )
        if all_sponsorships.count() != visible_sponsorships.count():
            raise Http404
        if any(
            not can_manage_sponsorship(self.request.user, sponsorship)
            for sponsorship in all_sponsorships
        ):
            raise Http404
        return sponsor

    def form_valid(self, form):
        messages.success(self.request, f'Sponsor "{self.object.name}" was deleted.')
        return super().form_valid(form)


# ==============================================================================
# GESTION DES PARTENARIATS / SPONSORSHIPS CRUD
# ==============================================================================

class SponsorshipCreateView(SponsorPermissionRequiredMixin, CreateView):
    """Création d'un accord de partenariat pour un hackathon."""

    model = Sponsorship
    form_class = SponsorshipForm
    template_name = "sponsors/sponsorship_form.html"
    required_permission = "manage"

    def get_initial(self):
        initial = super().get_initial()
        sponsor_id = self.request.GET.get("sponsor_id")
        hackathon_id = self.request.GET.get("hackathon_id")
        if sponsor_id:
            initial["sponsor"] = sponsor_id
        if hackathon_id:
            initial["hackathon"] = hackathon_id
        return initial

    def form_valid(self, form):
        response = super().form_valid(form)
        # Enregistrer le statut initial dans l'historique
        StatusHistory.objects.create(
            sponsorship=self.object,
            old_status="",
            new_status=self.object.status,
            changed_by=self.request.user,
        )
        messages.success(
            self.request,
            f'Sponsorship for "{self.object.sponsor.name}" was linked to hackathon "{self.object.hackathon.name}".'
        )
        return response

    def get_success_url(self):
        return reverse("sponsors:dashboard")


class SponsorshipUpdateView(SponsorPermissionRequiredMixin, UpdateView):
    """Modification des conditions d'un partenariat."""

    model = Sponsorship
    form_class = SponsorshipForm
    template_name = "sponsors/sponsorship_form.html"
    required_permission = "manage"

    def get_queryset(self):
        return sponsorships_visible_to(self.request.user)

    def get_object(self, queryset=None):
        obj = super().get_object(queryset)
        if not can_manage_sponsorship(self.request.user, obj):
            raise Http404
        return obj

    def form_valid(self, form):
        response = super().form_valid(form)
        messages.success(self.request, "Sponsorship details were saved.")
        return response

    def get_success_url(self):
        return reverse("sponsors:dashboard")


class SponsorshipDeleteView(SponsorPermissionRequiredMixin, DeleteView):
    """Suppression d'une convention de partenariat."""

    model = Sponsorship
    template_name = "sponsors/confirm_delete.html"
    success_url = reverse_lazy("sponsors:dashboard")
    required_permission = "delete"

    def get_queryset(self):
        return sponsorships_visible_to(self.request.user)

    def get_object(self, queryset=None):
        obj = super().get_object(queryset)
        if not can_manage_sponsorship(self.request.user, obj):
            raise Http404
        return obj

    def form_valid(self, form):
        messages.success(self.request, "The sponsorship was removed.")
        return super().form_valid(form)


# ==============================================================================
# ACTION RAPIDE DE CHANGEMENT DE STATUT (Support HTMX)
# ==============================================================================

class SponsorshipChangeStatusView(SponsorPermissionRequiredMixin, View):
    """
    Met à jour le statut d'un partenariat et trace l'opération dans StatusHistory.
    Compatible avec requêtes standards et HTMX.
    """
    required_permission = "manage"

    def post(self, request, pk):
        sponsorship = get_object_or_404(
            sponsorships_visible_to(request.user),
            pk=pk,
        )
        if not can_manage_sponsorship(request.user, sponsorship):
            return self.handle_no_permission()
        new_status = request.POST.get("status")

        if new_status in dict(StatusChoices.choices):
            sponsorship.change_status(new_status=new_status, changed_by=request.user)
            messages.success(
                request,
                f'Status updated: {sponsorship.sponsor.name} is now "{sponsorship.get_status_display()}".'
            )

        # Si requête HTMX, on renvoie le snippet mis à jour
        if request.headers.get("HX-Request"):
            return render(
                request,
                "sponsors/partials/sponsorship_row.html",
                {
                    "item": sponsorship,
                    "status_choices": StatusChoices.choices,
                },
            )

        # Redirection classique
        next_url = request.POST.get("next") or reverse("sponsors:dashboard")
        return HttpResponseRedirect(next_url)


# ==============================================================================
# ENVOI D'EMAIL AU CONTACT D'UN SPONSOR (Étape 7 - Staff Only)
# ==============================================================================

class SponsorContactView(SponsorPermissionRequiredMixin, View):
    """
    Vue d'envoi d'email au contact du sponsor (Staff only).
    Permet à l'organisateur de choisir un modèle prérempli (invitation, relance, remerciement),
    d'ajuster le sujet et le message, puis de valider l'envoi.
    Le destinataire est STRICTEMENT sponsor.contact_email (non modifiable).
    """

    template_name = "sponsors/sponsor_contact.html"
    required_permission = "contact"

    def get(self, request, pk):
        sponsor = get_object_or_404(sponsors_visible_to(request.user), pk=pk)
        template_key = request.GET.get("template_key", "invitation")
        hackathon_id = request.GET.get("hackathon")
        hackathon = None
        if hackathon_id and Hackathon:
            hackathon = Hackathon.objects.filter(pk=hackathon_id).first()

        composed = compose_email(sponsor=sponsor, hackathon=hackathon, template_key=template_key)
        form = SponsorContactForm(initial={
            "template_key": template_key,
            "subject": composed["subject"],
            "message": composed["body"],
        })

        if getattr(request, "htmx", False) or request.headers.get("HX-Request"):
            return render(
                request,
                "sponsors/partials/sponsor_contact_form.html",
                {
                    "form": form,
                    "sponsor": sponsor,
                    "template_key": template_key,
                },
            )

        return render(
            request,
            self.template_name,
            {
                "form": form,
                "sponsor": sponsor,
                "template_key": template_key,
            },
        )

    def post(self, request, pk):
        sponsor = get_object_or_404(sponsors_visible_to(request.user), pk=pk)
        form = SponsorContactForm(request.POST)

        if form.is_valid():
            subject = form.cleaned_data["subject"]
            message = form.cleaned_data["message"]
            ai_generated = form.cleaned_data.get("ai_generated", False)

            log, success = send_sponsor_contact_email(
                sponsor=sponsor,
                sent_by=request.user,
                subject=subject,
                body=message,
                ai_generated=ai_generated,
            )

            if success:
                messages.success(
                    request,
                    f'Email sent successfully to "{sponsor.name}" ({sponsor.contact_email}).'
                )
                return redirect("sponsors:sponsor_detail", pk=sponsor.pk)
            else:
                messages.error(
                    request,
                    f"Unable to send email: {log.error_message}"
                )

        return render(
            request,
            self.template_name,
            {
                "form": form,
                "sponsor": sponsor,
            },
        )


# ==============================================================================
# FONCTIONNALITÉS IA SPONSORS (Étape 8 - Staff Only)
# ==============================================================================

class SponsorAIGenerateEmailView(SponsorPermissionRequiredMixin, View):
    """
    required_permission = "contact"
    Action HTMX : Génération assistée par IA d'un email de prospection personnalisé.
    Données sécurisées (aucun montant, contact ni note transmis).
    Injecte le résultat dans le formulaire pour relecture et édition avant envoi.
    """

    def post(self, request, pk):
        sponsor = get_object_or_404(sponsors_visible_to(request.user), pk=pk)
        template_key = request.POST.get("template_key", "invitation")
        tone = request.POST.get("tone", "professionnel")
        hackathon_id = request.POST.get("hackathon")
        hackathon = None
        if hackathon_id and Hackathon:
            hackathon = Hackathon.objects.filter(pk=hackathon_id).first()

        result = generate_prospecting_email(
            sponsor=sponsor,
            hackathon=hackathon,
            tone=tone,
            template_key=template_key,
            user=request.user,
        )

        form = SponsorContactForm(initial={
            "template_key": template_key,
            "tone": tone,
            "subject": result["subject"],
            "message": result["body"],
            "ai_generated": result.get("ai_generated", False),
        })

        return render(
            request,
            "sponsors/partials/sponsor_contact_form.html",
            {
                "form": form,
                "sponsor": sponsor,
                "ai_notice": result.get("notice"),
                "ai_generated": result.get("ai_generated", False),
            },
        )


class SponsorRecommendationsView(SponsorPermissionRequiredMixin, View):
    """
    required_permission = "view_confidential"
    Endpoint HTMX / Staff retournant les recommandations vectorielles (TF-IDF)
    pour un hackathon sélectionné.
    """

    def get(self, request, hackathon_id):
        hackathon = get_object_or_404(Hackathon, pk=hackathon_id) if Hackathon else None
        data = recommend_sponsors_for_hackathon(
            hackathon,
            top_n=5,
            user=request.user,
        )
        return render(
            request,
            "sponsors/partials/recommendations_block.html",
            {
                "target_hackathon": hackathon,
                "ai_recommendations": data.get("recommendations", []),
                "ai_recommendations_message": data.get("message", ""),
            },
        )


# ==============================================================================
# EXPORT EXCEL DES PARTENARIATS (Étape 6 - Staff Only, openpyxl)
# ==============================================================================

class SponsorshipExportExcelView(SponsorPermissionRequiredMixin, View):
    """
    required_permission = "export"
    Export Excel (.xlsx) complet des partenariats (Staff only, GET uniquement).
    Respecte les filtres actifs, génère 2 feuilles (Détail + Synthèse analytique)
    et applique la protection contre l'injection de formules.
    """

    def get(self, request):
        queryset = filter_sponsorships_queryset(request.GET, request.user)

        try:
            excel_buffer = export_sponsorships_to_excel(queryset)
        except ValueError as exc:
            messages.error(request, str(exc))
            return redirect("sponsors:sponsor_list")
        except RuntimeError as exc:
            messages.error(request, str(exc))
            return redirect("sponsors:sponsor_list")

        date_str = timezone.now().strftime("%Y-%m-%d")
        filename = f"hackflow_sponsors_{date_str}.xlsx"

        response = HttpResponse(
            excel_buffer.getvalue(),
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        response["Content-Disposition"] = f'attachment; filename="{filename}"'
        return response
