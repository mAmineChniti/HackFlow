import json
import logging
import re

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.core.exceptions import PermissionDenied
from django.db.models import Count, Max, Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse, reverse_lazy
from django.utils import timezone
from django.views.decorators.http import require_POST
from django.views.generic import CreateView, DeleteView, DetailView, ListView, UpdateView

from core.groq import call_groq, is_configured
from projects.services import is_admin, is_organizer

from . import services
from .forms import ChallengeForm, ChallengeQuestionForm, ChallengeSubmissionForm
from .models import Challenge, ChallengeQuestion, ChallengeSubmission, ChallengeAnswer

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
            ).prefetch_related("answers__question").first()
        context["submission"] = submission
        context["questions"] = challenge.questions.all().order_by("order", "id")
        context["submission_form"] = ChallengeSubmissionForm(challenge=challenge)
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
        form = ChallengeSubmissionForm(request.POST, challenge=challenge)
        if form.is_valid():
            submission = existing
            if not submission:
                submission = ChallengeSubmission(challenge=challenge, participant=request.user)
                submission.attempt_count = 1
            else:
                submission.attempt_count += 1
                submission.submitted_at = timezone.now()

            total_points = 0
            max_points = sum(q.points for q in challenge.questions.all())
            all_correct = True

            for question in challenge.questions.all().order_by("order", "id"):
                field_name = f"question_{question.id}"
                user_answer = form.cleaned_data.get(field_name, "").strip()
                correct_answer = question.correct_answer.strip()

                is_correct = False
                if question.answer_type == ChallengeQuestion.AnswerType.NUMBER:
                    try:
                        is_correct = float(user_answer) == float(correct_answer)
                    except (ValueError, TypeError):
                        is_correct = False
                else:
                    is_correct = user_answer.lower() == correct_answer.lower()

                points_earned = question.points if is_correct else 0
                total_points += points_earned

                if not is_correct:
                    all_correct = False

                ChallengeAnswer.objects.update_or_create(
                    submission=submission,
                    question=question,
                    defaults={
                        "answer_text": user_answer,
                        "is_correct": is_correct,
                        "points_earned": points_earned,
                    },
                )

            submission.status = (
                ChallengeSubmission.Status.PASSED if all_correct else ChallengeSubmission.Status.FAILED
            )
            submission.score = int((total_points / max_points * 100)) if max_points > 0 else 0
            submission.save()

            if all_correct:
                messages.success(request, "All answers correct! Challenge passed.")
            else:
                messages.warning(
                    request, f"Submission saved. Score: {submission.score}/100. Try again for full points."
                )
            return redirect("challenges:detail", slug=slug)
    else:
        form = ChallengeSubmissionForm(challenge=challenge)

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


ANSWER_TYPE_HINTS = {
    ChallengeQuestion.AnswerType.FLAG: (
        "The answer is a flag in the format flag{...}. Re-read the challenge "
        "details and look for where the flag is exposed."
    ),
    ChallengeQuestion.AnswerType.NUMBER: (
        "The answer is a number. Work through the data step by step and "
        "double-check your calculation before submitting."
    ),
    ChallengeQuestion.AnswerType.TEXT: (
        "The answer is a short piece of text. Look for the key term the "
        "question and challenge description point to."
    ),
}


def _hint_reveals_answer(hint, answer):
    """Return True when a generated hint contains the organizer's answer."""
    normalized_answer = " ".join(answer.lower().split())
    if not normalized_answer:
        return False

    candidates = {normalized_answer}
    flag_match = re.fullmatch(r"flag\{(.+)\}", normalized_answer)
    if flag_match:
        candidates.add(flag_match.group(1).strip())

    normalized_hint = " ".join(hint.lower().split())
    for candidate in candidates:
        if not candidate:
            continue
        pattern = rf"(?<!\w){re.escape(candidate)}(?!\w)"
        if re.search(pattern, normalized_hint):
            return True
    return False


