from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.core.exceptions import PermissionDenied
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse_lazy
from django.utils import timezone
from django.views.generic import (
    CreateView,
    DeleteView,
    DetailView,
    ListView,
    UpdateView,
)

from .forms import HackathonForm, RegistrationForm, ScheduleForm
from .models import Hackathon, HackathonRegistration, HackathonSchedule


class HackathonListView(ListView):
    model = Hackathon
    template_name = "hackathons/list.html"
    context_object_name = "hackathons"
    paginate_by = 9

    def get_queryset(self):
        qs = Hackathon.objects.filter(is_published=True).select_related("organizer").annotate(
            total_registered=Count("registrations")
        )

        query = self.request.GET.get("q", "").strip()
        if query:
            qs = qs.filter(
                Q(title__icontains=query)
                | Q(tagline__icontains=query)
                | Q(category__icontains=query)
                | Q(description__icontains=query)
            )

        status = self.request.GET.get("status", "").strip()
        if status:
            qs = qs.filter(status=status)

        mode = self.request.GET.get("mode", "").strip()
        if mode:
            qs = qs.filter(mode=mode)

        category = self.request.GET.get("category", "").strip()
        if category:
            qs = qs.filter(category__iexact=category)

        ordering = self.request.GET.get("ordering", "start_date")
        if ordering == "newest":
            qs = qs.order_by("-created_at")
        elif ordering == "popular":
            qs = qs.order_by("-total_registered")
        else:
            qs = qs.order_by("start_date")

        return qs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["selected_status"] = self.request.GET.get("status", "")
        context["selected_mode"] = self.request.GET.get("mode", "")
        context["selected_category"] = self.request.GET.get("category", "")
        context["search_query"] = self.request.GET.get("q", "")
        context["status_choices"] = Hackathon.Status.choices
        context["mode_choices"] = Hackathon.Mode.choices
        context["categories"] = (
            Hackathon.objects.filter(is_published=True)
            .values_list("category", flat=True)
            .distinct()
        )
        return context

    def render_to_response(self, context, **response_kwargs):
        # Support HTMX dynamic live search and filtering!
        if self.request.headers.get("HX-Request"):
            return render(
                self.request,
                "hackathons/partials/_hackathon_grid.html",
                context,
            )
        return super().render_to_response(context, **response_kwargs)


class HackathonDetailView(DetailView):
    model = Hackathon
    template_name = "hackathons/detail.html"
    context_object_name = "hackathon"
    slug_url_kwarg = "slug"

    def get_queryset(self):
        # Allow organizer or superuser to view unpublished hackathons
        user = self.request.user
        if user.is_authenticated and (user.is_superuser or user.is_staff):
            return Hackathon.objects.all()
        if user.is_authenticated:
            return Hackathon.objects.filter(
                Q(is_published=True) | Q(organizer=user)
            )
        return Hackathon.objects.filter(is_published=True)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        hackathon = self.object
        context["schedule_items"] = hackathon.schedule_items.all().order_by("scheduled_at")
        context["faqs"] = hackathon.faqs.all().order_by("order")
        context["registration_form"] = RegistrationForm()
        context["now"] = timezone.now()

        # Check if current user is registered
        is_registered = False
        user_registration = None
        if self.request.user.is_authenticated:
            user_registration = HackathonRegistration.objects.filter(
                hackathon=hackathon, participant=self.request.user
            ).first()
            is_registered = user_registration is not None

        context["is_registered"] = is_registered
        context["user_registration"] = user_registration
        context["is_organizer"] = (
            self.request.user.is_authenticated
            and (self.request.user == hackathon.organizer or self.request.user.is_superuser)
        )
        return context


