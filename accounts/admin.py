from django.contrib import admin

from .models import Profile


@admin.register(Profile)
class ProfileAdmin(admin.ModelAdmin):
    list_display = ("user", "email_verified", "email_verified_at", "created_at")
    list_filter = ("email_verified",)
    search_fields = ("user__username", "user__email")
    readonly_fields = ("created_at", "updated_at")
    actions = ("mark_verified", "mark_unverified")

    @admin.action(description="Mark selected profiles as email verified")
    def mark_verified(self, request, queryset):
        for profile in queryset:
            profile.mark_email_verified()

    @admin.action(description="Mark selected profiles as email unverified")
    def mark_unverified(self, request, queryset):
        for profile in queryset:
            profile.reset_email_verification()
