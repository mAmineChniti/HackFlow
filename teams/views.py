from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.core.exceptions import PermissionDenied
from django.db.models import Count, Q
from django.http import Http404, HttpResponseRedirect, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse, reverse_lazy
from django.views.decorators.http import require_POST
from django.views.generic import CreateView, DeleteView, DetailView, ListView, UpdateView

from . import ai, services
from .forms import JoinTeamForm, SkillProfileForm, TeamForm
from .models import Hackathon, Invitation, SkillProfile, Team


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
        messages.success(self.request, "Team created successfully.")
        return HttpResponseRedirect(reverse("teams:detail", args=[self.object.pk]))


class TeamUpdateView(LoginRequiredMixin, LeaderRequiredMixin, UpdateView):
    model = Team
    form_class = TeamForm

    def form_valid(self, form):
        messages.success(self.request, "Team updated successfully.")
        return super().form_valid(form)

    def get_success_url(self):
        return reverse("teams:detail", args=[self.object.pk])


class TeamDeleteView(LoginRequiredMixin, LeaderRequiredMixin, DeleteView):
    model = Team
    success_url = reverse_lazy("teams:list")

    def form_valid(self, form):
        messages.success(self.request, "Team deleted successfully.")
        return super().form_valid(form)


@login_required
@require_POST
def join_team(request, pk):
    team = get_object_or_404(Team, pk=pk)
    form = JoinTeamForm(request.POST)
    if form.is_valid():
        try:
            services.join_team(team=team, user=request.user, **form.cleaned_data)
            messages.success(request, "You have joined the team.")
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
        messages.success(request, "You have left the team.")
    except services.TeamError as exc:
        messages.error(request, str(exc))
    return redirect("teams:detail", pk=pk)


class SkillProfileUpdateView(LoginRequiredMixin, UpdateView):
    model = SkillProfile
    form_class = SkillProfileForm
    success_url = reverse_lazy("teams:skills")

    def get_object(self, queryset=None):
        profile, _ = SkillProfile.objects.get_or_create(user=self.request.user)
        return profile

    def form_valid(self, form):
        messages.success(self.request, "Compétences enregistrées.")
        return super().form_valid(form)


@login_required
@require_POST
def suggest_teammates(request, pk):
    team = get_object_or_404(Team.objects.select_related("hackathon"), pk=pk)
    if team.leader_id != request.user.pk:
        return JsonResponse({"error": "Réservé au chef d'équipe."}, status=403)
    if team.is_full:
        return JsonResponse({"error": "L'équipe est déjà complète."}, status=400)
    return JsonResponse(ai.build_report(team))


# ------------------------------------------------------------ Invitations
def _is_ajax(request):
    return request.headers.get("x-requested-with") == "XMLHttpRequest"


@login_required
@require_POST
def send_invitation(request, pk):
    team = get_object_or_404(Team, pk=pk)
    ajax = _is_ajax(request)

    if team.leader_id != request.user.pk:
        if ajax:
            return JsonResponse({"error": "Réservé au chef d'équipe."}, status=403)
        raise PermissionDenied

    User = get_user_model()
    user_id = request.POST.get("user_id", "").strip()
    username = request.POST.get("username", "").strip()
    invitee = None
    if user_id.isdigit():
        invitee = User.objects.filter(pk=int(user_id)).first()
    elif username:
        invitee = User.objects.filter(username__iexact=username).first()

    try:
        if invitee is None:
            raise services.TeamError("Utilisateur introuvable.")
        services.invite_user(
            team=team,
            invited_by=request.user,
            invitee=invitee,
            message=request.POST.get("message", "").strip(),
        )
    except services.TeamError as exc:
        if ajax:
            return JsonResponse({"error": str(exc)}, status=400)
        messages.error(request, str(exc))
    else:
        text = f"Invitation envoyée à {invitee.username}."
        if ajax:
            return JsonResponse({"ok": True, "message": text})
        messages.success(request, text)
    return redirect("teams:detail", pk=team.pk)


@login_required
def my_invitations(request):
    received = Invitation.objects.filter(invitee=request.user).select_related(
        "team", "team__hackathon", "invited_by"
    )
    sent = Invitation.objects.filter(team__leader=request.user).select_related("team", "invitee")
    pending = Invitation.Status.PENDING
    return render(
        request,
        "teams/my_invitations.html",
        {
            "received_pending": received.filter(status=pending),
            "received_history": received.exclude(status=pending)[:10],
            "sent_pending": sent.filter(status=pending),
        },
    )


@login_required
@require_POST
def respond_invitation(request, pk, action):
    invitation = get_object_or_404(Invitation.objects.select_related("team"), pk=pk)
    if request.user.pk not in (invitation.invitee_id, invitation.team.leader_id):
        raise Http404
    handlers = {
        "accept": (services.accept_invitation, "Invitation accepted: welcome to the team!"),
        "decline": (services.decline_invitation, "Invitation declined."),
        "cancel": (services.cancel_invitation, "Invitation cancelled."),
    }
    if action not in handlers:
        raise Http404
    handler, success = handlers[action]
    try:
        invitation = handler(invitation=invitation, user=request.user)
    except services.TeamError as exc:
        messages.error(request, str(exc))
    else:
        messages.success(request, success)
        if action == "accept":
            return redirect("teams:detail", pk=invitation.team_id)
    return redirect("teams:my_invitations")
