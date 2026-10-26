import uuid

from django.conf import settings
from django.core.exceptions import ObjectDoesNotExist, ValidationError
from django.db import models
from django.urls import reverse
from django.utils import timezone
from django.utils.text import slugify

from core.fields import HTTPSURLField


class Hackathon(models.Model):
    """
    Central model for the platform — every other module (teams, projects,
    sponsors, room allocation) references a Hackathon.
    """

    # ── Lifecycle status machine ─────────────────────────────────────
    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        REGISTRATION_OPEN = "registration_open", "Registration Open"
        ONGOING = "ongoing", "Ongoing"
        JUDGING = "judging", "Judging"
        FINISHED = "finished", "Finished"
        CANCELLED = "cancelled", "Cancelled"

    # ── Event mode ───────────────────────────────────────────────────
    class Mode(models.TextChoices):
        ONLINE = "online", "Online"
        IN_PERSON = "in_person", "In-person"
        HYBRID = "hybrid", "Hybrid"

    # ── Difficulty level ─────────────────────────────────────────────
    class Difficulty(models.TextChoices):
        BEGINNER = "beginner", "Beginner"
        INTERMEDIATE = "intermediate", "Intermediate"
        ADVANCED = "advanced", "Advanced"
        ALL_LEVELS = "all_levels", "All Levels"

    # ── General information ──────────────────────────────────────────
    title = models.CharField(
        max_length=200,
        verbose_name="Title",
    )
    slug = models.SlugField(
        max_length=220,
        unique=True,
        blank=True,
        help_text="Auto-generated from title if left blank.",
    )
    tagline = models.CharField(
        max_length=255,
        verbose_name="Tagline",
        help_text="Catchy one-line slogan.",
    )
    description = models.TextField(
        verbose_name="Detailed Description",
    )
    category = models.CharField(
        max_length=100,
        verbose_name="Category",
        help_text="Ex: AI & Data, Web3, GreenTech, Cybersecurity…",
    )
    banner_image = models.ImageField(
        upload_to="hackathons/banners/",
        blank=True,
        null=True,
        verbose_name="Banner Image",
    )

    # ── Dates & scheduling ───────────────────────────────────────────
    registration_start = models.DateTimeField(
        verbose_name="Registration Opens",
    )
    registration_deadline = models.DateTimeField(
        verbose_name="Registration Deadline",
    )
    start_date = models.DateTimeField(
        verbose_name="Event Start Date",
    )
    end_date = models.DateTimeField(
        verbose_name="Event End Date",
    )

    # ── Mode & location ──────────────────────────────────────────────
    mode = models.CharField(
        max_length=20,
        choices=Mode.choices,
        default=Mode.IN_PERSON,
        verbose_name="Event Mode",
    )
    location = models.CharField(
        max_length=255,
        blank=True,
        default="",
        verbose_name="Location / Venue",
        help_text="Physical venue, Discord/Teams link, or both for hybrid.",
    )

    # ── Capacity & team rules ────────────────────────────────────────
    max_participants = models.PositiveIntegerField(
        default=100,
        verbose_name="Max Participants",
    )
    min_team_size = models.PositiveSmallIntegerField(
        default=2,
        verbose_name="Min Team Size",
    )
    max_team_size = models.PositiveSmallIntegerField(
        default=4,
        verbose_name="Max Team Size",
    )

    # ── Prize & level ────────────────────────────────────────────────
    prize_pool = models.CharField(
        max_length=100,
        blank=True,
        default="",
        verbose_name="Prize Pool",
        help_text="Ex: $10,000, 5,000 TND, Incubation, Certificates…",
    )
    difficulty = models.CharField(
        max_length=20,
        choices=Difficulty.choices,
        default=Difficulty.ALL_LEVELS,
        verbose_name="Difficulty Level",
    )

    # ── Rules & resources ────────────────────────────────────────────
    rules = models.TextField(
        blank=True,
        default="",
        verbose_name="Rules & Guidelines",
        help_text="Eligibility, judging criteria, code of conduct.",
    )
    resources_link = HTTPSURLField(
        blank=True,
        default="",
        verbose_name="Resources Link",
        help_text="Link to datasets, starter repos, API docs or Drive.",
    )
    contact_email = models.EmailField(
        blank=True,
        default="",
        verbose_name="Contact Email",
    )

    # ── Ownership & status ───────────────────────────────────────────
    organizer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="organized_hackathons",
        verbose_name="Organizer",
    )
    judges = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        blank=True,
        related_name="judged_hackathons",
        verbose_name="Assigned Judges",
        help_text="Judges assigned to evaluate submissions for this event.",
    )
    mentors = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        blank=True,
        related_name="mentored_hackathons",
        verbose_name="Assigned Mentors",
        help_text="Mentors assigned to guide teams for this event.",
    )
    status = models.CharField(
        max_length=25,
        choices=Status.choices,
        default=Status.DRAFT,
        verbose_name="Status",
    )
    is_published = models.BooleanField(
        default=False,
        verbose_name="Published",
        help_text="Only published hackathons appear in the public catalogue.",
    )

    # ── Timestamps ───────────────────────────────────────────────────
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-start_date"]
        verbose_name = "Hackathon"
        verbose_name_plural = "Hackathons"

    def save(self, *args, **kwargs):
        if not self.slug:
            base_slug = slugify(self.title)
            slug = base_slug
            counter = 1
            while Hackathon.objects.filter(slug=slug).exclude(pk=self.pk).exists():
                slug = f"{base_slug}-{counter}"
                counter += 1
            self.slug = slug
        super().save(*args, **kwargs)

    def clean(self):
        """Cross-field validation for dates and team sizes."""
        errors = {}

        if self.registration_start and self.registration_deadline:
            if self.registration_deadline <= self.registration_start:
                errors["registration_deadline"] = (
                    "Registration deadline must be after registration start."
                )

        if self.registration_deadline and self.start_date:
            if self.start_date < self.registration_deadline:
                errors["start_date"] = "The hackathon cannot start before registration closes."

        if self.start_date and self.end_date:
            if self.end_date <= self.start_date:
                errors["end_date"] = "End date must be after start date."

        if self.min_team_size and self.max_team_size:
            if self.min_team_size > self.max_team_size:
                errors["min_team_size"] = "Minimum team size cannot exceed maximum team size."

        if errors:
            raise ValidationError(errors)

    def __str__(self):
        return self.title

    def get_absolute_url(self):
        return reverse("hackathons:detail", kwargs={"slug": self.slug})

    # ── Computed helpers ─────────────────────────────────────────────
    @property
    def is_registration_upcoming(self):
        if not self.registration_start:
            return False
        return timezone.now() < self.registration_start

    @property
    def is_registration_closed(self):
        if not self.registration_deadline:
            return False
        return timezone.now() > self.registration_deadline

    @property
    def is_registration_open(self):
        now = timezone.now()
        if not (self.registration_start and self.registration_deadline):
            return False
        return (
            self.status == self.Status.REGISTRATION_OPEN
            and self.registration_start <= now <= self.registration_deadline
        )

    @property
    def is_ongoing(self):
        now = timezone.now()
        return self.start_date <= now <= self.end_date

    @property
    def is_past(self):
        return timezone.now() > self.end_date

    @property
    def days_until_start(self):
        delta = self.start_date - timezone.now()
        return max(delta.days, 0)

    @property
    def registered_count(self):
        """Count of confirmed participants."""
        return self.registrations.filter(status=HackathonRegistration.Status.CONFIRMED).count()

    @property
    def waitlist_count(self):
        """Count of waitlisted participants."""
        return self.registrations.filter(status=HackathonRegistration.Status.WAITLIST).count()

    @property
    def is_full(self):
        """True if confirmed participants reached maximum capacity."""
        return self.registered_count >= self.max_participants

    @property
    def registration_progress_percent(self):
        if self.max_participants == 0:
            return 0
        return min(int((self.registered_count / self.max_participants) * 100), 100)