def _build_question_hint(challenge, question, participant_answer):
    """Return a per-question hint, preferring the organizer's own hint."""
    organizer_hint = question.hint.strip()
    if organizer_hint:
        return organizer_hint

    fallback = ANSWER_TYPE_HINTS.get(
        question.answer_type,
        "Re-read the question and the challenge description before trying again.",
    )

    system_prompt = (
        "You are a mentor for a CTF-style challenge platform. Give one short, "
        "non-spoiler hint (two sentences maximum) that nudges the participant "
        "toward the answer. Never reveal, quote, spell out, or partially "
        "disclose the reference answer, including inside examples. Match the "
        "expected answer type without exposing the value."
    )
    prompt = (
        f"Challenge: {challenge.title}\n"
        f"Category: {challenge.category}\n"
        f"Difficulty: {challenge.get_difficulty_display()}\n"
        f"Description:\n{challenge.description[:1500]}\n\n"
        f"Question: {question.question_text}\n"
        f"Answer type: {question.get_answer_type_display()} "
        f"({question.points} points)\n"
        f"Reference answer (organizer only, never reveal): {question.correct_answer}\n"
    )
    if participant_answer:
        prompt += f"Participant's current attempt: {participant_answer}\n"
    prompt += "Write the hint now."

    hint = call_groq(prompt, system_prompt=system_prompt, max_tokens=200)
    if hint:
        hint = hint.strip().strip('"').strip()
        if hint and not _hint_reveals_answer(hint, question.correct_answer):
            return hint
    return fallback


@require_POST
@login_required
def question_hint_view(request, slug, question_id):
    challenge = get_object_or_404(Challenge, slug=slug)
    question = get_object_or_404(ChallengeQuestion, pk=question_id, challenge=challenge)
    if not services.can_submit_challenge(request.user, challenge):
        return JsonResponse(
            {"success": False, "error": "You cannot request hints for this challenge."},
            status=403,
        )

    participant_answer = ""
    try:
        payload = json.loads(request.body.decode("utf-8")) if request.body else {}
        if isinstance(payload, dict):
            participant_answer = str(payload.get("answer") or "").strip()
    except (ValueError, json.JSONDecodeError):
        participant_answer = (request.POST.get("answer") or "").strip()
    participant_answer = participant_answer[:500]

    hint = _build_question_hint(challenge, question, participant_answer)

    # Only refresh hints on answers that already exist; asking for a hint must
    # not create a blank answer row before the participant has submitted.
    ChallengeAnswer.objects.filter(
        submission__challenge=challenge,
        submission__participant=request.user,
        question=question,
    ).update(last_hint=hint)

    return JsonResponse({"success": True, "hint": hint, "ai_configured": is_configured()})


@login_required
def question_create(request, slug):
    challenge = get_object_or_404(Challenge, slug=slug)
    if not services.can_edit_challenge(request.user, challenge):
        messages.error(request, "You do not have permission to add questions to this challenge.")
        return redirect("challenges:detail", slug=slug)

    if request.method == "POST":
        form = ChallengeQuestionForm(request.POST)
        if form.is_valid():
            question = form.save(commit=False)
            question.challenge = challenge
            if question.order is None:
                max_order = challenge.questions.aggregate(Max("order"))["order__max"] or 0
                question.order = max_order + 1
            question.save()
            messages.success(request, "Question added successfully.")
            return redirect("challenges:detail", slug=slug)
    else:
        form = ChallengeQuestionForm()

    return render(
        request,
        "challenges/question_form.html",
        {"challenge": challenge, "form": form, "page_title": "Add Question"},
    )


@login_required
def question_edit(request, slug, question_id):
    challenge = get_object_or_404(Challenge, slug=slug)
    question = get_object_or_404(ChallengeQuestion, pk=question_id, challenge=challenge)
    if not services.can_edit_challenge(request.user, challenge):
        messages.error(request, "You do not have permission to edit this question.")
        return redirect("challenges:detail", slug=slug)

    if request.method == "POST":
        form = ChallengeQuestionForm(request.POST, instance=question)
        if form.is_valid():
            form.save()
            messages.success(request, "Question updated successfully.")
            return redirect("challenges:detail", slug=slug)
    else:
        form = ChallengeQuestionForm(instance=question)

    return render(
        request,
        "challenges/question_form.html",
        {"challenge": challenge, "question": question, "form": form, "page_title": "Edit Question"},
    )


@login_required
def question_delete(request, slug, question_id):
    challenge = get_object_or_404(Challenge, slug=slug)
    question = get_object_or_404(ChallengeQuestion, pk=question_id, challenge=challenge)
    if not services.can_edit_challenge(request.user, challenge):
        messages.error(request, "You do not have permission to delete this question.")
        return redirect("challenges:detail", slug=slug)

    if request.method == "POST":
        question.delete()
        messages.success(request, "Question deleted successfully.")
        return redirect("challenges:detail", slug=slug)

    return render(
        request,
        "challenges/question_confirm_delete.html",
        {"challenge": challenge, "question": question},
    )
