from django import forms
from .models import Project, ProjectMember, ConseilMentor


class ProjectForm(forms.ModelForm):
    class Meta:
        model = Project
        fields = [
            "title",
            "tagline",
            "description",
            "category",
            "hackathon",
            "status",
            "repository_url",
            "demo_url",
            "video_url",
        ]
        widgets = {
            "title": forms.TextInput(
                attrs={
                    "class": "flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background file:border-0 file:bg-transparent file:text-sm file:font-medium placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50",
                    "placeholder": "e.g. HackFlow - Hackathon Platform",
                }
            ),
            "tagline": forms.TextInput(
                attrs={
                    "class": "flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background file:border-0 file:bg-transparent file:text-sm file:font-medium placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50",
                    "placeholder": "A compelling tagline describing your project",
                }
            ),
            "description": forms.Textarea(
                attrs={
                    "rows": 5,
                    "class": "flex min-h-[120px] w-full rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50",
                    "placeholder": "Describe the problem, technical choices, and impact of your solution...",
                }
            ),
            "category": forms.Select(
                attrs={
                    "class": "flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2",
                }
            ),
            "hackathon": forms.TextInput(
                attrs={
                    "class": "flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background file:border-0 file:bg-transparent file:text-sm file:font-medium placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50",
                    "placeholder": "e.g. HackFlow 2026, AI Summit, etc.",
                }
            ),
            "status": forms.Select(
                attrs={
                    "class": "flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2",
                }
            ),
            "repository_url": forms.URLInput(
                attrs={
                    "class": "flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2",
                    "placeholder": "https://github.com/my-team/my-project",
                }
            ),
            "demo_url": forms.URLInput(
                attrs={
                    "class": "flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2",
                    "placeholder": "https://my-project.vercel.app",
                }
            ),
            "video_url": forms.URLInput(
                attrs={
                    "class": "flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2",
                    "placeholder": "https://youtu.be/...",
                }
            ),
        }

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user
        from . import services

        # Retirer le champ 'status' pour les étudiants (seuls Organizer et Admin ont ce champ)
        if user is None or not (services.is_organizer(user) or services.is_admin(user)):
            self.fields.pop("status", None)

    def clean_status(self):
        status = self.cleaned_data.get("status")
        if status and self.user:
            from . import services

            services.validate_status_permission(self.user, status)
        return status


class ProjectMemberForm(forms.ModelForm):
    class Meta:
        model = ProjectMember
        fields = ["user", "role"]
        widgets = {
            "user": forms.Select(
                attrs={
                    "class": "flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2",
                }
            ),
            "role": forms.Select(
                attrs={
                    "class": "flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2",
                }
            ),
        }

    def __init__(self, *args, project=None, **kwargs):
        super().__init__(*args, **kwargs)
        # Rôles d'équipe uniquement
        self.fields["role"].choices = ProjectMember.Role.choices
        self.fields["role"].initial = ProjectMember.Role.DEVELOPPEUR

        # Filtrer la liste des utilisateurs pour ne proposer que des étudiants
        from django.contrib.auth import get_user_model
        from accounts.models import Profile

        User = get_user_model()
        students_qs = User.objects.filter(profile__role=Profile.Role.STUDENT, is_active=True)
        if project:
            # Exclure les membres déjà présents dans l'équipe
            existing_user_ids = project.team_memberships.values_list("user_id", flat=True)
            students_qs = students_qs.exclude(id__in=existing_user_ids).exclude(
                id=project.created_by_id
            )
        self.fields["user"].queryset = students_qs
        self.fields["user"].label_from_instance = lambda u: (
            f"{u.get_username()} ({u.email or 'Student'})"
        )


class ProjectReviewDecisionForm(forms.Form):
    DECISION_CHOICES = (
        ("accept", "Accept Project"),
        ("reject", "Reject Project"),
    )
    decision = forms.ChoiceField(
        choices=DECISION_CHOICES,
        widget=forms.RadioSelect(attrs={"class": "accent-primary"}),
        initial="accept",
    )
    rejection_reason = forms.CharField(
        required=False,
        widget=forms.Textarea(
            attrs={
                "rows": 3,
                "class": "flex min-h-[90px] w-full rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2",
                "placeholder": "Mandatory reason explaining why the project is rejected...",
            }
        ),
        label="Rejection Reason",
    )

    def clean(self):
        cleaned_data = super().clean()
        decision = cleaned_data.get("decision")
        reason = (cleaned_data.get("rejection_reason") or "").strip()
        if decision == "reject" and not reason:
            self.add_error(
                "rejection_reason", "Please provide a reason explaining the project rejection."
            )
        return cleaned_data


SCORE_CHOICES = [(i, f"{i} / 10") for i in range(1, 11)]


class ProjectScoreForm(forms.Form):
    """Scoring form for organizers (1 to 10)."""

    score = forms.ChoiceField(
        choices=SCORE_CHOICES,
        label="Score (1 = low, 10 = excellent)",
        widget=forms.Select(
            attrs={
                "class": "h-9 rounded-md border border-input bg-background px-2.5 text-xs text-foreground focus:outline-none focus:ring-1 focus:ring-primary",
            }
        ),
    )


class ConseilMentorForm(forms.ModelForm):
    """Mentor advice submission form."""

    class Meta:
        model = ConseilMentor
        fields = ["texte"]
        widgets = {
            "texte": forms.Textarea(
                attrs={
                    "rows": 3,
                    "class": "flex min-h-[90px] w-full rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-500 focus-visible:ring-offset-2",
                    "placeholder": "Share your feedback, technical recommendations, or improvements for the team...",
                    "required": "required",
                }
            ),
        }
        labels = {
            "texte": "Advice Content",
        }
