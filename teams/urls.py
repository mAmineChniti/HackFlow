from django.urls import path

from . import views

app_name = "teams"

urlpatterns = [
    path("", views.TeamListView.as_view(), name="list"),
    path("new/", views.TeamCreateView.as_view(), name="create"),
    path("skills/", views.SkillProfileUpdateView.as_view(), name="skills"),
    path("invitations/", views.my_invitations, name="my_invitations"),
    path("invitations/<int:pk>/<str:action>/", views.respond_invitation, name="respond_invitation"),
    path("<int:pk>/invite/", views.send_invitation, name="send_invitation"),
    path("<int:pk>/", views.TeamDetailView.as_view(), name="detail"),
    path("<int:pk>/edit/", views.TeamUpdateView.as_view(), name="update"),
    path("<int:pk>/delete/", views.TeamDeleteView.as_view(), name="delete"),
    path("<int:pk>/join/", views.join_team, name="join"),
    path("<int:pk>/leave/", views.leave_team, name="leave"),
    path("<int:pk>/suggest/", views.suggest_teammates, name="suggest"),
]