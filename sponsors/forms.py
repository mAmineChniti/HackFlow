"""Modern Tailwind-styled forms for the HackFlow sponsorship module."""

from django import forms
from django.utils.translation import gettext_lazy as _

from .models import (
    Sponsor,
    Sponsorship,
    StatusChoices,
    TierChoices,
    ContributionTypeChoices,
    SECTOR_CHOICES,
)


INPUT_CLASSES = (
    "w-full rounded-lg border border-border/80 bg-background/60 px-3.5 py-2.5 "
    "text-sm text-foreground placeholder:text-muted-foreground/70 shadow-sm "
    "transition-colors focus:border-primary focus:outline-none focus:ring-1 focus:ring-primary"
)

SELECT_CLASSES = (
    "w-full rounded-lg border border-border/80 bg-background/80 px-3.5 py-2.5 "
    "text-sm text-foreground shadow-sm transition-colors focus:border-primary "
    "focus:outline-none focus:ring-1 focus:ring-primary"
)

TEXTAREA_CLASSES = (
    "w-full rounded-lg border border-border/80 bg-background/60 px-3.5 py-2.5 "
    "text-sm text-foreground placeholder:text-muted-foreground/70 shadow-sm "
    "transition-colors focus:border-primary focus:outline-none focus:ring-1 focus:ring-primary resize-y"
)

FILE_CLASSES = (
    "w-full rounded-lg border border-border/80 bg-background/60 px-3.5 py-2 text-sm "
    "text-foreground file:mr-4 file:rounded-md file:border-0 file:bg-primary file:px-3 file:py-1.5 "
    "file:text-xs file:font-semibold file:text-primary-foreground hover:file:bg-primary/90 focus:outline-none"
)


class SponsorForm(forms.ModelForm):
    """Create or update a sponsor company."""

    class Meta:
        model = Sponsor
        fields = [
            "name",
            "logo",
            "website",
            "sector",
            "description",
            "contact_name",
            "contact_email",
        ]
        widgets = {
            "name": forms.TextInput(
                attrs={
                    "class": INPUT_CLASSES,
                    "placeholder": "e.g. Google Cloud, Orange, Vermeg...",
                }
            ),
            "logo": forms.ClearableFileInput(
                attrs={
                    "class": FILE_CLASSES,
                    "accept": "image/*",
                }
            ),
            "website": forms.URLInput(
                attrs={
                    "class": INPUT_CLASSES,
                    "placeholder": "https://www.company.com",
                }
            ),
            "sector": forms.Select(attrs={"class": SELECT_CLASSES}),
            "description": forms.Textarea(
                attrs={
                    "class": TEXTAREA_CLASSES,
                    "rows": 3,
                    "placeholder": "Briefly describe the company and its commitment to technology or students...",
                }
            ),
            "contact_name": forms.TextInput(
                attrs={
                    "class": INPUT_CLASSES,
                    "placeholder": "e.g. Sarah Ben Ali (HR / DevRel Manager)",
                }
            ),
            "contact_email": forms.EmailInput(
                attrs={
                    "class": INPUT_CLASSES,
                    "placeholder": "partnership@company.com",
                }
            ),
        }


class SponsorshipForm(forms.ModelForm):
    """
    Create or update a sponsorship for a specific hackathon.
    The status field is excluded so status changes use the change_status() workflow.
    """

    class Meta:
        model = Sponsorship
        fields = [
            "sponsor",
            "hackathon",
            "tier",
            "amount",
            "contribution_type",
            "notes",
        ]
        widgets = {
            "sponsor": forms.Select(attrs={"class": SELECT_CLASSES}),
            "hackathon": forms.Select(attrs={"class": SELECT_CLASSES}),
            "tier": forms.Select(attrs={"class": SELECT_CLASSES}),
            "amount": forms.NumberInput(
                attrs={
                    "class": INPUT_CLASSES,
                    "placeholder": "e.g. 3500.000",
                    "step": "50",
                    "min": "0",
                }
            ),
            "contribution_type": forms.Select(attrs={"class": SELECT_CLASSES}),
            "notes": forms.Textarea(
                attrs={
                    "class": TEXTAREA_CLASSES,
                    "rows": 3,
                    "placeholder": "Negotiation details, previous contacts, and agreed benefits...",
                }
            ),
        }


class QuickStatusChangeForm(forms.Form):
    """Quick status change form for HTMX or drag-and-drop."""

    status = forms.ChoiceField(
        choices=StatusChoices.choices,
        widget=forms.Select(
            attrs={"class": "rounded-md border border-border bg-background px-2.5 py-1 text-xs"}
        ),
    )


class SponsorContactForm(forms.Form):
    """Send an email to a sponsor using a selected template."""

    TEMPLATE_CHOICES = [
        ("invitation", "Template: Sponsorship invitation"),
        ("relance", "Template: Follow-up"),
        ("remerciement", "Template: Thank you"),
    ]

    TONE_CHOICES = [
        ("professionnel", "Formal & professional"),
        ("amical", "Friendly & energetic"),
    ]

    template_key = forms.ChoiceField(
        choices=TEMPLATE_CHOICES,
        required=False,
        widget=forms.Select(attrs={"class": SELECT_CLASSES}),
        label=_("Message template"),
    )
    tone = forms.ChoiceField(
        choices=TONE_CHOICES,
        required=False,
        widget=forms.Select(attrs={"class": SELECT_CLASSES}),
        label=_("AI writing tone"),
    )
    subject = forms.CharField(
        max_length=255,
        widget=forms.TextInput(
            attrs={
                "class": INPUT_CLASSES,
                "placeholder": "Your message subject...",
            }
        ),
        label=_("Subject"),
    )
    message = forms.CharField(
        widget=forms.Textarea(
            attrs={
                "class": TEXTAREA_CLASSES,
                "rows": 8,
                "placeholder": "Message to send to the sponsor contact...",
            }
        ),
        label=_("Message"),
    )
    ai_generated = forms.BooleanField(
        required=False,
        widget=forms.HiddenInput(),
    )
