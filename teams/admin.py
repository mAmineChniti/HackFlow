from django.contrib import admin

from .models import Hackathon, Team, TeamMember, SkillProfile


class TeamMemberInline(admin.TabularInline):
    model = TeamMember
    extra = 1


@admin.register(Hackathon)
class HackathonAdmin(admin.ModelAdmin):
    list_display = ("title", "start_date", "end_date")


@admin.register(Team)
class TeamAdmin(admin.ModelAdmin):
    list_display = ("name", "hackathon", "leader", "max_members", "created_at")
    list_filter = ("hackathon",)
    search_fields = ("name", "leader__username")
    inlines = [TeamMemberInline]

@admin.register(SkillProfile)
class SkillProfileAdmin(admin.ModelAdmin):
    list_display = ("user", "main_role", "skills", "looking_for_team")
    list_filter = ("main_role", "looking_for_team")
    search_fields = ("user__username", "skills")