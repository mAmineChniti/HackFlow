"""
Configuration des URLs du module Gestion des Sponsors — HackFlow ESPRIT.

Routes publiques et sécurisées (Organisateur / Staff).
"""

from django.urls import path
from . import views

app_name = "sponsors"

urlpatterns = [
    # Page publique "Nos Sponsors" (accessible à tous)
    path("", views.PublicSponsorListView.as_view(), name="public_list"),
    # Tableau de bord Organisateur / Staff
    path("dashboard/", views.SponsorDashboardView.as_view(), name="dashboard"),
    # Annuaire des entreprises sponsors
    path("directory/", views.SponsorDirectoryView.as_view(), name="sponsor_list"),
    path("export/excel/", views.SponsorshipExportExcelView.as_view(), name="sponsor_export_excel"),
    path("new/", views.SponsorCreateView.as_view(), name="sponsor_create"),
    path("<int:pk>/", views.SponsorDetailView.as_view(), name="sponsor_detail"),
    path("<int:pk>/edit/", views.SponsorUpdateView.as_view(), name="sponsor_update"),
    path("<int:pk>/delete/", views.SponsorDeleteView.as_view(), name="sponsor_delete"),
    path("<int:pk>/contact/", views.SponsorContactView.as_view(), name="sponsor_contact"),
    path(
        "<int:pk>/ai-generate/",
        views.SponsorAIGenerateEmailView.as_view(),
        name="sponsor_ai_generate_email",
    ),
    path(
        "recommendations/<int:hackathon_id>/",
        views.SponsorRecommendationsView.as_view(),
        name="sponsor_recommendations",
    ),
    # Gestion des conventions de sponsoring (Sponsorships)
    path("sponsorships/new/", views.SponsorshipCreateView.as_view(), name="sponsorship_create"),
    path(
        "sponsorships/<int:pk>/edit/",
        views.SponsorshipUpdateView.as_view(),
        name="sponsorship_update",
    ),
    path(
        "sponsorships/<int:pk>/delete/",
        views.SponsorshipDeleteView.as_view(),
        name="sponsorship_delete",
    ),
    # Action rapide de changement de statut (compatible HTMX)
    path(
        "sponsorships/<int:pk>/change-status/",
        views.SponsorshipChangeStatusView.as_view(),
        name="sponsorship_change_status",
    ),
]
