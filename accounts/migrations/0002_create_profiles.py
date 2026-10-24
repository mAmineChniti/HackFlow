from django.conf import settings
from django.db import migrations


def create_profiles_for_existing_users(apps, schema_editor):
    User = apps.get_model(*settings.AUTH_USER_MODEL.split("."))
    Profile = apps.get_model("accounts", "Profile")

    existing_user_ids = set(Profile.objects.values_list("user_id", flat=True))
    new_profiles = [
        Profile(user_id=user_id)
        for user_id in User.objects.exclude(pk__in=existing_user_ids).values_list(
            "pk", flat=True
        )
    ]
    Profile.objects.bulk_create(new_profiles, batch_size=500)


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(
            create_profiles_for_existing_users,
            migrations.RunPython.noop,
        ),
    ]
