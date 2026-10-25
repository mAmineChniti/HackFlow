"""
Data migration: fix HistoriqueProjet dates for existing records.

1. Replaces entry.date with the real date:
   - For "submitted" and "soumis_a_nouveau" actions: project.submitted_at (or project.date_soumission).
   - For "refuse" and "accepte" actions: project.reviewed_at (or project.date_decision).
   - For other status actions: project.reviewed_at.
2. If the real date does not exist (is None), deletes the line instead of keeping a fabricated date.
"""
from django.db import migrations


def forwards(apps, schema_editor):
    HistoriqueProjet = apps.get_model("projects", "HistoriqueProjet")

    for entry in list(HistoriqueProjet.objects.select_related("project").all()):
        project = entry.project
        action = entry.action

        # Pour les actions "soumis" (submitted) et "soumis à nouveau" (soumis_a_nouveau)
        if action in ("submitted", "soumis_a_nouveau"):
            real_date = getattr(project, "submitted_at", None) or getattr(project, "date_soumission", None)
            if real_date:
                entry.date = real_date
                entry.save(update_fields=["date"])
            else:
                # Si la vraie date n'existe pas, supprime cette ligne
                entry.delete()

        # Pour les actions "refusé" (refuse) et "accepté" (accepte)
        elif action in ("refuse", "accepte"):
            real_date = getattr(project, "reviewed_at", None) or getattr(project, "date_decision", None)
            if real_date:
                entry.date = real_date
                entry.save(update_fields=["date"])
            else:
                # Si la vraie date n'existe pas, supprime cette ligne
                entry.delete()

        # Pour toute autre action d'évaluation (en_evaluation, finaliste, laureat)
        else:
            real_date = getattr(project, "reviewed_at", None) or getattr(project, "date_decision", None)
            if real_date:
                entry.date = real_date
                entry.save(update_fields=["date"])
            else:
                entry.delete()


def backwards(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("projects", "0011_alter_historiqueprojet_date"),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
