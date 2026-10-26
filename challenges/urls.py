from django.urls import path
from . import views

app_name = "challenges"

urlpatterns = [
    path("", views.ChallengeListView.as_view(), name="list"),
    path("create/", views.ChallengeCreateView.as_view(), name="create"),
    path("<slug:slug>/", views.ChallengeDetailView.as_view(), name="detail"),
    path("<slug:slug>/edit/", views.ChallengeUpdateView.as_view(), name="update"),
    path("<slug:slug>/delete/", views.ChallengeDeleteView.as_view(), name="delete"),
    path("<slug:slug>/submit/", views.challenge_submit, name="submit"),
    path("<slug:slug>/hint/", views.challenge_hint_view, name="hint"),
]
