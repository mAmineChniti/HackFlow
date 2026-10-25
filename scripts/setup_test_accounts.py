"""Seed local test accounts for HackFlow.

Passwords are never hardcoded: set TEST_ACCOUNT_PASSWORD before running, e.g.

    TEST_ACCOUNT_PASSWORD='choose-a-strong-one' python scripts/setup_test_accounts.py

The script refuses to run against a production settings module (DJANGO_DEBUG
not true) unless ALLOW_PROD_SEED=1 is set explicitly, because it creates a
superuser account.
"""

import os
import sys

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "HackFlow.settings")

import django  # noqa: E402

django.setup()

from django.conf import settings  # noqa: E402
from django.contrib.auth.models import User  # noqa: E402

from accounts.models import Profile  # noqa: E402

# (username, role, is_staff, is_superuser)
TEST_ACCOUNTS = [
    ("admin", "admin", True, True),
    ("organizer", "organizer", True, False),
    ("judge", "judge", False, False),
    ("mentor", "mentor", False, False),
    ("sarah", "student", False, False),
    ("alex", "student", False, False),
    ("Etudiant1", "student", False, False),
]


def main() -> int:
    if not settings.DEBUG and os.getenv("ALLOW_PROD_SEED") != "1":
        print(
            "Refusing to seed accounts while DJANGO_DEBUG is false.\n"
            "This creates a superuser with a shared password. Set "
            "ALLOW_PROD_SEED=1 only if you really mean it.",
            file=sys.stderr,
        )
        return 1

    password = os.getenv("TEST_ACCOUNT_PASSWORD", "").strip()
    if len(password) < 12:
        print(
            "TEST_ACCOUNT_PASSWORD must be set to at least 12 characters.",
            file=sys.stderr,
        )
        return 1

    print("=" * 55)
    print("REINITIALISATION DES COMPTES DE TEST HACKFLOW")
    print("=" * 55)

    for username, role, is_staff, is_superuser in TEST_ACCOUNTS:
        user, created = User.objects.get_or_create(
            username=username,
            defaults={
                "email": f"{username.lower()}@hackflow.tn",
                "is_staff": is_staff,
                "is_superuser": is_superuser,
                "is_active": True,
            },
        )
        user.set_password(password)
        user.is_staff = is_staff
        user.is_superuser = is_superuser
        user.is_active = True
        if not user.email:
            user.email = f"{username.lower()}@hackflow.tn"
        user.save()

        profile, _ = Profile.objects.get_or_create(user=user)
        profile.role = role
        profile.email_verified = True
        profile.save()

        status = "CREATED" if created else "UPDATED"
        print(f"  OK [{status:7}] {username:15} | role: {role:12}")

    print("=" * 55)
    print("Tous les comptes sont prets (mot de passe: TEST_ACCOUNT_PASSWORD).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
