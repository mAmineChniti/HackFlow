import django
import os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'HackFlow.settings')
django.setup()

from django.contrib.auth.models import User
from accounts.models import Profile

print("=" * 60)
print("LISTE DES UTILISATEURS HACKFLOW")
print("=" * 60)
users = User.objects.all().select_related('profile')
for u in users:
    role = "no profile"
    try:
        role = u.profile.role
    except:
        pass
    print(f"  username: {u.username}")
    print(f"  role:     {role}")
    print(f"  staff:    {u.is_staff} | superuser: {u.is_superuser}")
    print("-" * 40)
print(f"\nTotal: {users.count()} utilisateur(s)")
