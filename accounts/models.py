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
        return f"{self.user.get_username()} profile ({self.get_role_display()})"

    @property
    def is_admin_user(self):
        return self.role == self.Role.ADMIN or self.user.is_superuser

    @property
    def is_organizer_user(self):
        return self.role == self.Role.ORGANIZER or self.is_admin_user

    @property
    def is_student_user(self):
        return self.role == self.Role.STUDENT

    @property
    def is_judge_user(self):
        return self.role == self.Role.JUDGE

    @property
    def is_mentor_user(self):
        return self.role == self.Role.MENTOR

    @property
    def role_badge_colors(self):
        """Tailwind badge color classes tailored for each actor role."""
        if self.is_admin_user:
            return "border-rose-500/40 bg-rose-500/10 text-rose-400 font-semibold"
        if self.role == self.Role.ORGANIZER:
            return "border-primary/40 bg-primary/10 text-primary font-semibold"
        if self.role == self.Role.JUDGE:
            return "border-amber-500/40 bg-amber-500/10 text-amber-400 font-semibold"
        if self.role == self.Role.MENTOR:
            return "border-emerald-500/40 bg-emerald-500/10 text-emerald-400 font-semibold"
        return "border-sky-500/40 bg-sky-500/10 text-sky-400"

    def mark_email_verified(self):
        self.email_verified = True
        self.email_verified_at = timezone.now()
        self.save(update_fields=["email_verified", "email_verified_at", "updated_at"])

    def reset_email_verification(self):
        self.email_verified = False
        self.email_verified_at = None
        self.save(update_fields=["email_verified", "email_verified_at", "updated_at"])
