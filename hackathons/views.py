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

import csv
import json
from django.http import HttpResponse, JsonResponse
from .ai import (
    calculate_team_match_score,
    generate_hackathon_content,
    generate_project_ideas,
)
from .badges import generate_badge_qr
from .emails import (
    check_and_notify_capacity_thresholds,
    send_organizer_new_registration_email,
    send_student_registration_email,
    send_waitlist_promoted_email,
)
from .forms import HackathonForm, RegistrationForm, ScheduleForm
from .models import Hackathon, HackathonRegistration, HackathonSchedule
from accounts.models import Profile
from projects.services import is_organizer, is_admin, is_student, is_judge, is_mentor


class HackathonListView(ListView):
    model = Hackathon
    template_name = "hackathons/list.html"
    context_object_name = "hackathons"
    paginate_by = 9

    def get_queryset(self):
        qs = (
            Hackathon.objects.filter(is_published=True)
            .select_related("organizer")
            .annotate(total_registered=Count("registrations"))
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
        context["selected_ordering"] = self.request.GET.get("ordering", "start_date")
        if context["selected_ordering"] not in {"start_date", "newest", "popular"}:
            context["selected_ordering"] = "start_date"
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
        user = self.request.user
        # Prefetch related objects to avoid N+1 queries
        qs = Hackathon.objects.select_related("organizer").prefetch_related(
            "judges", "mentors", "schedule_items", "faqs", "registrations"
        )

        if user.is_authenticated and (user.is_superuser or user.is_staff):
            return qs
        if user.is_authenticated:
            return qs.filter(
                Q(is_published=True) | Q(organizer=user) | Q(judges=user) | Q(mentors=user)
            ).distinct()
        return qs.filter(is_published=True)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        hackathon = self.object
        context["schedule_items"] = hackathon.schedule_items.all().order_by("scheduled_at")
        context["faqs"] = hackathon.faqs.all().order_by("order")
        context["registration_form"] = RegistrationForm()
        now = timezone.now()
        context["now"] = now

        context["is_registration_upcoming"] = hackathon.is_registration_upcoming
        context["is_registration_open"] = hackathon.is_registration_open
        context["is_registration_closed"] = hackathon.is_registration_closed
        context["is_full"] = hackathon.is_full
        is_deadline_passed = hackathon.is_registration_closed
        context["is_deadline_passed"] = is_deadline_passed

        is_registered = False
        user_registration = None
        if self.request.user.is_authenticated:
            user_registration = HackathonRegistration.objects.filter(
                hackathon=hackathon, participant=self.request.user
            ).first()
            is_registered = user_registration is not None

        context["is_registered"] = is_registered
        context["user_registration"] = user_registration
        context["can_unregister"] = is_registered and not is_deadline_passed
        context["is_organizer"] = self.request.user.is_authenticated and (
            self.request.user == hackathon.organizer or self.request.user.is_superuser
        )
        context["is_assigned_judge"] = (
            self.request.user.is_authenticated
            and hackathon.judges.filter(id=self.request.user.id).exists()
        )
        context["is_assigned_mentor"] = (
            self.request.user.is_authenticated
            and hackathon.mentors.filter(id=self.request.user.id).exists()
        )

        # AI Feature: Project Ideas & Inspiration based on the Hackathon
        ideas = generate_project_ideas(hackathon.title, hackathon.category, hackathon.description)
        context["project_ideas"] = ideas
        context["project_ideas_json"] = json.dumps(ideas)

        context["confirmed_registrations_count"] = hackathon.registrations.filter(
            status=HackathonRegistration.Status.CONFIRMED
        ).count()
        context["waitlist_registrations_count"] = hackathon.registrations.filter(
            status=HackathonRegistration.Status.WAITLIST
        ).count()

        # Organizer Check-in Desk metrics & registrations
        confirmed_count = context["confirmed_registrations_count"]
        checked_in_count = hackathon.registrations.filter(checked_in=True).count()
        context["checked_in_count"] = checked_in_count
        context["pending_checkin_count"] = max(confirmed_count - checked_in_count, 0)
        context["attendance_rate"] = int((checked_in_count / max(confirmed_count, 1)) * 100)

        if context["is_organizer"] or (
            self.request.user.is_authenticated and self.request.user.is_staff
        ):
            context["organizer_registrations"] = hackathon.registrations.select_related(
                "participant"
            ).order_by("-status", "checked_in", "participant__username")
        else:
            context["organizer_registrations"] = []

        # Student personal badge: ONLY generated if the student is actually registered
        if user_registration:
            context["badge_registration"] = user_registration
            context["badge_qr_b64"] = generate_badge_qr(self.request, user_registration)
        else:
            context["badge_registration"] = None
            context["badge_qr_b64"] = None

        return context


class HackathonCreateView(LoginRequiredMixin, UserPassesTestMixin, CreateView):
    model = Hackathon
    form_class = HackathonForm
    template_name = "hackathons/form.html"

    def test_func(self):
        user = self.request.user
        return user.is_superuser or is_organizer(user)

    def handle_no_permission(self):
        messages.error(
            self.request,
            "Access restricted: Only Organizers and Administrators can host hackathons. "
            f"You are currently signed in as a {getattr(self.request.user, 'profile', None) and self.request.user.profile.get_role_display() or 'Student'}.",
        )
        return redirect("hackathons:list")

    def form_valid(self, form):
        form.instance.organizer = self.request.user
        response = super().form_valid(form)
        # Promote selected judges to the Judge role (only organizers/admins can do this).
        for judge in form.instance.judges.all():
            profile, _ = Profile.objects.get_or_create(user=judge)
            if profile.role not in (Profile.Role.ADMIN, Profile.Role.ORGANIZER):
                profile.role = Profile.Role.JUDGE
                profile.save(update_fields=["role", "updated_at"])
        messages.success(
            self.request,
            f"Hackathon '{self.object.title}' has been successfully created!",
        )
        return response

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["page_title"] = "Create a Hackathon"
        context["action_label"] = "Publish Hackathon"
        return context


class HackathonUpdateView(LoginRequiredMixin, UserPassesTestMixin, UpdateView):
    model = Hackathon
    form_class = HackathonForm
    template_name = "hackathons/form.html"
    slug_url_kwarg = "slug"

    def test_func(self):
        hackathon = self.get_object()
        return self.request.user == hackathon.organizer or self.request.user.is_superuser

    def handle_no_permission(self):
        messages.error(
            self.request,
            "You do not have permission to edit this hackathon. Only the organizer or an administrator can modify it.",
        )
        return redirect("hackathons:list")

    def form_valid(self, form):
        response = super().form_valid(form)
        for judge in self.object.judges.all():
            profile, _ = Profile.objects.get_or_create(user=judge)
            if profile.role not in (Profile.Role.ADMIN, Profile.Role.ORGANIZER):
                profile.role = Profile.Role.JUDGE
                profile.save(update_fields=["role", "updated_at"])
        messages.success(
            self.request,
            f"Hackathon '{self.object.title}' details updated successfully.",
        )
        return response

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["page_title"] = f"Edit Hackathon: {self.object.title}"
        context["action_label"] = "Save Changes"
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
        messages.info(request, f"Hackathon '{title}' has been deleted.")
        return super().delete(request, *args, **kwargs)


@login_required
def register_participant(request, slug):
    hackathon = get_object_or_404(Hackathon, slug=slug)
    now = timezone.now()

    # 0. Role check: only students (or superusers) can register as participants
    if request.user == hackathon.organizer:
        messages.error(
            request,
            "As the organizer of this event, you cannot register as a participant.",
        )
        return redirect("hackathons:detail", slug=slug)

    if (
        hasattr(request.user, "profile")
        and not is_student(request.user)
        and not request.user.is_superuser
    ):
        messages.error(
            request,
            f"Registration as a participant is reserved for students. Your current role is {request.user.profile.get_role_display()}.",
        )
        return redirect("hackathons:detail", slug=slug)

    # 1. Registration not yet open
    if hackathon.registration_start and now < hackathon.registration_start:
        messages.info(
            request,
            f"Registration for '{hackathon.title}' is not open yet. It opens on {hackathon.registration_start.strftime('%b %d, %Y at %H:%M')}.",
        )
        return redirect("hackathons:detail", slug=slug)

    # 2. Registration deadline passed
    if hackathon.registration_deadline and now > hackathon.registration_deadline:
        messages.error(
            request,
            f"The registration deadline for '{hackathon.title}' passed on {hackathon.registration_deadline.strftime('%b %d, %Y at %H:%M')}.",
        )
        return redirect("hackathons:detail", slug=slug)

    # 3. Overall status check
    if hackathon.status != Hackathon.Status.REGISTRATION_OPEN:
        messages.error(request, "Registration is currently closed for this hackathon.")
        return redirect("hackathons:detail", slug=slug)

    # 4. Check if already registered
    existing_reg = HackathonRegistration.objects.filter(
        hackathon=hackathon, participant=request.user
    ).first()
    if existing_reg:
        messages.info(
            request,
            f"You are already registered for this hackathon (Status: {existing_reg.get_status_display()}).",
        )
        return redirect("hackathons:detail", slug=slug)

    # 5. Determine if registration is confirmed or waitlist
    is_full = hackathon.is_full
    target_status = (
        HackathonRegistration.Status.WAITLIST if is_full else HackathonRegistration.Status.CONFIRMED
    )

    if request.method == "POST":
        registration = HackathonRegistration(
            hackathon=hackathon,
            participant=request.user,
            status=target_status,
        )
        form = RegistrationForm(request.POST, instance=registration)
        if form.is_valid():
            prev_confirmed_count = hackathon.registered_count
            saved_reg = form.save(commit=False)
            saved_reg.hackathon = hackathon
            saved_reg.participant = request.user
            saved_reg.status = target_status
            saved_reg.save()
            form.save_m2m()

            # Registration emails disabled as requested
            # send_student_registration_email(saved_reg)
            # send_organizer_new_registration_email(saved_reg)

            if saved_reg.status == HackathonRegistration.Status.CONFIRMED:
                messages.success(
                    request,
                    f"Congratulations! Your registration for '{hackathon.title}' is confirmed.",
                )
            else:
                messages.warning(
                    request,
                    f"Maximum capacity reached. You have been placed on the priority waitlist for '{hackathon.title}'.",
                )

            return redirect("hackathons:detail", slug=slug)
    else:
        form = RegistrationForm()

    return render(
        request,
        "hackathons/register.html",
        {
            "hackathon": hackathon,
            "form": form,
            "is_full": is_full,
        },
    )


@login_required
def unregister_participant(request, slug):
    if request.method == "POST":
        hackathon = get_object_or_404(Hackathon, slug=slug)
        now = timezone.now()

        # Strict check: Student can unregister only BEFORE the deadline
        if hackathon.registration_deadline and now > hackathon.registration_deadline:
            messages.error(
                request,
                f"Cannot unregister: The deadline ({hackathon.registration_deadline.strftime('%b %d, %Y at %H:%M')}) has already passed.",
            )
            return redirect("hackathons:detail", slug=slug)

        reg = HackathonRegistration.objects.filter(
            hackathon=hackathon, participant=request.user
        ).first()

        if reg:
            was_confirmed = reg.status == HackathonRegistration.Status.CONFIRMED
            reg.delete()
            messages.info(
                request,
                f"Your registration for '{hackathon.title}' has been successfully cancelled.",
            )

            # If spot freed up, promote the first candidate on the waitlist
            if was_confirmed:
                promoted = (
                    HackathonRegistration.objects.filter(
                        hackathon=hackathon,
                        status=HackathonRegistration.Status.WAITLIST,
                    )
                    .order_by("registered_at")
                    .first()
                )
                if promoted:
                    promoted.status = HackathonRegistration.Status.CONFIRMED
                    promoted.save(update_fields=["status"])
                    # send_waitlist_promoted_email(promoted)
        else:
            messages.warning(request, "You were not registered for this event.")

    return redirect("hackathons:detail", slug=slug)


@login_required
def organizer_dashboard(request):
    user = request.user

    if user.is_superuser or is_admin(user):
        hackathons = (
            Hackathon.objects.all()
            .annotate(total_registered=Count("registrations"))
            .order_by("-created_at")
        )
        dashboard_title = "Admin Portal — All Platform Hackathons"
        user_role = "admin"
    elif is_judge(user):
        hackathons = (
            Hackathon.objects.filter(judges=user)
            .annotate(total_registered=Count("registrations"))
            .order_by("-created_at")
        )
        dashboard_title = "Judge Portal — Assigned Hackathons for Evaluation"
        user_role = "judge"
    elif is_mentor(user):
        hackathons = (
            Hackathon.objects.filter(mentors=user)
            .annotate(total_registered=Count("registrations"))
            .order_by("-created_at")
        )
        dashboard_title = "Mentor Portal — Assigned Hackathons for Mentoring"
        user_role = "mentor"
    elif is_organizer(user):
        hackathons = (
            Hackathon.objects.filter(organizer=user)
            .annotate(total_registered=Count("registrations"))
            .order_by("-created_at")
        )
        dashboard_title = "Organizer Dashboard — Hosted Hackathons"
        user_role = "organizer"
    else:  # Student
        hackathons = (
            Hackathon.objects.filter(registrations__participant=user)
            .annotate(total_registered=Count("registrations"))
            .order_by("-created_at")
        )
        dashboard_title = "Student Dashboard — My Registered Hackathons"
        user_role = "student"

    return render(
        request,
        "hackathons/dashboard.html",
        {
            "hackathons": hackathons,
            "dashboard_title": dashboard_title,
            "user_role": user_role,
        },
    )


@login_required
def ai_generate_hackathon(request):
    """
    AI Copilot endpoint: generates tagline, description, rules, and suggested skills
    for organizers creating or editing a hackathon.
    """
    if request.method != "POST":
        return JsonResponse({"error": "POST method required."}, status=405)

    user = request.user
    if not is_organizer(user):
        return JsonResponse({"error": "Only organizers can use the AI Assistant."}, status=403)

    try:
        if request.content_type == "application/json" and request.body:
            payload = json.loads(request.body.decode("utf-8"))
        else:
            payload = request.POST

        title = payload.get("title", "").strip()
        category = payload.get("category", "").strip()
        hints = payload.get("hints", "").strip()

        if not title:
            return JsonResponse({"error": "Please provide an event title first."}, status=400)

        result = generate_hackathon_content(title=title, category=category, theme_hints=hints)
        return JsonResponse({"success": True, "data": result})
    except Exception as exc:
        return JsonResponse({"error": str(exc)}, status=500)


@login_required
def export_participants_csv(request, slug):
    """
    High-value Organizer Tool: 1-click export of registered participants to CSV (Excel compatible).
    """
    hackathon = get_object_or_404(Hackathon, slug=slug)

    # Permission check: only host organizer or superuser
    if not (
        request.user == hackathon.organizer or request.user.is_superuser or request.user.is_staff
    ):
        messages.error(
            request, "Access restricted: Only the organizer can export participant lists."
        )
        return redirect("hackathons:detail", slug=slug)

    registrations = hackathon.registrations.select_related("participant").order_by(
        "-status", "registered_at"
    )

    response = HttpResponse(content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = f'attachment; filename="{hackathon.slug}-participants.csv"'

    # Write UTF-8 BOM so Microsoft Excel opens special characters and accents seamlessly
    response.write("\ufeff")

    writer = csv.writer(response)
    writer.writerow(
        [
            "Username",
            "Full Name",
            "Email",
            "Status",
            "University / School",
            "Study Level",
            "Experience Level",
            "Skills",
            "Looking for Team",
            "Portfolio URL",
            "Motivation",
            "Registration Date",
        ]
    )

    for reg in registrations:
        p = reg.participant
        writer.writerow(
            [
                p.username,
                p.get_full_name() or p.username,
                p.email,
                reg.get_status_display(),
                reg.university or "Not specified",
                reg.get_study_level_display(),
                reg.get_experience_level_display(),
                reg.skills or "",
                "Yes" if reg.seeking_team else "No",
                reg.portfolio_url or "",
                reg.motivation or "",
                reg.registered_at.strftime("%Y-%m-%d %H:%M"),
            ]
        )

    return response


def ai_generate_ideas(request, slug):
    """
    Dynamic endpoint: Generates fresh AI project blueprints tailored to this hackathon event.
    """
    hackathon = get_object_or_404(Hackathon, slug=slug)
    ideas = generate_project_ideas(hackathon.title, hackathon.category, hackathon.description)
    return JsonResponse({"success": True, "ideas": ideas})


@login_required
def participant_badge(request, slug):
    """
    Displays the official Digital Hackathon Participant Badge / Pass with secure QR Code.
    """
    hackathon = get_object_or_404(Hackathon, slug=slug)

    ticket_code = request.GET.get("ticket", "").strip()
    is_organizer = (
        request.user == hackathon.organizer or request.user.is_staff or request.user.is_superuser
    )

    if ticket_code and is_organizer:
        registration = get_object_or_404(
            HackathonRegistration, hackathon=hackathon, ticket_code=ticket_code
        )
    else:
        registration = HackathonRegistration.objects.filter(
            hackathon=hackathon, participant=request.user
        ).first()

    # If the user is not personally registered (e.g. organizer, admin, visitor), show the hackathon's attendee pass
    if not registration:
        registration = HackathonRegistration.objects.filter(hackathon=hackathon).first()

    if not registration:
        registration = HackathonRegistration(
            hackathon=hackathon,
            participant=request.user,
            ticket_code=f"HF-PASS-{hackathon.id}9C4E",
            status=HackathonRegistration.Status.CONFIRMED,
            university="ESPRIT",
            study_level=HackathonRegistration.StudyLevel.ING3,
            experience_level=HackathonRegistration.ExperienceLevel.ADVANCED,
        )

    qr_code_b64 = generate_badge_qr(request, registration)

    context = {
        "hackathon": hackathon,
        "registration": registration,
        "participant": registration.participant,
        "qr_code_b64": qr_code_b64,
        "is_organizer": is_organizer,
        "page_title": f"Official Participant Badge — {hackathon.title}",
    }
    return render(request, "hackathons/badge.html", context)


@login_required
def organizer_checkin(request, slug, ticket_code):
    """
    Verifies and validates attendee check-in when their QR Code is scanned.
    Accessible to organizers, judges, mentors, and staff.
    """
    hackathon = get_object_or_404(Hackathon, slug=slug)
    is_authorized = (
        request.user == hackathon.organizer
        or request.user.is_staff
        or request.user.is_superuser
        or hackathon.judges.filter(id=request.user.id).exists()
    )

    registration = get_object_or_404(
        HackathonRegistration, hackathon=hackathon, ticket_code=ticket_code
    )

    action_done = None
    if is_authorized and request.method == "POST":
        if not registration.checked_in:
            registration.checked_in = True
            registration.checked_in_at = timezone.now()
            registration.save(update_fields=["checked_in", "checked_in_at"])
            action_done = "checked_in_now"
        else:
            action_done = "already_checked_in"

    context = {
        "hackathon": hackathon,
        "registration": registration,
        "participant": registration.participant,
        "is_authorized": is_authorized,
        "action_done": action_done,
        "page_title": f"Attendee Check-In — {registration.ticket_code}",
    }
    return render(request, "hackathons/checkin.html", context)


@login_required
def toggle_checkin(request, slug, ticket_code):
    """
    Quick toggle for organizers to mark an attendee as checked-in or unchecked.
    """
    hackathon = get_object_or_404(Hackathon, slug=slug)
    is_authorized = (
        request.user == hackathon.organizer
        or request.user.is_staff
        or request.user.is_superuser
        or hackathon.judges.filter(id=request.user.id).exists()
    )
    if not is_authorized:
        messages.error(request, "Permission denied: Only organizers can manage check-ins.")
        return redirect("hackathons:detail", slug=slug)

    registration = get_object_or_404(
        HackathonRegistration, hackathon=hackathon, ticket_code=ticket_code
    )

    registration.checked_in = not registration.checked_in
    registration.checked_in_at = timezone.now() if registration.checked_in else None
    registration.save(update_fields=["checked_in", "checked_in_at"])

    status_str = "marked as present" if registration.checked_in else "marked as pending arrival"
    messages.success(
        request,
        f"{registration.participant.get_full_name() or registration.participant.username} is now {status_str}.",
    )
    return redirect(f"{hackathon.get_absolute_url()}#badge")
