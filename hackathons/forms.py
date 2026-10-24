from django import forms
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
    checkbox_class = (
        "size-4 rounded border-input text-primary focus:ring-ring bg-transparent"
    )

    def apply_tailwind_classes(self):
        for name, field in self.fields.items():
            widget = field.widget
            if isinstance(widget, forms.CheckboxInput):
                widget.attrs["class"] = f"{widget.attrs.get('class', '')} {self.checkbox_class}".strip()
            elif isinstance(widget, forms.Textarea):
                widget.attrs["class"] = f"{widget.attrs.get('class', '')} {self.textarea_class}".strip()
            elif isinstance(widget, (forms.Select, forms.SelectMultiple)):
                widget.attrs["class"] = f"{widget.attrs.get('class', '')} {self.select_class}".strip()
            else:
                widget.attrs["class"] = f"{widget.attrs.get('class', '')} {self.input_class}".strip()


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
            "description": forms.Textarea(attrs={"rows": 4, "placeholder": "Décrivez la vision, le défi et les objectifs..."}),
            "rules": forms.Textarea(attrs={"rows": 4, "placeholder": "Règles d'éligibilité, code de conduite, critères..."}),
            "tagline": forms.TextInput(attrs={"placeholder": "Ex: 48 heures pour révolutionner l'intelligence artificielle"}),
            "category": forms.TextInput(attrs={"placeholder": "Ex: AI & Data, Web3, GreenTech"}),
            "location": forms.TextInput(attrs={"placeholder": "Ex: ESPRIT Bloc B / En ligne via Discord"}),
            "prize_pool": forms.TextInput(attrs={"placeholder": "Ex: 5 000 TND + Incubation"}),
            "resources_link": forms.URLInput(attrs={"placeholder": "https://..."}),
            "contact_email": forms.EmailInput(attrs={"placeholder": "contact@hackflow.dev"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.apply_tailwind_classes()
        # Formats for datetime-local
        for date_field in ["registration_start", "registration_deadline", "start_date", "end_date"]:
            if self.instance and getattr(self.instance, date_field, None):
                self.initial[date_field] = getattr(self.instance, date_field).strftime("%Y-%m-%dT%H:%M")

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
                "La date limite d'inscription doit être postérieure à l'ouverture des inscriptions.",
            )

        if reg_deadline and start_date and start_date < reg_deadline:
            self.add_error(
                "start_date",
                "Le hackathon ne peut pas commencer avant la fin des inscriptions.",
            )

        if start_date and end_date and end_date <= start_date:
            self.add_error(
                "end_date",
                "La date de fin doit être postérieure à la date de début.",
            )

        if min_team and max_team and min_team > max_team:
            self.add_error(
                "min_team_size",
                "La taille minimale ne peut pas dépasser la taille maximale.",
            )

        return cleaned_data


class RegistrationForm(TailwindFormMixin, forms.ModelForm):
    class Meta:
        model = HackathonRegistration
        fields = ["motivation", "skills"]
        widgets = {
            "motivation": forms.Textarea(
                attrs={
                    "rows": 3,
                    "placeholder": "Pourquoi souhaitez-vous participer à ce hackathon ? Quels défis vous motivent ?",
                }
            ),
            "skills": forms.TextInput(
                attrs={
                    "placeholder": "Ex: Python, Django, React, Machine Learning, UI/UX (séparés par des virgules)",
                }
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.apply_tailwind_classes()


class ScheduleForm(TailwindFormMixin, forms.ModelForm):
    class Meta:
        model = HackathonSchedule
        fields = ["title", "description", "scheduled_at"]
        widgets = {
            "scheduled_at": forms.DateTimeInput(
                attrs={"type": "datetime-local"}, format="%Y-%m-%dT%H:%M"
            ),
            "description": forms.Textarea(attrs={"rows": 2}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.apply_tailwind_classes()
