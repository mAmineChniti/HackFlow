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

from hackathons.models import Hackathon
from projects.models import Project

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
    "Cancelled": "outline",
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


def _event_local_date(value):
    """Convert a stored datetime to a date in the project timezone."""
    if not value:
        return None
    if timezone.is_aware(value):
        return timezone.localtime(value).date()
    return value.date()


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
    """Derive a display status from the event dates."""
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
    start = _event_local_date(event.start_date)
    end = _event_local_date(event.end_date)
    if event.status == Hackathon.Status.CANCELLED:
        status = "Cancelled"
    elif event.status == Hackathon.Status.FINISHED:
        status = "Completed"
    else:
        status = _event_status(start, end, today)

    duration = _event_duration(start, end)
    registered = event.registered_count
    capacity = event.max_participants
    progress = min(int((registered / capacity) * 100), 100) if capacity else 0

    return {
        "name": event.title,
        "title": event.title,
        "tagline": event.tagline,
        "theme": event.tagline or event.category,
        "category": event.category or "Hackathon",
        "status": status,
        "status_code": event.status,
        "badge_variant": EVENT_BADGE_VARIANTS.get(status, "secondary"),
        "dates": _format_date_range(start, end),
        "duration": f"{duration}-day event" if duration else "",
        "mode": event.get_mode_display(),
        "prize": event.prize_pool or "Prize TBA",
        "registered": registered,
        "capacity": capacity,
        "progress": progress,
        "url": event.get_absolute_url(),
        "banner_image": event.banner_image,
        "start_date": event.start_date,
        "end_date": event.end_date,
        "gradient": EVENT_GRADIENTS[index % len(EVENT_GRADIENTS)],
        "is_finished": status in {"Completed", "Cancelled"},
        "is_cancelled": status == "Cancelled",
    }


def _featured_event(events, today):
    """Pick the event to spotlight.

    Order of preference: an event happening right now, then the soonest
    upcoming one, then the most recently finished one, then anything undated.
    """
    if not events:
        return None

    ongoing = []
    upcoming = []
    finished = []
    for event in events:
        start = _event_local_date(event.start_date)
        end = _event_local_date(event.end_date)
        if start and end and start <= today <= end:
            ongoing.append(event)
        elif start and start > today:
            upcoming.append(event)
        elif end and end < today:
            finished.append(event)

    if ongoing:
        return min(ongoing, key=lambda event: event.start_date)
    if upcoming:
        return min(upcoming, key=lambda event: event.start_date)
    if finished:
        return max(finished, key=lambda event: event.end_date)
    return events[0]


def _platform_stats():
    """Real counters for the landing page instead of invented numbers."""
    confirmed_funding = 0
    confirmed_count = 0
    if Sponsorship is not None:
        confirmed = Sponsorship.objects.filter(status=SponsorshipStatus.CONFIRME)
        confirmed_count = confirmed.count()
        confirmed_funding = confirmed.aggregate(total=Sum("amount"))["total"] or 0

    published_events = Hackathon.objects.filter(is_published=True).exclude(
        status=Hackathon.Status.CANCELLED
    )
    return {
        "projects": Project.objects.count(),
        "builders": User.objects.count(),
        "events": published_events.count(),
        "live_events": published_events.filter(end_date__gte=timezone.now()).count(),
        "confirmed_sponsorships": confirmed_count,
        "funding": confirmed_funding,
    }


# ---------------------------------------------------------------------------
# Placeholder content — no models exist yet for these three sections.
# Replace with real querysets when the challenges, testimonials and FAQ
# features are implemented.
# ---------------------------------------------------------------------------

DEMO_CHALLENGES = [
    {
        "title": "Rate Limit Bypass",
        "category": "Web Security",
        "glyph": "</>",
        "difficulty": "Hard",
        "difficulty_class": "tone-rose",
        "points": "500",
        "solves": "1,284",
        "tag": "New",
    },
    {
        "title": "Build a RAG Pipeline",
        "category": "AI / ML",
        "glyph": "{ }",
        "difficulty": "Intermediate",
        "difficulty_class": "tone-amber",
        "points": "750",
        "solves": "642",
        "tag": "",
    },
    {
        "title": "Zero-Copy Parser",
        "category": "Systems",
        "glyph": "0x1",
        "difficulty": "Hard",
        "difficulty_class": "tone-rose",
        "points": "1000",
        "solves": "231",
        "tag": "",
    },
]

DEMO_TESTIMONIALS = [
    {
        "quote": (
            "HackFlow is where our team met. Two hackathons later we had a "
            "working prototype, a design partner and a seed round."
        ),
        "name": "Maya Chen",
        "role": "Co-founder, Loopline",
        "initials": "MC",
        "accent": "tone-lime",
    },
    {
        "quote": (
            "The best-run hackathon I've ever judged. Rubrics were clear, "
            "scoring was transparent, and the team actually shipped on time."
        ),
        "name": "Dev Patel",
        "role": "Staff Engineer, Vercel",
        "initials": "DP",
        "accent": "tone-sky",
    },
    {
        "quote": (
            "I shipped my first open-source PR through a HackFlow challenge. "
            "A year later I maintain the project."
        ),
        "name": "Ana Souza",
        "role": "OSS maintainer, Rift",
        "initials": "AS",
        "accent": "tone-fuchsia",
    },
]

DEMO_FAQS = [
    {
        "value": "faq-what",
        "question": "What exactly is HackFlow?",
        "answer": (
            "HackFlow is a home for builders. We run time-boxed hackathons, host "
            "always-on challenges, and give organizers the tooling to run their own "
            "events — registration, teams, submissions, judging and live leaderboards, "
            "all in one place."
        ),
    },
    {
        "value": "faq-free",
        "question": "Is it free to join?",
        "answer": (
            "Yes. Creating a profile, joining hackathons and solving challenges is free "
            "for builders. Organizers can start with a free tier and upgrade when they "
            "need advanced judging, sponsor tooling or private events."
        ),
    },
    {
        "value": "faq-host",
        "question": "Can I host my own hackathon?",
        "answer": (
            "Absolutely. You get a branded event page, registration and team management, "
            "submission handling, rubric-based judging, automated scoring for technical "
            "challenges and a real-time leaderboard. Reach out and we'll help you launch."
        ),
    },
    {
        "value": "faq-beginner",
        "question": "Are the challenges beginner friendly?",
        "answer": (
            "Every challenge is tagged by difficulty, and we publish hints, write-ups and "
            "community solutions after each event. Start with the beginner track, then "
            "level up at your own pace."
        ),
    },
    {
        "value": "faq-judging",
        "question": "How are submissions judged?",
        "answer": (
            "Hackathon projects are scored against a published rubric by independent "
            "judges, with conflict-of-interest checks and transparent score breakdowns. "
            "Technical challenges run against automated test suites, so leaderboard points "
            "are reproducible."
        ),
    },
]


def home(request):
    today = timezone.localdate()

    now = timezone.now()
    published_events = Hackathon.objects.filter(is_published=True).exclude(
        status=Hackathon.Status.CANCELLED
    )
    events = list(
        published_events.filter(end_date__gte=now).order_by("start_date")[:6]
    )
    remaining_slots = 6 - len(events)
    if remaining_slots:
        events.extend(
            published_events.filter(end_date__lt=now).order_by("-end_date")[
                :remaining_slots
            ]
        )
    event_cards = [_build_event(event, index, today) for index, event in enumerate(events)]

    featured = _featured_event(events, today)
    featured_data = None
    if featured is not None:
        featured_data = _build_event(featured, 0, today)
        featured_data["url"] = featured.get_absolute_url()

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