class HackathonSchedule(models.Model):
    hackathon = models.ForeignKey(
        Hackathon,
        on_delete=models.CASCADE,
        related_name="schedule_items",
    )
    title = models.CharField(max_length=200, verbose_name="Title")
    description = models.TextField(blank=True, default="", verbose_name="Description")
    scheduled_at = models.DateTimeField(verbose_name="Scheduled Time")

    class Meta:
        ordering = ["scheduled_at"]
        verbose_name = "Schedule Item"
        verbose_name_plural = "Hackathon Schedule"

    def __str__(self):
        return f"{self.hackathon.title} — {self.title}"


class HackathonRegistration(models.Model):
    class Status(models.TextChoices):
        CONFIRMED = "confirmed", "Confirmed"
        WAITLIST = "waitlist", "Waitlist"
        CANCELLED = "cancelled", "Cancelled"

    class StudyLevel(models.TextChoices):
        L1 = "L1", "Bachelor 1st Year (L1)"
        L2 = "L2", "Bachelor 2nd Year (L2)"
        L3 = "L3", "Bachelor 3rd Year (L3)"
        M1 = "M1", "Master 1st Year (M1)"
        M2 = "M2", "Master 2nd Year (M2)"
        ING1 = "ING1", "Engineering 1st Year"
        ING2 = "ING2", "Engineering 2nd Year"
        ING3 = "ING3", "Engineering Final Year"
        DOC = "DOC", "PhD / Doctorate"
        OTHER = "OTHER", "Other"

    class ExperienceLevel(models.TextChoices):
        BEGINNER = "beginner", "Beginner"
        INTERMEDIATE = "intermediate", "Intermediate"
        ADVANCED = "advanced", "Advanced"

    hackathon = models.ForeignKey(
        Hackathon,
        on_delete=models.CASCADE,
        related_name="registrations",
    )
    participant = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="hackathon_registrations",
    )
    registered_at = models.DateTimeField(auto_now_add=True)
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.CONFIRMED,
        verbose_name="Status",
        db_index=True,  # Frequently filtered for confirmed/waitlist counts
    )

    # Required form fields
    university = models.CharField(
        max_length=150,
        blank=True,
        default="",
        verbose_name="University / Institution",
    )
    study_level = models.CharField(
        max_length=20,
        choices=StudyLevel.choices,
        default=StudyLevel.L3,
        verbose_name="Study Level",
    )
    skills = models.CharField(
        max_length=255,
        blank=True,
        default="",
        verbose_name="Skills",
        help_text="Key technical skills (Python, Django, React, UI/UX, AI, Data...)",
    )
    experience_level = models.CharField(
        max_length=20,
        choices=ExperienceLevel.choices,
        default=ExperienceLevel.INTERMEDIATE,
        verbose_name="Experience Level",
    )

    # Optional form fields
    seeking_team = models.BooleanField(
        default=False,
        verbose_name="Looking for a team",
    )
    tshirt_dietary = models.CharField(
        max_length=200,
        blank=True,
        default="",
        verbose_name="T-shirt size & dietary restrictions",
    )
    portfolio_url = HTTPSURLField(
        blank=True,
        default="",
        verbose_name="GitHub / LinkedIn Link",
    )
    motivation = models.TextField(
        blank=True,
        default="",
        verbose_name="Motivation",
        help_text="Why do you want to participate?",
    )
    accepted_rules = models.BooleanField(
        default=True,
        verbose_name="Accept Rules & Code of Conduct",
    )

    # Check-in & Badge Pass attributes
    ticket_code = models.CharField(
        max_length=64,
        blank=True,
        default="",
        verbose_name="Ticket / Badge Code",
        help_text="Unique verifiable badge identifier (e.g. HF-A8F290B1E4)",
    )
    checked_in = models.BooleanField(
        default=False,
        verbose_name="Checked In",
        help_text="Participant badge scanned and marked present at venue",
    )
    checked_in_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="Checked In At",
    )

    class Meta:
        ordering = ["-registered_at"]
        unique_together = [("hackathon", "participant")]
        verbose_name = "Registration"
        verbose_name_plural = "Registrations"

    def __str__(self):
        return f"{self.participant.get_username()} → {self.hackathon.title} ({self.get_status_display()})"

    def save(self, *args, **kwargs):
        if not self.ticket_code:
            self.ticket_code = f"HF-{uuid.uuid4().hex[:10].upper()}"
        super().save(*args, **kwargs)

    def clean(self):
        try:
            hackathon = self.hackathon
        except ObjectDoesNotExist:
            hackathon = None
        if hackathon:
            now = timezone.now()
            if hackathon.registration_deadline and now > hackathon.registration_deadline:
                raise ValidationError("Registration is currently closed for this hackathon.")
            if hackathon.registration_start and now < hackathon.registration_start:
                raise ValidationError("Registration has not opened yet.")


class HackathonFAQ(models.Model):
    hackathon = models.ForeignKey(
        Hackathon,
        on_delete=models.CASCADE,
        related_name="faqs",
    )
    question = models.CharField(max_length=300, verbose_name="Question")
    answer = models.TextField(verbose_name="Answer")
    order = models.PositiveSmallIntegerField(default=0, verbose_name="Order")

    class Meta:
        ordering = ["order"]
        verbose_name = "FAQ"
        verbose_name_plural = "FAQs"

    def __str__(self):
        return f"FAQ: {self.question[:50]}"
