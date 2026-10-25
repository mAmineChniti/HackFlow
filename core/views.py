"""Home page view.

The landing page is data-driven wherever a model already exists:

* hero + events grid  -> ``hackathons.Hackathon``
* leaderboard + recent submissions -> ``projects.Project``
* sponsor strip       -> ``sponsors`` app (via ``get_confirmed_sponsors``)
* platform counters   -> counted from the database

Challenges, testimonials and the FAQ have no models yet, so they stay inline
below as clearly marked placeholder content until those features are built.
"""

from django.contrib.auth import get_user_model
from django.db.models import Sum
from django.shortcuts import render
from django.utils import timezone

from projects.models import Project

try:  # The hackathons app is still a temporary stub that may be replaced.
    from hackathons.models import Hackathon
except Exception:  # pragma: no cover - only when the stub app is removed
    Hackathon = None

try:  # Sponsors is an optional module for deployments that don't run events.
    from sponsors.models import Sponsorship, StatusChoices as SponsorshipStatus
except Exception:  # pragma: no cover - only when the sponsors app is removed
    Sponsorship = None
    SponsorshipStatus = None

User = get_user_model()

# Visual accents cycled across event cards so the grid keeps its rhythm.
EVENT_GRADIENTS = (
    "event-gradient-lime",
    "event-gradient-sky",
    "event-gradient-fuchsia",
)

EVENT_BADGE_VARIANTS = {
    "Live now": "default",
    "Upcoming": "secondary",
    "Completed": "outline",
    "Announced": "secondary",
}

RECENT_SUBMISSION_STATUSES = (
    Project.Status.SUBMITTED,
    Project.Status.UNDER_REVIEW,
    Project.Status.ACCEPTED,
)

STATUS_TONES = {
    Project.Status.SUBMITTED: "tone-emerald",
    Project.Status.UNDER_REVIEW: "tone-amber",
    Project.Status.ACCEPTED: "tone-sky",
}


def _format_date_range(start, end):
    """Return a compact, human date range such as "14 – 16 Nov 2026"."""
    if not start and not end:
        return "Dates to be announced"
    if start and not end:
        return f"From {start:%d %b %Y}"
    if not start and end:
        return f"Until {end:%d %b %Y}"
    if start == end:
        return f"{start:%d %b %Y}"
    if (start.year, start.month) == (end.year, end.month):
        return f"{start:%d} – {end:%d %b %Y}"
    if start.year == end.year:
        return f"{start:%d %b} – {end:%d %b %Y}"
    return f"{start:%d %b %Y} – {end:%d %b %Y}"


def _event_status(start, end, today):
    """Derive a display status from the event dates (no stored status field)."""
    if end and today > end:
        return "Completed"
    if start and today < start:
        return "Upcoming"
    if start and end and start <= today <= end:
        return "Live now"
    return "Announced"


def _event_duration(start, end):
    """Number of days covered by the event, or None when unknown."""
    if not start or not end:
        return None
    return (end - start).days + 1


def _initials(text):
    """Two-letter monogram used by the avatar circles."""
    words = [part for part in str(text).replace("-", " ").split() if part]
    if not words:
        return "??"
    if len(words) == 1:
        return words[0][:2].upper()
    return (words[0][0] + words[1][0]).upper()


def _build_event(event, index, today):
    status = _event_status(event.start_date, event.end_date, today)
    duration = _event_duration(event.start_date, event.end_date)
    return {
        "name": event.name,
        "theme": event.theme,
        "category": event.theme or "Hackathon",
        "status": status,
        "badge_variant": EVENT_BADGE_VARIANTS.get(status, "secondary"),
        "dates": _format_date_range(event.start_date, event.end_date),
        "duration": f"{duration}-day event" if duration else "",
        "start_date": event.start_date,
        "end_date": event.end_date,
        "gradient": EVENT_GRADIENTS[index % len(EVENT_GRADIENTS)],
        "is_finished": status == "Completed",
    }


def _featured_event(events, today):
    """Pick the event to spotlight.

    Order of preference: an event happening right now, then the soonest
    upcoming one, then the most recently finished one, then anything undated.
    """
    if not events:
        return None

    ongoing = [
        event
        for event in events
        if event.start_date
        and event.end_date
        and event.start_date <= today <= event.end_date
    ]
    if ongoing:
        return min(ongoing, key=lambda event: event.start_date)

    upcoming = [
        event
        for event in events
        if event.start_date and event.start_date > today
    ]
    if upcoming:
        return min(upcoming, key=lambda event: event.start_date)

    finished = [
        event
        for event in events
        if event.end_date and event.end_date < today
    ]
    if finished:
        return max(finished, key=lambda event: event.end_date)

    return events[0]


def _platform_stats():
    """Real counters for the landing page instead of invented numbers."""
    today = timezone.localdate()
    confirmed_funding = 0
    confirmed_count = 0
    if Sponsorship is not None:
        confirmed = Sponsorship.objects.filter(status=SponsorshipStatus.CONFIRME)
        confirmed_count = confirmed.count()
        confirmed_funding = confirmed.aggregate(total=Sum("amount"))["total"] or 0

    return {
        "projects": Project.objects.count(),
        "builders": User.objects.count(),
        "events": Hackathon.objects.count() if Hackathon else 0,
        "live_events": (
            Hackathon.objects.exclude(end_date__lt=today).count() if Hackathon else 0
        ),
        "confirmed_sponsorships": confirmed_count,
        "funding": confirmed_funding,
    }


