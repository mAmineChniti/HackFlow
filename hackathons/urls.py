from django.urls import path
from . import views

app_name = "hackathons"

urlpatterns = [
    path("", views.HackathonListView.as_view(), name="list"),
    path("create/", views.HackathonCreateView.as_view(), name="create"),
    path("ai-generate/", views.ai_generate_hackathon, name="ai_generate"),
    path("dashboard/", views.organizer_dashboard, name="dashboard"),
    path("<slug:slug>/", views.HackathonDetailView.as_view(), name="detail"),
    path("<slug:slug>/edit/", views.HackathonUpdateView.as_view(), name="update"),
    path("<slug:slug>/delete/", views.HackathonDeleteView.as_view(), name="delete"),
    path("<slug:slug>/ai-ideas/", views.ai_generate_ideas, name="ai_ideas"),
    path("<slug:slug>/badge/", views.participant_badge, name="participant_badge"),
    path("<slug:slug>/checkin/<str:ticket_code>/", views.organizer_checkin, name="organizer_checkin"),
    path("<slug:slug>/toggle-checkin/<str:ticket_code>/", views.toggle_checkin, name="toggle_checkin"),
    path("<slug:slug>/export-participants/", views.export_participants_csv, name="export_participants"),
    path("<slug:slug>/register/", views.register_participant, name="register"),
    path("<slug:slug>/unregister/", views.unregister_participant, name="unregister"),
]
