from django.conf import settings
from django.db import models
from django.utils import timezone


class Profile(models.Model):
    class Role(models.TextChoices):
        STUDENT = "student", "Student / Participant"
        ORGANIZER = "organizer", "Organizer"
        JUDGE = "judge", "Judge / Jury"
        MENTOR = "mentor", "Mentor"
        ADMIN = "admin", "Administrator"

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="profile",
    )
    role = models.CharField(
        max_length=25,
        choices=Role.choices,
        default=Role.STUDENT,
        verbose_name="Role",
        help_text="Global account role in HackFlow",
    )
    email_verified = models.BooleanField(default=False)
    email_verified_at = models.DateTimeField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-created_at",)

    def __str__(self):
        return f"{self.user.get_username()} profile"

    def mark_email_verified(self):
        self.email_verified = True
        self.email_verified_at = timezone.now()
        self.save(update_fields=["email_verified", "email_verified_at", "updated_at"])

    def reset_email_verification(self):
        self.email_verified = False
        self.email_verified_at = None
        self.save(update_fields=["email_verified", "email_verified_at", "updated_at"])
