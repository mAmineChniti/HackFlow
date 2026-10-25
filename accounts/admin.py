from django.contrib import admin
from django.utils.translation import gettext_lazy as _

from .models import Profile


class RoleListFilter(admin.SimpleListFilter):
    title = _("By Role")
    parameter_name = "role"

    def lookups(self, request, model_admin):
        return Profile.Role.choices

    def queryset(self, request, queryset):
        if self.value():
            return queryset.filter(role=self.value())
        return queryset


@admin.register(Profile)
class ProfileAdmin(admin.ModelAdmin):
    list_display = ("user", "role", "email_verified", "email_verified_at", "created_at")
    list_editable = ("role",)
    list_filter = (RoleListFilter, "email_verified")
    search_fields = ("user__username", "user__email")
    readonly_fields = ("created_at", "updated_at")
    actions = (
        "set_role_student",
        "set_role_organizer",
        "set_role_judge",
        "set_role_mentor",
        "set_role_admin",
        "mark_verified",
        "mark_unverified",
    )

    @admin.action(description="Changer le rôle en: Student / Participant")
    def set_role_student(self, request, queryset):
        queryset.update(role=Profile.Role.STUDENT)

    @admin.action(description="Changer le rôle en: Organizer")
    def set_role_organizer(self, request, queryset):
        queryset.update(role=Profile.Role.ORGANIZER)

    @admin.action(description="Changer le rôle en: Judge / Jury")
    def set_role_judge(self, request, queryset):
        queryset.update(role=Profile.Role.JUDGE)

    @admin.action(description="Changer le rôle en: Mentor")
    def set_role_mentor(self, request, queryset):
        queryset.update(role=Profile.Role.MENTOR)

    @admin.action(description="Changer le rôle en: Administrator")
    def set_role_admin(self, request, queryset):
        for profile in queryset:
            profile.role = Profile.Role.ADMIN
            profile.save(update_fields=["role"])
            profile.user.is_staff = True
            profile.user.is_superuser = True
            profile.user.save(update_fields=["is_staff", "is_superuser"])

    @admin.action(description="Mark selected profiles as email verified")
    def mark_verified(self, request, queryset):
        for profile in queryset:
            profile.mark_email_verified()

    @admin.action(description="Mark selected profiles as email unverified")
    def mark_unverified(self, request, queryset):
        for profile in queryset:
            profile.reset_email_verification()
