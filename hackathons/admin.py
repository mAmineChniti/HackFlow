# TEMPORAIRE — Admin minimal pour le modèle Hackathon stub.
# Ne pas inclure dans la PR du module sponsors.

from django.contrib import admin

from .models import Hackathon


@admin.register(Hackathon)
class HackathonAdmin(admin.ModelAdmin):
    list_display = ("name", "theme", "start_date", "end_date")
    search_fields = ("name", "theme")
