from django.shortcuts import render

HACKATHONS = [
    {
        "name": "Neon Nights 2026",
        "category": "AI & Agents",
        "status": "Registration open",
        "badge_variant": "default",
        "tagline": "Build autonomous agents that thrive in the dark.",
        "dates": "Nov 14 – 16",
        "mode": "Online",
        "prize": "$50,000",
        "registered": 2418,
        "capacity": 3000,
        "gradient": "event-gradient-lime",
        "code": "// 48 hours · ship or ship",
    },
    {
        "name": "Open Source Sprint",
        "category": "OSS & DevTools",
        "status": "Team forming",
        "badge_variant": "secondary",
        "tagline": "Ship meaningful PRs to the tools you use every day.",
        "dates": "Dec 1 – 8",
        "mode": "Remote",
        "prize": "$15,000",
        "registered": 1204,
        "capacity": 2000,
        "gradient": "event-gradient-sky",
        "code": "// one week · real maintainers",
    },
    {
        "name": "Zero Day CTF",
        "category": "Security",
        "status": "Waitlist",
        "badge_variant": "outline",
        "tagline": "Find the bugs before the clock finds you.",
        "dates": "Jan 9 – 11",
        "mode": "Berlin + Online",
        "prize": "$25,000",
        "registered": 3102,
        "capacity": 3200,
        "gradient": "event-gradient-fuchsia",
        "code": "// 72 hours · capture the flag",
    },
]

CHALLENGES = [
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

LEADERBOARD = [
    {"name": "overclock", "handle": "@overclock", "initials": "OC", "points": "9,840", "delta": "+320"},
    {"name": "nullpointer", "handle": "@nullptr", "initials": "NP", "points": "9,210", "delta": "+180"},
    {"name": "syntax_samurai", "handle": "@samurai", "initials": "SS", "points": "8,775", "delta": "+240"},
    {"name": "kernelpanic", "handle": "@kpanic", "initials": "KP", "points": "8,120", "delta": "+90"},
    {"name": "async_ana", "handle": "@asyncana", "initials": "AA", "points": "7,960", "delta": "+150"},
]

FAQS = [
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

TESTIMONIALS = [
    {
        "quote": (
            "HackFlow is where our team met. Two hackathons later we had a working "
            "prototype, a design partner and a seed round."
        ),
        "name": "Maya Chen",
        "role": "Co-founder, Loopline",
        "initials": "MC",
        "accent": "tone-lime",
    },
    {
        "quote": (
            "The best-run hackathon I've ever judged. Rubrics were clear, scoring was "
            "transparent, and the team actually shipped on time."
        ),
        "name": "Dev Patel",
        "role": "Staff Engineer, Vercel",
        "initials": "DP",
        "accent": "tone-sky",
    },
    {
        "quote": (
            "I shipped my first open-source PR through a HackFlow challenge. A year "
            "later I maintain the project."
        ),
        "name": "Ana Souza",
        "role": "OSS maintainer, Rift",
        "initials": "AS",
        "accent": "tone-fuchsia",
    },
]

from hackathons.models import Hackathon


def home(request):
    db_hackathons = list(
        Hackathon.objects.filter(is_published=True).order_by("start_date")[:6]
    )

    return render(
        request,
        "core/home.html",
        {
            "hackathons": db_hackathons if db_hackathons else HACKATHONS,
            "using_db_hackathons": bool(db_hackathons),
            "challenges": CHALLENGES,
            "leaderboard": LEADERBOARD,
            "faqs": FAQS,
            "testimonials": TESTIMONIALS,
        },
    )

