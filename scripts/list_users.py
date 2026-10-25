"""Print every HackFlow user with their role and staff flags (read-only)."""

import os

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "HackFlow.settings")

import django  # noqa: E402

django.setup()

from django.contrib.auth.models import User  # noqa: E402


def main() -> None:
    print("=" * 60)
    print("LISTE DES UTILISATEURS HACKFLOW")
    print("=" * 60)
    users = User.objects.select_related("profile").all()
    for user in users:
        profile = getattr(user, "profile", None)
        role = profile.role if profile else "no profile"
        print(f"  username: {user.username}")
        print(f"  role:     {role}")
        print(f"  staff:    {user.is_staff} | superuser: {user.is_superuser}")
        print("-" * 40)
    print(f"\nTotal: {users.count()} utilisateur(s)")


if __name__ == "__main__":
    main()
