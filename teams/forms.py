from django import forms
from django.core.exceptions import ValidationError

from .models import SkillProfile, Team, TeamMember

INPUT_CLASS = (
    "w-full rounded-md border border-input bg-background px-3 py-2 text-sm "
    "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
)


class StyledFormMixin:
    def _apply_styles(self):
        for field in self.fields.values():
            field.widget.attrs.setdefault("class", INPUT_CLASS)


class TeamForm(StyledFormMixin, forms.ModelForm):
    class Meta:
        model = Team
        fields = ["name", "description", "hackathon", "max_members"]
        widgets = {"description": forms.Textarea(attrs={"rows": 4})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._apply_styles()

    def clean_max_members(self):
        value = self.cleaned_data["max_members"]
        if self.instance.pk and value < self.instance.members.count():
            raise ValidationError(
                "Le maximum ne peut pas être inférieur au nombre de membres actuels."
            )
        return value


class JoinTeamForm(StyledFormMixin, forms.ModelForm):
    class Meta:
        model = TeamMember
        fields = ["role", "skills"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["role"].choices = [
            c for c in TeamMember.Role.choices if c[0] != TeamMember.Role.LEADER
        ]
        self._apply_styles()


class SkillProfileForm(StyledFormMixin, forms.ModelForm):
    class Meta:
        model = SkillProfile
        fields = ["main_role", "skills", "bio", "looking_for_team"]
        widgets = {"bio": forms.Textarea(attrs={"rows": 3})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._apply_styles()
        self.fields["looking_for_team"].widget.attrs["class"] = "size-4"
