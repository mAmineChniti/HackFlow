import os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'HackFlow.settings')
import django
django.setup()

from django.contrib.auth.models import User
from accounts.models import Profile

# Comptes de test avec roles fixes - passwords from environment or defaults
test_accounts = [
    # (username, password_env_var, password_default, role, is_staff, is_superuser)
    ('admin',         'TEST_ADMIN_PASSWORD',         'admin123',      'admin',     True,  True),
    ('organizer',     'TEST_ORGANIZER_PASSWORD',     'organizer123',  'organizer', True,  False),
    ('judge',         'TEST_JUDGE_PASSWORD',         'judge123',      'judge',     False, False),
    ('mentor',        'TEST_MENTOR_PASSWORD',        'mentor123',     'mentor',    False, False),
    ('sarah',         'TEST_SARAH_PASSWORD',         'sarah123',      'student',   False, False),
    ('alex',          'TEST_ALEX_PASSWORD',          'alex123',       'student',   False, False),
    ('Etudiant1',     'TEST_ETUDIANT1_PASSWORD',     'etudiant123',   'student',   False, False),
]

print("=" * 55)
print("REINITIALISATION DES COMPTES DE TEST HACKFLOW")
print("=" * 55)

for username, env_var, default_password, role, is_staff, is_superuser in test_accounts:
    password = os.getenv(env_var, default_password)
    try:
        u = User.objects.get(username=username)
        u.set_password(password)
        u.is_staff = is_staff
        u.is_superuser = is_superuser
        u.is_active = True
        u.save()

        # Mettre a jour le profil
        try:
            p = u.profile
            p.role = role
            p.save()
        except Exception:
            Profile.objects.create(user=u, role=role)

        print(f"  OK  {username:15} | role: {role:12}")
    except User.DoesNotExist:
        print(f"  --  {username:15} | NOT FOUND, skipping")

print("=" * 55)
print("Tous les comptes sont prets !")
print("Note: Use environment variables to override default passwords.")
