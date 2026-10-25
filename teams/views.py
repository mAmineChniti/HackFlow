from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.db.models import Count, Q
from django.http import HttpResponseRedirect
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse, reverse_lazy
from django.views.decorators.http import require_POST
from django.views.generic import CreateView, DeleteView, DetailView, ListView, UpdateView

from . import services
from .forms import JoinTeamForm, TeamForm
from .models import Hackathon, Team


class LeaderRequiredMixin(UserPassesTestMixin):
    """Seul le chef d'équipe passe. Un utilisateur connecté refusé reçoit une 403."""

    def test_func(self):
        return self.get_object().leader_id == self.request.user.pk


class TeamListView(ListView):
    model = Team
    paginate_by = 9

    def get_queryset(self):
                qs = (
            Team.objects.select_related("hackathon", "leader")
            .annotate(member_count=Count("members"))
            .order_by("-created_at")
        )
        q = self.request.GET.get("q", "").strip()
        hackathon = self.request.GET.get("hackathon", "").strip()
        if q:
            qs = qs.filter(Q(name__icontains=q) | Q(description__icontains=q))
        if hackathon.isdigit():
            qs = qs.filter(hackathon_id=hackathon)
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["hackathons"] = Hackathon.objects.all()
        ctx["q"] = self.request.GET.get("q", "")
        ctx["selected_hackathon"] = self.request.GET.get("hackathon", "")
        return ctx


class TeamDetailView(DetailView):
    model = Team

    def get_queryset(self):
        return Team.objects.select_related("hackathon", "leader")

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        team = self.object
        user = self.request.user
        members = team.members.select_related("user")
        ctx["members"] = members
        ctx["is_leader"] = user.is_authenticated and team.leader_id == user.pk
        ctx["is_member"] = user.is_authenticated and members.filter(user=user).exists()
        ctx["join_form"] = JoinTeamForm()
        return ctx


class TeamCreateView(LoginRequiredMixin, CreateView):
    model = Team
    form_class = TeamForm

    def form_valid(self, form):
        try:
            self.object = services.create_team(leader=self.request.user, **form.cleaned_data)
        except services.TeamError as exc:
            form.add_error(None, str(exc))
            return self.form_invalid(form)
        messages.success(self.request, "Équipe créée avec succès.")
        return HttpResponseRedirect(reverse("teams:detail", args=[self.object.pk]))


class TeamUpdateView(LoginRequiredMixin, LeaderRequiredMixin, UpdateView):
    model = Team
    form_class = TeamForm

    def form_valid(self, form):
        messages.success(self.request, "Équipe mise à jour.")
        return super().form_valid(form)

    def get_success_url(self):
        return reverse("teams:detail", args=[self.object.pk])


class TeamDeleteView(LoginRequiredMixin, LeaderRequiredMixin, DeleteView):
    model = Team
    success_url = reverse_lazy("teams:list")

    def form_valid(self, form):
        messages.success(self.request, "Équipe supprimée.")
        return super().form_valid(form)


@login_required
@require_POST
def join_team(request, pk):
    team = get_object_or_404(Team, pk=pk)
    form = JoinTeamForm(request.POST)
    if form.is_valid():
        try:
            services.join_team(team=team, user=request.user, **form.cleaned_data)
            messages.success(request, "Vous avez rejoint l'équipe.")
        except services.TeamError as exc:
            messages.error(request, str(exc))
    else:
        messages.error(request, "Formulaire invalide.")
    return redirect("teams:detail", pk=pk)


@login_required
@require_POST
def leave_team(request, pk):
    team = get_object_or_404(Team, pk=pk)
    try:
        services.leave_team(team=team, user=request.user)
        messages.success(request, "Vous avez quitté l'équipe.")
    except services.TeamError as exc:
        messages.error(request, str(exc))
    return redirect("teams:detail", pk=pk)