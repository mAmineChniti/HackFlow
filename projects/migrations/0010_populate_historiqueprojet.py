"""
Data migration: populate HistoriqueProjet from existing Project fields.

For each project the migration creates:
  - A "submitted" row when submitted_at is set (or reviewed_at as fallback).
  - A "soumis_a_nouveau" row if the project was rejected and later re-submitted
    (heuristic: status == submitted and reviewed_at exists means at least one
    prior cycle).
  - A decision row (refuse / accepte / en_evaluation / finaliste / laureat)
    when reviewed_at is set.
"""
from django.db import migrations
from django.utils import timezone


def forwards(apps, schema_editor):
    Project = apps.get_model("projects", "Project")
    HistoriqueProjet = apps.get_model("projects", "HistoriqueProjet")

    ACTION_MAP = {
        "submitted":    "submitted",
        "under_review": "en_evaluation",
        "accepted":     "accepte",
        "rejected":     "refuse",
        "finalist":     "finaliste",
        "winner":       "laureat",
    }

    rows = []
    for project in Project.objects.select_related("created_by", "reviewed_by").all():
        # ── Submission entry ──────────────────────────────────────────────
        submitted_ts = project.submitted_at
        if submitted_ts:
            rows.append(HistoriqueProjet(
                project=project,
                action="submitted",
                acteur=project.created_by,
                commentaire="",
                date=submitted_ts,
            ))

        # ── Decision entry ────────────────────────────────────────────────
        status = project.status
        if project.reviewed_at and status in ACTION_MAP and status != "submitted":
            action_val = ACTION_MAP[status]
            rows.append(HistoriqueProjet(
                project=project,
                action=action_val,
                acteur=project.reviewed_by,
                commentaire=project.rejection_reason or "",
                date=project.reviewed_at,
            ))

    HistoriqueProjet.objects.bulk_create(rows)


def backwards(apps, schema_editor):
    HistoriqueProjet = apps.get_model("projects", "HistoriqueProjet")
    HistoriqueProjet.objects.all().delete()


class Migration(migrations.Migration):

    dependencies = [
        ("projects", "0009_historiqueprojet"),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
