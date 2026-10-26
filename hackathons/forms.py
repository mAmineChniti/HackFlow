from django import forms
from django.db import models
from .models import Hackathon, HackathonRegistration, HackathonSchedule


class TailwindFormMixin:
    """Helper mixin to give Django form fields the HackFlow / Shadcn Tailwind styling."""

    input_class = (
        "flex h-9 w-full rounded-md border border-input bg-transparent px-3 py-1 text-sm shadow-xs "
        "transition-colors file:border-0 file:bg-transparent file:text-sm file:font-medium "
        "placeholder:text-muted-foreground focus-visible:outline-hidden focus-visible:ring-1 "
        "focus-visible:ring-ring disabled:cursor-not-allowed disabled:opacity-50"
    )
    textarea_class = (
        "flex min-h-[90px] w-full rounded-md border border-input bg-transparent px-3 py-2 text-sm shadow-xs "
        "placeholder:text-muted-foreground focus-visible:outline-hidden focus-visible:ring-1 "
        "focus-visible:ring-ring disabled:cursor-not-allowed disabled:opacity-50"
    )
    select_class = (
        "flex h-9 w-full rounded-md border border-input bg-background px-3 py-1 text-sm shadow-xs "
        "transition-colors focus-visible:outline-hidden focus-visible:ring-1 focus-visible:ring-ring "
        "disabled:cursor-not-allowed disabled:opacity-50"
    )
    checkbox_class = "size-4 rounded border-border text-primary focus:ring-primary accent-primary cursor-pointer shrink-0"

    def apply_tailwind_classes(self):
        for name, field in self.fields.items():
            widget = field.widget
            if isinstance(widget, (forms.CheckboxInput, forms.CheckboxSelectMultiple)):
                widget.attrs["class"] = (
                    f"{widget.attrs.get('class', '')} {self.checkbox_class}".strip()
                )
            elif isinstance(widget, forms.Textarea):
                widget.attrs["class"] = (
                    f"{widget.attrs.get('class', '')} {self.textarea_class}".strip()
                )
            elif isinstance(widget, (forms.Select, forms.SelectMultiple)):
                widget.attrs["class"] = (
                    f"{widget.attrs.get('class', '')} {self.select_class}".strip()
                )
            else:
                widget.attrs["class"] = (
                    f"{widget.attrs.get('class', '')} {self.input_class}".strip()
                )


