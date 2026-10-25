from django.urls import path
from . import views

app_name = "projects"

urlpatterns = [
    path("", views.project_list, name="project_list"),
    path("create/", views.project_create, name="project_create"),
    path("admin-dashboard/", views.project_admin_dashboard, name="admin_dashboard"),
    path("admin-dashboard/export-csv/", views.export_projects_csv, name="export_csv"),
    path("admin-dashboard/export-pdf/", views.export_projects_pdf, name="export_pdf"),
    path("admin-dashboard/<slug:slug>/review/", views.project_admin_review, name="admin_review"),
    path("admin-dashboard/<slug:slug>/score/", views.project_score, name="project_score"),
    path("ai/detect-category/", views.project_ai_detect_category, name="ai_detect_category"),
    path("<slug:slug>/", views.project_detail, name="project_detail"),
    path("<slug:slug>/ai-analyze/", views.project_ai_analyze, name="ai_analyze"),
    path("<slug:slug>/submit/", views.project_submit, name="project_submit"),
    path("<slug:slug>/edit/", views.project_update, name="project_update"),
    path("<slug:slug>/delete/", views.project_delete, name="project_delete"),
    path("<slug:slug>/members/add/", views.member_add, name="member_add"),
    path("<slug:slug>/members/<int:member_id>/remove/", views.member_remove, name="member_remove"),
    path("<slug:slug>/mentor-advice/", views.project_add_mentor_advice, name="project_add_mentor_advice"),
]
