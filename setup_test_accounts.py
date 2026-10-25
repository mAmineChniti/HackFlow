import os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'HackFlow.settings')
import django
django.setup()

from django.contrib.auth.models import User
from accounts.models import Profile

# Comptes de test avec roles fixes
test_accounts = [
    # (username, password, role, is_staff, is_superuser)
    ('admin',         'admin123',      'admin',     True,  True),
    ('organizer',     'organizer123',  'organizer', True,  False),
    ('judge',         'judge123',      'judge',     False, False),
    ('mentor',        'mentor123',     'mentor',    False, False),
    ('sarah',         'sarah123',      'student',   False, False),
    ('alex',          'alex123',       'student',   False, False),
    ('Etudiant1',     'etudiant123',   'student',   False, False),
]

print("=" * 55)
print("REINITIALISATION DES COMPTES DE TEST HACKFLOW")
print("=" * 55)

for username, password, role, is_staff, is_superuser in test_accounts:
    u, created = User.objects.get_or_create(
        username=username,
        defaults={
            "email": f"{username.lower()}@hackflow.tn",
            "is_staff": is_staff,
            "is_superuser": is_superuser,
            "is_active": True,
        },
    )
    u.set_password(password)
    u.is_staff = is_staff
    u.is_superuser = is_superuser
    u.is_active = True
    if not u.email:
        u.email = f"{username.lower()}@hackflow.tn"
    u.save()

    p, _ = Profile.objects.get_or_create(user=u)
    p.role = role
    p.email_verified = True
    p.save()

    status_str = "CREATED" if created else "UPDATED"
    print(f"  OK [{status_str:7}] {username:15} | role: {role:12} | pass: {password}")

print("=" * 55)
print("Tous les comptes sont prets !")