class HackathonForm(TailwindFormMixin, forms.ModelForm):
    class Meta:
        model = Hackathon
        fields = [
            "title",
            "tagline",
            "description",
            "category",
            "banner_image",
            "mode",
            "location",
            "registration_start",
            "registration_deadline",
            "start_date",
            "end_date",
            "max_participants",
            "min_team_size",
            "max_team_size",
            "prize_pool",
            "difficulty",
            "rules",
            "resources_link",
            "contact_email",
            "judges",
            "mentors",
            "status",
            "is_published",
        ]
        widgets = {
            "registration_start": forms.DateTimeInput(
                attrs={"type": "datetime-local"}, format="%Y-%m-%dT%H:%M"
            ),
            "registration_deadline": forms.DateTimeInput(
                attrs={"type": "datetime-local"}, format="%Y-%m-%dT%H:%M"
            ),
            "start_date": forms.DateTimeInput(
                attrs={"type": "datetime-local"}, format="%Y-%m-%dT%H:%M"
            ),
            "end_date": forms.DateTimeInput(
                attrs={"type": "datetime-local"}, format="%Y-%m-%dT%H:%M"
            ),
            "description": forms.Textarea(
                attrs={
                    "rows": 4,
                    "placeholder": "Describe the theme, challenge prompt and goals...",
                }
            ),
            "rules": forms.Textarea(
                attrs={"rows": 4, "placeholder": "Eligibility, code of conduct, scoring rubric..."}
            ),
            "tagline": forms.TextInput(
                attrs={"placeholder": "Ex: 48 hours to build autonomous AI agents"}
            ),
            "category": forms.TextInput(
                attrs={"placeholder": "Ex: AI & Data, Web3, GreenTech, Cybersecurity"}
            ),
            "location": forms.TextInput(
                attrs={"placeholder": "Ex: ESPRIT Building B / Remote via Discord"}
            ),
            "prize_pool": forms.TextInput(
                attrs={"placeholder": "Ex: $10,000 + Incubation Support"}
            ),
            "resources_link": forms.URLInput(attrs={"placeholder": "https://..."}),
            "contact_email": forms.EmailInput(attrs={"placeholder": "organizers@hackflow.dev"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.apply_tailwind_classes()
        for date_field in ["registration_start", "registration_deadline", "start_date", "end_date"]:
            if self.instance and getattr(self.instance, date_field, None):
                self.initial[date_field] = getattr(self.instance, date_field).strftime(
                    "%Y-%m-%dT%H:%M"
                )

        from django.contrib.auth import get_user_model

        User = get_user_model()
        if "judges" in self.fields:
            self.fields["judges"].queryset = User.objects.filter(
                models.Q(profile__role="judge") | models.Q(is_superuser=True)
            )
            self.fields["judges"].required = False
            self.fields["judges"].help_text = "Select judges assigned to evaluate projects."
        if "mentors" in self.fields:
            self.fields["mentors"].queryset = User.objects.filter(
                models.Q(profile__role="mentor") | models.Q(is_superuser=True)
            )
            self.fields["mentors"].required = False
            self.fields["mentors"].help_text = "Select mentors assigned to guide teams."

    def clean(self):
        cleaned_data = super().clean()
        reg_start = cleaned_data.get("registration_start")
        reg_deadline = cleaned_data.get("registration_deadline")
        start_date = cleaned_data.get("start_date")
        end_date = cleaned_data.get("end_date")
        min_team = cleaned_data.get("min_team_size")
        max_team = cleaned_data.get("max_team_size")

        if reg_start and reg_deadline and reg_deadline <= reg_start:
            self.add_error(
                "registration_deadline",
                "Registration deadline must be after registration opening date.",
            )

        if reg_deadline and start_date and start_date < reg_deadline:
            self.add_error(
                "start_date",
                "The hackathon cannot start before registration closes.",
            )

        if start_date and end_date and end_date <= start_date:
            self.add_error(
                "end_date",
                "End date must be after start date.",
            )

        if min_team and max_team and min_team > max_team:
            self.add_error(
                "min_team_size",
                "Minimum team size cannot be greater than maximum team size.",
            )

        return cleaned_data


class RegistrationForm(TailwindFormMixin, forms.ModelForm):
    POPULAR_SKILLS = [
        ("Python", "Python"),
        ("Django", "Django"),
        ("React", "React"),
        ("Next.js", "Next.js"),
        ("UI/UX", "UI/UX Design"),
        ("AI", "AI / Machine Learning"),
        ("Data", "Data Science"),
        ("Cybersecurity", "Cybersecurity"),
        ("Cloud/DevOps", "Cloud / DevOps"),
        ("Mobile", "Mobile (Flutter/React Native)"),
        ("Web3", "Web3 / Blockchain"),
    ]

    selected_skills = forms.MultipleChoiceField(
        label="Key Technical Skills",
        choices=POPULAR_SKILLS,
        required=False,
        widget=forms.CheckboxSelectMultiple(
            attrs={
                "class": "size-4 rounded border-border text-primary accent-primary cursor-pointer shrink-0"
            }
        ),
        help_text="Check all your primary technical skills",
    )
    other_skills = forms.CharField(
        label="Other skills & technologies",
        required=False,
        widget=forms.TextInput(
            attrs={"placeholder": "Ex: Vue, Rust, Docker, ThreeJS (comma-separated)"}
        ),
    )
    accepted_rules = forms.BooleanField(
        label="I have read and agree to the official hackathon rules and code of conduct.",
        required=True,
        widget=forms.CheckboxInput,
    )

    class Meta:
        model = HackathonRegistration
        fields = [
            "university",
            "study_level",
            "experience_level",
            "skills",
            "seeking_team",
            "tshirt_dietary",
            "portfolio_url",
            "motivation",
            "accepted_rules",
        ]
        widgets = {
            "university": forms.TextInput(
                attrs={
                    "placeholder": "Ex: MIT, Stanford, ESPRIT, INSAT, Oxford...",
                    "required": "required",
                }
            ),
            "study_level": forms.Select(),
            "experience_level": forms.Select(),
            "skills": forms.HiddenInput(attrs={"required": False}),
            "seeking_team": forms.CheckboxInput(),
            "tshirt_dietary": forms.TextInput(
                attrs={
                    "placeholder": "Ex: Size M — Vegetarian, Gluten-free, or None",
                }
            ),
            "portfolio_url": forms.URLInput(
                attrs={
                    "placeholder": "https://github.com/your-handle or https://linkedin.com/in/...",
                }
            ),
            "motivation": forms.Textarea(
                attrs={
                    "rows": 3,
                    "placeholder": "What drives you to participate? What problems or projects do you want to tackle?",
                }
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["university"].required = True
        self.fields["study_level"].required = True
        self.fields["experience_level"].required = True
        self.fields["accepted_rules"].required = True
        self.fields["skills"].required = False

        if self.instance and self.instance.skills:
            current_skills = [s.strip() for s in self.instance.skills.split(",") if s.strip()]
            popular_keys = [k for k, _ in self.POPULAR_SKILLS]
            matched = [s for s in current_skills if s in popular_keys]
            unmatched = [s for s in current_skills if s not in popular_keys]
            self.initial["selected_skills"] = matched
            if unmatched:
                self.initial["other_skills"] = ", ".join(unmatched)

        self.apply_tailwind_classes()

    def clean(self):
        cleaned_data = super().clean()
        selected = cleaned_data.get("selected_skills") or []
        other = (cleaned_data.get("other_skills") or "").strip()
        direct_skills = (cleaned_data.get("skills") or "").strip()

        all_skills = list(selected)
        if other:
            all_skills.extend([s.strip() for s in other.split(",") if s.strip()])
        if direct_skills and not all_skills:
            all_skills.extend([s.strip() for s in direct_skills.split(",") if s.strip()])

        if not all_skills:
            self.add_error(
                "selected_skills",
                "Please check at least one skill or specify one in 'Other skills'.",
            )
        else:
            cleaned_data["skills"] = ", ".join(all_skills)

        if not cleaned_data.get("accepted_rules"):
            self.add_error(
                "accepted_rules",
                "You must accept the hackathon rules and code of conduct to register.",
            )

        return cleaned_data


class ScheduleForm(TailwindFormMixin, forms.ModelForm):
    class Meta:
        model = HackathonSchedule
        fields = ["title", "description", "scheduled_at"]
        widgets = {
            "scheduled_at": forms.DateTimeInput(
                attrs={"type": "datetime-local"}, format="%Y-%m-%dT%H:%M"
            ),
            "description": forms.Textarea(
                attrs={"rows": 2, "placeholder": "Key details for this milestone..."}
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.apply_tailwind_classes()
