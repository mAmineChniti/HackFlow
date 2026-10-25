"""Reset the password of the `admin` account.

The password is never hardcoded: set TEST_ADMIN_PASSWORD before running.

    TEST_ADMIN_PASSWORD='choose-a-strong-one' python scripts/reset_admin.py
"""

import os
import sys

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "HackFlow.settings")

import django  # noqa: E402

django.setup()

from django.contrib.auth.models import User  # noqa: E402


def main() -> int:
    password = os.getenv("TEST_ADMIN_PASSWORD", "").strip()
    if len(password) < 12:
        print(
            "TEST_ADMIN_PASSWORD must be set to at least 12 characters.",
            file=sys.stderr,
        )
        return 1

    try:
        user = User.objects.get(username="admin")
    except User.DoesNotExist:
        print("User admin not found!", file=sys.stderr)
        return 1

    user.set_password(password)
    user.is_staff = True
    user.is_superuser = True
    user.is_active = True
    user.save()

    print("OK admin password reset to the value of TEST_ADMIN_PASSWORD.")
    print("is_staff:", user.is_staff)
    print("is_superuser:", user.is_superuser)
    print("is_active:", user.is_active)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
