from django.contrib import admin
from django.utils import timezone

from .models import Hackathon, HackathonFAQ, HackathonRegistration, HackathonSchedule


class HackathonScheduleInline(admin.TabularInline):
    model = HackathonSchedule
    extra = 1


class HackathonFAQInline(admin.TabularInline):
    model = HackathonFAQ
    extra = 1


class HackathonRegistrationInline(admin.TabularInline):
    model = HackathonRegistration
    extra = 0
    readonly_fields = (
        "participant",
        "ticket_code",
        "checked_in",
        "checked_in_at",
        "registered_at",
        "skills",
    )
    can_delete = True


@admin.register(Hackathon)
class HackathonAdmin(admin.ModelAdmin):
    list_display = (
        "title",
        "organizer",
        "category",
        "status",
        "mode",
        "start_date",
        "end_date",
        "is_published",
        "registered_count",
    )
    list_filter = ("status", "mode", "is_published", "category", "created_at")
    search_fields = ("title", "tagline", "description", "organizer__username")
    prepopulated_fields = {"slug": ("title",)}
    readonly_fields = ("created_at", "updated_at")
    date_hierarchy = "start_date"
    inlines = [HackathonScheduleInline, HackathonFAQInline, HackathonRegistrationInline]
    actions = ("publish_hackathons", "unpublish_hackathons")

    fieldsets = (
        (
            "General Information",
            {
                "fields": ("title", "slug", "tagline", "description", "category", "banner_image"),
            },
        ),
        (
            "Dates & Milestones",
            {
                "fields": ("registration_start", "registration_deadline", "start_date", "end_date"),
            },
        ),
        (
            "Mode & Venue",
            {
                "fields": ("mode", "location"),
            },
        ),
        (
            "Capacity & Team Constraints",
            {
                "fields": ("max_participants", "min_team_size", "max_team_size"),
            },
        ),
        (
            "Prizes & Difficulty",
            {
                "fields": ("prize_pool", "difficulty"),
            },
        ),
        (
            "Rules & Resources",
            {
                "fields": ("rules", "resources_link", "contact_email"),
            },
        ),
        (
            "Visibility & Ownership",
            {
                "fields": ("organizer", "status", "is_published"),
            },
        ),
        (
            "Metadata",
            {
                "fields": ("created_at", "updated_at"),
                "classes": ("collapse",),
            },
        ),
    )

    def registered_count(self, obj):
        return obj.registered_count

    registered_count.short_description = "Registered"

    @admin.action(description="Publish selected hackathons")
    def publish_hackathons(self, request, queryset):
        updated = queryset.update(is_published=True)
        self.message_user(request, f"{updated} hackathon(s) marked as published.")

    @admin.action(description="Unpublish selected hackathons (Draft)")
    def unpublish_hackathons(self, request, queryset):
        updated = queryset.update(is_published=False)
        self.message_user(request, f"{updated} hackathon(s) marked as unpublished.")


@admin.register(HackathonRegistration)
class HackathonRegistrationAdmin(admin.ModelAdmin):
    list_display = (
        "participant",
        "hackathon",
        "ticket_code",
        "checked_in",
        "checked_in_at",
        "registered_at",
    )
    list_filter = ("checked_in", "hackathon", "registered_at")
    search_fields = ("participant__username", "participant__email", "ticket_code")
    readonly_fields = ("registered_at", "ticket_code", "checked_in_at")
    actions = ("mark_checked_in", "reset_check_in")

    @admin.action(description="Mark selected registrations as Checked-In (Present)")
    def mark_checked_in(self, request, queryset):
        count = 0
        now = timezone.now()
        for reg in queryset:
            if not reg.checked_in:
                reg.checked_in = True
                reg.checked_in_at = now
                reg.save(update_fields=["checked_in", "checked_in_at"])
                count += 1
        self.message_user(request, f"{count} participant(s) marked as checked-in.")

    @admin.action(description="Reset check-in status for selected registrations")
    def reset_check_in(self, request, queryset):
        updated = queryset.update(checked_in=False, checked_in_at=None)
        self.message_user(request, f"{updated} participant(s) check-in reset.")
