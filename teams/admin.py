from django.contrib import admin

from .models import Invitation, SkillProfile, Team, TeamMember


class TeamMemberInline(admin.TabularInline):
    model = TeamMember
    extra = 1


@admin.register(Team)
class TeamAdmin(admin.ModelAdmin):
    list_display = ("name", "hackathon", "leader", "max_members", "created_at")
    list_filter = ("hackathon",)
    search_fields = ("name", "leader__username")
    raw_id_fields = ("hackathon", "leader")
    inlines = [TeamMemberInline]


@admin.register(SkillProfile)
class SkillProfileAdmin(admin.ModelAdmin):
    list_display = ("user", "main_role", "skills", "looking_for_team")
    list_filter = ("main_role", "looking_for_team")
    search_fields = ("user__username", "skills")
    raw_id_fields = ("user",)


@admin.register(Invitation)
class InvitationAdmin(admin.ModelAdmin):
    list_display = ("team", "invitee", "invited_by", "status", "created_at")
    list_filter = ("status",)
    search_fields = ("team__name", "invitee__username", "invited_by__username")
    raw_id_fields = ("team", "invitee", "invited_by")