class HackathonCreateView(LoginRequiredMixin, CreateView):
    model = Hackathon
    form_class = HackathonForm
    template_name = "hackathons/form.html"

    def form_valid(self, form):
        form.instance.organizer = self.request.user
        response = super().form_valid(form)
        messages.success(
            self.request,
            f"Le hackathon '{self.object.title}' a été créé avec succès !",
        )
        return response

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["page_title"] = "Créer un Hackathon"
        context["action_label"] = "Publier l'événement"
        return context


class HackathonUpdateView(LoginRequiredMixin, UserPassesTestMixin, UpdateView):
    model = Hackathon
    form_class = HackathonForm
    template_name = "hackathons/form.html"
    slug_url_kwarg = "slug"

    def test_func(self):
        hackathon = self.get_object()
        return self.request.user == hackathon.organizer or self.request.user.is_superuser

    def form_valid(self, form):
        response = super().form_valid(form)
        messages.success(
            self.request,
            f"Les informations du hackathon '{self.object.title}' ont été mises à jour.",
        )
        return response

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["page_title"] = f"Modifier : {self.object.title}"
        context["action_label"] = "Enregistrer les modifications"
        context["is_edit"] = True
        return context


class HackathonDeleteView(LoginRequiredMixin, UserPassesTestMixin, DeleteView):
    model = Hackathon
    template_name = "hackathons/confirm_delete.html"
    slug_url_kwarg = "slug"
    success_url = reverse_lazy("hackathons:list")

    def test_func(self):
        hackathon = self.get_object()
        return self.request.user == hackathon.organizer or self.request.user.is_superuser

    def delete(self, request, *args, **kwargs):
        hackathon = self.get_object()
        title = hackathon.title
        messages.info(request, f"Le hackathon '{title}' a été supprimé.")
        return super().delete(request, *args, **kwargs)


@login_required
def register_participant(request, slug):
    """Register the authenticated user for the hackathon."""
    hackathon = get_object_or_404(Hackathon, slug=slug)

    if not hackathon.is_registration_open:
        messages.error(request, "Les inscriptions pour ce hackathon sont actuellement fermées.")
        return redirect("hackathons:detail", slug=slug)

    if HackathonRegistration.objects.filter(hackathon=hackathon, participant=request.user).exists():
        messages.info(request, "Vous êtes déjà inscrit(e) à ce hackathon.")
        return redirect("hackathons:detail", slug=slug)

    if hackathon.registered_count >= hackathon.max_participants:
        messages.error(request, "Désolé, la capacité maximale de participants est atteinte.")
        return redirect("hackathons:detail", slug=slug)

    if request.method == "POST":
        form = RegistrationForm(request.POST)
        if form.is_valid():
            reg = form.save(commit=False)
            reg.hackathon = hackathon
            reg.participant = request.user
            reg.save()
            messages.success(
                request,
                f"Félicitations ! Vous êtes bien inscrit(e) à {hackathon.title}.",
            )
            return redirect("hackathons:detail", slug=slug)
    else:
        form = RegistrationForm()

    return render(
        request,
        "hackathons/register.html",
        {"hackathon": hackathon, "form": form},
    )


@login_required
def unregister_participant(request, slug):
    """Unregister the authenticated user from the hackathon."""
    if request.method == "POST":
        hackathon = get_object_or_404(Hackathon, slug=slug)
        reg = HackathonRegistration.objects.filter(
            hackathon=hackathon, participant=request.user
        ).first()

        if reg:
            reg.delete()
            messages.info(request, f"Votre inscription à {hackathon.title} a été annulée.")
        else:
            messages.warning(request, "Vous n'étiez pas inscrit(e) à cet événement.")

    return redirect("hackathons:detail", slug=slug)


@login_required
def organizer_dashboard(request):
    """Dashboard for organizers to manage their hackathons and see participant registrations."""
    hackathons = (
        Hackathon.objects.filter(organizer=request.user)
        .annotate(total_registered=Count("registrations"))
        .order_by("-created_at")
    )
    return render(
        request,
        "hackathons/dashboard.html",
        {"hackathons": hackathons},
    )
