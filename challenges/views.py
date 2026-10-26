import json
import logging

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.core.exceptions import PermissionDenied
from django.db.models import Count, Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse, reverse_lazy
from django.utils import timezone
from django.views.decorators.http import require_POST
from django.views.generic import CreateView, DeleteView, DetailView, ListView, UpdateView

from core.groq import call_groq, is_configured
from projects.services import is_admin, is_organizer

from . import services
from .forms import ChallengeForm, ChallengeSubmissionForm
from .models import Challenge, ChallengeSubmission

logger = logging.getLogger(__name__)


class ChallengeListView(ListView):
    model = Challenge
    template_name = "challenges/list.html"
    context_object_name = "challenges"
    paginate_by = 12

    def get_queryset(self):
        qs = Challenge.objects.select_related("organizer", "hackathon")
        user = self.request.user
        if not (user.is_authenticated and (is_admin(user) or is_organizer(user))):
            qs = qs.filter(status=Challenge.Status.ACTIVE)
        query = self.request.GET.get("q", "").strip()
        if query:
            qs = qs.filter(
                Q(title__icontains=query)
                | Q(description__icontains=query)
                | Q(category__icontains=query)
            )
        difficulty = self.request.GET.get("difficulty", "").strip()
        if difficulty:
            qs = qs.filter(difficulty=difficulty)
        category = self.request.GET.get("category", "").strip()
        if category:
            qs = qs.filter(category__iexact=category)
        return qs.order_by("-created_at")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["search_query"] = self.request.GET.get("q", "")
        context["selected_difficulty"] = self.request.GET.get("difficulty", "")
        context["selected_category"] = self.request.GET.get("category", "")
        context["difficulty_choices"] = Challenge.Difficulty.choices
        context["categories"] = Challenge.objects.values_list("category", flat=True).distinct()
        return context


class ChallengeDetailView(DetailView):
    model = Challenge
    template_name = "challenges/detail.html"
    context_object_name = "challenge"
    slug_url_kwarg = "slug"

    def get_queryset(self):
        user = self.request.user
        qs = Challenge.objects.select_related("organizer", "hackathon")
        if not (user.is_authenticated and (is_admin(user) or is_organizer(user))):
            qs = qs.filter(status=Challenge.Status.ACTIVE)
        return qs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        challenge = self.object
        user = self.request.user
        submission = None
        if user.is_authenticated:
            submission = ChallengeSubmission.objects.filter(
                challenge=challenge, participant=user
            ).first()
        context["submission"] = submission
        context["submission_form"] = ChallengeSubmissionForm(instance=submission)
        context["solve_count"] = challenge.submissions.filter(
            status=ChallengeSubmission.Status.PASSED
        ).count()
        context["total_attempts"] = challenge.submissions.count()
        context["can_submit"] = user.is_authenticated and services.can_submit_challenge(
            user, challenge
        )
        context["is_organizer"] = user.is_authenticated and (
            is_admin(user) or (is_organizer(user) and challenge.organizer_id == user.id)
        )
        return context


class ChallengeCreateView(LoginRequiredMixin, UserPassesTestMixin, CreateView):
    model = Challenge
    form_class = ChallengeForm
    template_name = "challenges/form.html"

    def test_func(self):
        return is_admin(self.request.user) or is_organizer(self.request.user)

    def handle_no_permission(self):
        messages.error(self.request, "Only organizers and administrators can create challenges.")
        return redirect("challenges:list")

    def form_valid(self, form):
        form.instance.organizer = self.request.user
        messages.success(self.request, f"Challenge '{form.instance.title}' created.")
        return super().form_valid(form)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["page_title"] = "Create a Challenge"
        return context

    def get_success_url(self):
        return reverse("challenges:detail", kwargs={"slug": self.object.slug})


