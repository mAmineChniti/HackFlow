"""
Formulaires pour le module Gestion des Sponsors — HackFlow ESPRIT.

Formulaires modernes stylisés avec les classes Tailwind CSS de HackFlow.
"""

from django import forms
from django.utils.translation import gettext_lazy as _

from .models import Sponsor, Sponsorship, StatusChoices, TierChoices, ContributionTypeChoices, SECTOR_CHOICES


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
    """Formulaire de création et modification d'une entreprise partenaire (Sponsor)."""

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
            "name": forms.TextInput(attrs={
                "class": INPUT_CLASSES,
                "placeholder": "ex: Google Cloud, Orange, Vermeg...",
            }),
            "logo": forms.ClearableFileInput(attrs={
                "class": FILE_CLASSES,
                "accept": "image/*",
            }),
            "website": forms.URLInput(attrs={
                "class": INPUT_CLASSES,
                "placeholder": "https://www.entreprise.com",
            }),
            "sector": forms.Select(attrs={"class": SELECT_CLASSES}),
            "description": forms.Textarea(attrs={
                "class": TEXTAREA_CLASSES,
                "rows": 3,
                "placeholder": "Courte description de l'entreprise et de son engagement tech/étudiant...",
            }),
            "contact_name": forms.TextInput(attrs={
                "class": INPUT_CLASSES,
                "placeholder": "ex: Sarah Ben Ali (HR / DevRel Manager)",
            }),
            "contact_email": forms.EmailInput(attrs={
                "class": INPUT_CLASSES,
                "placeholder": "partenariat@entreprise.com",
            }),
        }


class SponsorshipForm(forms.ModelForm):
    """
    Formulaire pour créer ou modifier un partenariat spécifique à un hackathon.
    Le champ 'status' est exclu pour forcer le passage par le workflow change_status().
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
            "amount": forms.NumberInput(attrs={
                "class": INPUT_CLASSES,
                "placeholder": "ex: 3500.000",
                "step": "50",
                "min": "0",
            }),
            "contribution_type": forms.Select(attrs={"class": SELECT_CLASSES}),
            "notes": forms.Textarea(attrs={
                "class": TEXTAREA_CLASSES,
                "rows": 3,
                "placeholder": "Détails de la négociation, contacts passés, contreparties convenues...",
            }),
        }


class QuickStatusChangeForm(forms.Form):
    """Formulaire rapide de changement de statut pour HTMX ou drag-and-drop."""
    status = forms.ChoiceField(
        choices=StatusChoices.choices,
        widget=forms.Select(attrs={"class": "rounded-md border border-border bg-background px-2.5 py-1 text-xs"}),
    )


class SponsorContactForm(forms.Form):
    """Formulaire d'envoi d'email à un sponsor avec choix de modèle."""

    TEMPLATE_CHOICES = [
        ("invitation", "Modèle : Invitation à sponsoriser"),
        ("relance", "Modèle : Relance de proposition"),
        ("remerciement", "Modèle : Remerciement"),
    ]

    TONE_CHOICES = [
        ("professionnel", "Ton formel & professionnel"),
        ("amical", "Ton convivial & dynamique"),
    ]

    template_key = forms.ChoiceField(
        choices=TEMPLATE_CHOICES,
        required=False,
        widget=forms.Select(attrs={"class": SELECT_CLASSES}),
        label=_("Modèle de message"),
    )
    tone = forms.ChoiceField(
        choices=TONE_CHOICES,
        required=False,
        widget=forms.Select(attrs={"class": SELECT_CLASSES}),
        label=_("Ton de rédaction (IA)"),
    )
    subject = forms.CharField(
        max_length=255,
        widget=forms.TextInput(attrs={
            "class": INPUT_CLASSES,
            "placeholder": "Objet de votre message...",
        }),
        label=_("Objet"),
    )
    message = forms.CharField(
        widget=forms.Textarea(attrs={
            "class": TEXTAREA_CLASSES,
            "rows": 8,
            "placeholder": "Contenu du message envoyé au contact du sponsor...",
        }),
        label=_("Message"),
    )
    ai_generated = forms.BooleanField(
        required=False,
        widget=forms.HiddenInput(),
    )