# ---------------------------------------------------------------------------
# Placeholder content — no models exist yet for these three sections.
# Replace with real querysets when the challenges, testimonials and FAQ
# features are implemented.
# ---------------------------------------------------------------------------

DEMO_CHALLENGES = [
    {"title": "Rate Limit Bypass", "category": "Web Security", "glyph": "</>",
     "difficulty": "Hard", "difficulty_class": "tone-rose", "points": "500",
     "solves": "1,284", "tag": "New"},
    {"title": "Build a RAG Pipeline", "category": "AI / ML", "glyph": "{ }",
     "difficulty": "Intermediate", "difficulty_class": "tone-amber", "points": "750",
     "solves": "642", "tag": ""},
    {"title": "Zero-Copy Parser", "category": "Systems", "glyph": "0x1",
     "difficulty": "Hard", "difficulty_class": "tone-rose", "points": "1000",
     "solves": "231", "tag": ""},
]

DEMO_TESTIMONIALS = [
    {"quote": ("HackFlow is where our team met. Two hackathons later we had a "
               "working prototype, a design partner and a seed round."),
     "name": "Maya Chen", "role": "Co-founder, Loopline", "initials": "MC",
     "accent": "tone-lime"},
    {"quote": ("The best-run hackathon I've ever judged. Rubrics were clear, "
               "scoring was transparent, and the team actually shipped on time."),
     "name": "Dev Patel", "role": "Staff Engineer, Vercel", "initials": "DP",
     "accent": "tone-sky"},
    {"quote": ("I shipped my first open-source PR through a HackFlow challenge. "
               "A year later I maintain the project."),
     "name": "Ana Souza", "role": "OSS maintainer, Rift", "initials": "AS",
     "accent": "tone-fuchsia"},
]

DEMO_FAQS = [
    {"value": "faq-what", "question": "What exactly is HackFlow?",
     "answer": ("HackFlow is a home for builders. We run time-boxed hackathons, host "
                "always-on challenges, and give organizers the tooling to run their own "
                "events — registration, teams, submissions, judging and live leaderboards, "
                "all in one place.")},
    {"value": "faq-free", "question": "Is it free to join?",
     "answer": ("Yes. Creating a profile, joining hackathons and solving challenges is free "
                "for builders. Organizers can start with a free tier and upgrade when they "
                "need advanced judging, sponsor tooling or private events.")},
    {"value": "faq-host", "question": "Can I host my own hackathon?",
     "answer": ("Absolutely. You get a branded event page, registration and team management, "
                "submission handling, rubric-based judging, automated scoring for technical "
                "challenges and a real-time leaderboard. Reach out and we'll help you launch.")},
    {"value": "faq-beginner", "question": "Are the challenges beginner friendly?",
     "answer": ("Every challenge is tagged by difficulty, and we publish hints, write-ups and "
                "community solutions after each event. Start with the beginner track, then "
                "level up at your own pace.")},
    {"value": "faq-judging", "question": "How are submissions judged?",
     "answer": ("Hackathon projects are scored against a published rubric by independent "
                "judges, with conflict-of-interest checks and transparent score breakdowns. "
                "Technical challenges run against automated test suites, so leaderboard points "
                "are reproducible.")},
]


def home(request):
    today = timezone.localdate()

    events = []
    if Hackathon is not None:
        events = list(
            Hackathon.objects.exclude(name="").order_by("-start_date", "name")
        )
    event_cards = [_build_event(event, index, today) for index, event in enumerate(events)]

    featured = _featured_event(events, today)
    featured_data = None
    if featured is not None:
        featured_data = _build_event(featured, 0, today)
        featured_data["url"] = "#hackathons"

    scored_projects = (
        Project.objects.filter(score__isnull=False)
        .exclude(status=Project.Status.DRAFT)
        .select_related("created_by")
        .order_by("-score", "-updated_at")[:5]
    )
    leaderboard = [
        {
            "name": project.title,
            "handle": f"@{project.created_by.get_username()}" if project.created_by else "",
            "initials": _initials(project.title),
            "points": f"{project.score}/10",
            "url": project.get_absolute_url(),
        }
        for project in scored_projects
    ]

    recent_submissions = [
        {
            "title": project.title,
            "tagline": project.tagline,
            "status": project.get_status_display(),
            "tone": STATUS_TONES.get(project.status, "tone-emerald"),
            "url": project.get_absolute_url(),
        }
        for project in Project.objects.filter(status__in=RECENT_SUBMISSION_STATUSES)
        .select_related("created_by")
        .order_by("-submitted_at", "-created_at")[:3]
    ]

    return render(
        request,
        "core/home.html",
        {
            "hackathons": event_cards,
            "featured_event": featured_data,
            "leaderboard": leaderboard,
            "recent_submissions": recent_submissions,
            "stats": _platform_stats(),
            # Placeholder sections (no backing models yet).
            "challenges": DEMO_CHALLENGES,
            "testimonials": DEMO_TESTIMONIALS,
            "faqs": DEMO_FAQS,
        },
    )
