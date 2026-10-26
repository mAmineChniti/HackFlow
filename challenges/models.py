from django.conf import settings
from django.db import models
from django.utils.text import slugify
from django.utils import timezone


class Challenge(models.Model):
    class Difficulty(models.TextChoices):
        BEGINNER = "beginner", "Beginner"
        INTERMEDIATE = "intermediate", "Intermediate"
        ADVANCED = "advanced", "Advanced"

    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        ACTIVE = "active", "Active"

    title = models.CharField(max_length=200, verbose_name="Title")
    slug = models.SlugField(max_length=220, unique=True, blank=True)
    description = models.TextField(verbose_name="Description")
    category = models.CharField(max_length=100, default="General", verbose_name="Category")
    difficulty = models.CharField(
        max_length=20,
        choices=Difficulty.choices,
        default=Difficulty.BEGINNER,
        verbose_name="Difficulty",
    )
    points = models.PositiveIntegerField(default=100, verbose_name="Points")
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.ACTIVE,
        verbose_name="Status",
    )
    organizer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="organized_challenges",
        verbose_name="Organizer",
    )
    hackathon = models.ForeignKey(
        "hackathons.Hackathon",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="challenges",
        verbose_name="Hackathon",
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Created at")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Updated at")

    class Meta:
        ordering = ("-created_at",)
        verbose_name = "Challenge"
        verbose_name_plural = "Challenges"

    def save(self, *args, **kwargs):
        if not self.slug:
            base = slugify(self.title) or "challenge"
            slug = base
            counter = 1
            while Challenge.objects.filter(slug=slug).exclude(pk=self.pk).exists():
                slug = f"{base}-{counter}"
                counter += 1
            self.slug = slug
        super().save(*args, **kwargs)

    def __str__(self):
        return self.title


class ChallengeSubmission(models.Model):
    class Status(models.TextChoices):
        SUBMITTED = "submitted", "Submitted"
        PASSED = "passed", "Passed"
        FAILED = "failed", "Failed"

    challenge = models.ForeignKey(
        Challenge,
        on_delete=models.CASCADE,
        related_name="submissions",
        verbose_name="Challenge",
    )
    participant = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="challenge_submissions",
        verbose_name="Participant",
    )
    solution = models.TextField(verbose_name="Solution")
    submitted_at = models.DateTimeField(auto_now_add=True, verbose_name="Submitted at")
    attempt_count = models.PositiveIntegerField(default=1, verbose_name="Attempts")
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.SUBMITTED,
        verbose_name="Status",
    )
    score = models.PositiveSmallIntegerField(null=True, blank=True, verbose_name="Score (0-100)")
    feedback = models.TextField(blank=True, default="", verbose_name="Feedback")
    last_hint = models.TextField(blank=True, default="", verbose_name="Last AI hint")

    class Meta:
        ordering = ("-submitted_at",)
        unique_together = [("challenge", "participant")]
        verbose_name = "Challenge submission"
        verbose_name_plural = "Challenge submissions"

    def __str__(self):
        return f"{self.participant} → {self.challenge} ({self.get_status_display()})"
