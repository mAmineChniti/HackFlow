import os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'HackFlow.settings')

import django
django.setup()

from django.contrib.auth.models import User

# Reset password for admin
try:
    u = User.objects.get(username='admin')
    u.set_password('admin123')
    u.is_staff = True
    u.is_superuser = True
    u.is_active = True
    u.save()
    print("OK admin password set to: admin123")
    print("is_staff:", u.is_staff)
    print("is_superuser:", u.is_superuser)
    print("is_active:", u.is_active)
except User.DoesNotExist:
    print("User admin not found!")