class ChallengeUpdateView(LoginRequiredMixin, UserPassesTestMixin, UpdateView):
    model = Challenge
    form_class = ChallengeForm
    template_name = "challenges/form.html"
    slug_url_kwarg = "slug"

    def test_func(self):
        challenge = self.get_object()
        return services.can_edit_challenge(self.request.user, challenge)

    def handle_no_permission(self):
        messages.error(self.request, "You do not have permission to edit this challenge.")
        return redirect("challenges:list")

    def form_valid(self, form):
        messages.success(self.request, f"Challenge '{form.instance.title}' updated.")
        return super().form_valid(form)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["page_title"] = f"Edit Challenge: {self.object.title}"
        return context

    def get_success_url(self):
        return reverse("challenges:detail", kwargs={"slug": self.object.slug})


class ChallengeDeleteView(LoginRequiredMixin, UserPassesTestMixin, DeleteView):
    model = Challenge
    template_name = "challenges/confirm_delete.html"
    slug_url_kwarg = "slug"
    success_url = reverse_lazy("challenges:list")

    def test_func(self):
        challenge = self.get_object()
        return services.can_delete_challenge(self.request.user, challenge)

    def delete(self, request, *args, **kwargs):
        challenge = self.get_object()
        messages.info(request, f"Challenge '{challenge.title}' deleted.")
        return super().delete(request, *args, **kwargs)


@login_required
def challenge_submit(request, slug):
    challenge = get_object_or_404(Challenge, slug=slug)
    if not services.can_submit_challenge(request.user, challenge):
        messages.error(request, "You cannot submit a solution to this challenge.")
        return redirect("challenges:detail", slug=slug)

    existing = ChallengeSubmission.objects.filter(
        challenge=challenge, participant=request.user
    ).first()

    if request.method == "POST":
        form = ChallengeSubmissionForm(request.POST, instance=existing)
        if form.is_valid():
            submission = form.save(commit=False)
            submission.challenge = challenge
            submission.participant = request.user
            if existing:
                submission.attempt_count = existing.attempt_count + 1
                submission.submitted_at = timezone.now()
            else:
                submission.attempt_count = 1
            solution_text = (submission.solution or "").strip()
            passed = len(solution_text) >= 40
            submission.status = (
                ChallengeSubmission.Status.PASSED if passed else ChallengeSubmission.Status.FAILED
            )
            submission.score = 100 if passed else 0
            submission.save()
            if passed:
                messages.success(request, "Solution submitted and marked as passed.")
            else:
                messages.warning(
                    request, "Solution submitted but needs more detail (min 40 chars)."
                )
            return redirect("challenges:detail", slug=slug)
    else:
        form = ChallengeSubmissionForm(instance=existing)

    return render(
        request,
        "challenges/submit.html",
        {"challenge": challenge, "form": form, "submission": existing},
    )


@require_POST
@login_required
def challenge_hint_view(request, slug):
    challenge = get_object_or_404(Challenge, slug=slug)
    solution = ""
    try:
        payload = json.loads(request.body.decode("utf-8")) if request.body else {}
        solution = (payload.get("solution") or "").strip()
    except (ValueError, json.JSONDecodeError):
        solution = (request.POST.get("solution") or "").strip()

    fallback = (
        f"Hint: re-read the challenge description carefully. "
        f"Break the problem into smaller steps and verify each one. "
        f"Difficulty is {challenge.get_difficulty_display()} ({challenge.points} pts)."
    )

    system_prompt = (
        "You are a helpful mentor for a coding challenge platform. "
        "Give a concise, non-spoiler hint (3-5 sentences) that guides the "
        "participant toward the solution without revealing the full answer. "
        "Do not include code that fully solves the challenge."
    )
    prompt = (
        f"Challenge: {challenge.title}\n"
        f"Category: {challenge.category}\n"
        f"Difficulty: {challenge.get_difficulty_display()}\n"
        f"Description:\n{challenge.description}\n\n"
    )
    if solution:
        prompt += f"Participant's current attempt:\n{solution}\n\n"
    prompt += "Provide a helpful hint."

    hint = call_groq(prompt, system_prompt=system_prompt, max_tokens=250)
    if not hint:
        hint = fallback

    sub = ChallengeSubmission.objects.filter(challenge=challenge, participant=request.user).first()
    if sub:
        sub.last_hint = hint
        sub.save(update_fields=["last_hint"])

    return JsonResponse({"success": True, "hint": hint, "ai_configured": is_configured()})
