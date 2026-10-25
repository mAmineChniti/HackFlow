from django.contrib import admin

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
    readonly_fields = ("participant", "registered_at", "skills")


@admin.register(Hackathon)
class HackathonAdmin(admin.ModelAdmin):
    list_display = (
        "title",
        "category",
        "status",
        "mode",
        "start_date",
        "end_date",
        "is_published",
        "registered_count",
    )
    list_filter = ("status", "mode", "is_published", "category")
    search_fields = ("title", "tagline", "description")
    prepopulated_fields = {"slug": ("title",)}
    readonly_fields = ("created_at", "updated_at")
    inlines = [HackathonScheduleInline, HackathonFAQInline, HackathonRegistrationInline]

    fieldsets = (
        ("General Information", {
            "fields": ("title", "slug", "tagline", "description", "category", "banner_image"),
        }),
        ("Dates & Milestones", {
            "fields": ("registration_start", "registration_deadline", "start_date", "end_date"),
        }),
        ("Mode & Venue", {
            "fields": ("mode", "location"),
        }),
        ("Capacity & Team Constraints", {
            "fields": ("max_participants", "min_team_size", "max_team_size"),
        }),
        ("Prizes & Difficulty", {
            "fields": ("prize_pool", "difficulty"),
        }),
        ("Rules & Resources", {
            "fields": ("rules", "resources_link", "contact_email"),
        }),
        ("Visibility & Ownership", {
            "fields": ("organizer", "status", "is_published"),
        }),
        ("Metadata", {
            "fields": ("created_at", "updated_at"),
            "classes": ("collapse",),
        }),
    )

    def registered_count(self, obj):
        return obj.registered_count
    registered_count.short_description = "Registered"


@admin.register(HackathonRegistration)
class HackathonRegistrationAdmin(admin.ModelAdmin):
    list_display = ("participant", "hackathon", "registered_at", "skills")
    list_filter = ("hackathon",)
    search_fields = ("participant__username", "participant__email")
