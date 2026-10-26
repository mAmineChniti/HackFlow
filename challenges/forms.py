from django import forms

from .models import Challenge, ChallengeSubmission


class ChallengeForm(forms.ModelForm):
    class Meta:
        model = Challenge
        fields = ["title", "description", "category", "difficulty", "points", "status", "hackathon"]
        widgets = {
            "description": forms.Textarea(attrs={"rows": 6}),
            "title": forms.TextInput(attrs={"placeholder": "Ex: Rate Limit Bypass"}),
            "category": forms.TextInput(attrs={"placeholder": "Ex: Web Security, AI / ML"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            widget = field.widget
            if isinstance(widget, forms.Textarea):
                widget.attrs["class"] = (
                    "flex min-h-[90px] w-full rounded-md border border-input bg-transparent "
                    "px-3 py-2 text-sm shadow-xs placeholder:text-muted-foreground "
                    "focus-visible:outline-hidden focus-visible:ring-1 focus-visible:ring-ring"
                )
            elif isinstance(widget, (forms.Select, forms.SelectMultiple)):
                widget.attrs["class"] = (
                    "flex h-9 w-full rounded-md border border-input bg-background px-3 py-1 "
                    "text-sm shadow-xs focus-visible:outline-hidden focus-visible:ring-1 "
                    "focus-visible:ring-ring"
                )
            else:
                widget.attrs["class"] = (
                    "flex h-9 w-full rounded-md border border-input bg-transparent px-3 py-1 "
                    "text-sm shadow-xs placeholder:text-muted-foreground "
                    "focus-visible:outline-hidden focus-visible:ring-1 focus-visible:ring-ring"
                )


class ChallengeSubmissionForm(forms.ModelForm):
    class Meta:
        model = ChallengeSubmission
        fields = ["solution"]
        widgets = {
            "solution": forms.Textarea(
                attrs={
                    "rows": 10,
                    "placeholder": "Describe your approach, code, or answer. Be specific.",
                }
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["solution"].widget.attrs["class"] = (
            "flex min-h-[180px] w-full rounded-md border border-input bg-transparent "
            "px-3 py-2 text-sm shadow-xs placeholder:text-muted-foreground "
            "focus-visible:outline-hidden focus-visible:ring-1 focus-visible:ring-ring font-mono"
        )
