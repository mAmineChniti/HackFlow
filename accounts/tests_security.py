"""Regression tests for account security fixes.

Covers:
  * public signup can never grant an organizer/administrator role or the
    is_staff/is_superuser flags (privilege escalation);
  * self-service account settings cannot change the global role;
  * signup and logout enforce CSRF.
"""

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

from accounts.forms import HackFlowSignupForm
from accounts.models import Profile

User = get_user_model()

PASSWORD = "Sup3rSecret!pass"


class SignupRoleEscalationTests(TestCase):
    def test_privileged_roles_are_not_offered_at_signup(self):
        choices = dict(HackFlowSignupForm().fields["role"].choices)
        self.assertNotIn(Profile.Role.ADMIN, choices)
        self.assertNotIn(Profile.Role.ORGANIZER, choices)
        self.assertIn(Profile.Role.STUDENT, choices)

    def test_signup_with_forged_organizer_role_does_not_create_privileged_user(self):
        response = self.client.post(
            reverse("accounts:signup"),
            {
                "username": "mallory",
                "email": "mallory@example.com",
                "password1": PASSWORD,
                "password2": PASSWORD,
                "role": Profile.Role.ORGANIZER,
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertFalse(User.objects.filter(username="mallory").exists())

    def test_signup_with_forged_admin_role_does_not_create_user(self):
        response = self.client.post(
            reverse("accounts:signup"),
            {
                "username": "mallory2",
                "email": "mallory2@example.com",
                "password1": PASSWORD,
                "password2": PASSWORD,
                "role": Profile.Role.ADMIN,
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertFalse(User.objects.filter(username="mallory2").exists())

    def test_plain_signup_creates_student_without_staff_flags(self):
        self.client.post(
            reverse("accounts:signup"),
            {
                "username": "student_user",
                "email": "student@example.com",
                "password1": PASSWORD,
                "password2": PASSWORD,
                "role": Profile.Role.STUDENT,
            },
        )

        user = User.objects.get(username="student_user")
        self.assertEqual(user.profile.role, Profile.Role.STUDENT)
        self.assertFalse(user.is_staff)
        self.assertFalse(user.is_superuser)

    def test_signup_without_role_defaults_to_student(self):
        self.client.post(
            reverse("accounts:signup"),
            {
                "username": "no_role_user",
                "email": "norole@example.com",
                "password1": PASSWORD,
                "password2": PASSWORD,
            },
        )

        user = User.objects.get(username="no_role_user")
        self.assertEqual(user.profile.role, Profile.Role.STUDENT)
        self.assertFalse(user.is_superuser)


class ProfileRoleEscalationTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="student_lead",
            email="lead@example.com",
            password=PASSWORD,
        )
        self.user.profile.role = Profile.Role.STUDENT
        self.user.profile.save()
        self.client.force_login(self.user)

    def test_role_field_is_not_exposed_in_account_settings_form(self):
        response = self.client.get(reverse("accounts:profile"))
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("role", response.context["form"].fields)

    def test_posting_admin_role_does_not_change_role(self):
        response = self.client.post(
            reverse("accounts:profile"),
            {
                "username": "student_lead",
                "email": "lead@example.com",
                "first_name": "",
                "last_name": "",
                "role": Profile.Role.ADMIN,
            },
        )

        self.assertEqual(response.status_code, 302)
        self.user.refresh_from_db()
        self.user.profile.refresh_from_db()
        self.assertEqual(self.user.profile.role, Profile.Role.STUDENT)
        self.assertFalse(self.user.is_staff)
        self.assertFalse(self.user.is_superuser)

    def test_posting_organizer_role_does_not_change_role(self):
        self.client.post(
            reverse("accounts:profile"),
            {
                "username": "student_lead",
                "email": "lead@example.com",
                "first_name": "",
                "last_name": "",
                "role": Profile.Role.ORGANIZER,
            },
        )

        self.user.profile.refresh_from_db()
        self.assertEqual(self.user.profile.role, Profile.Role.STUDENT)


class CsrfEnforcementTests(TestCase):
    def setUp(self):
        self.csrf_client = Client(enforce_csrf_checks=True)

    def test_signup_rejects_post_without_csrf_token(self):
        response = self.csrf_client.post(
            reverse("accounts:signup"),
            {
                "username": "csrf_victim",
                "email": "victim@example.com",
                "password1": PASSWORD,
                "password2": PASSWORD,
                "role": Profile.Role.STUDENT,
            },
        )

        self.assertEqual(response.status_code, 403)
        self.assertFalse(User.objects.filter(username="csrf_victim").exists())

    def test_signup_accepts_post_with_csrf_token(self):
        # The token cookie is issued because the signup template renders
        # {% csrf_token %}.
        self.csrf_client.get(reverse("accounts:signup"))
        token = self.csrf_client.cookies["csrftoken"].value

        response = self.csrf_client.post(
            reverse("accounts:signup"),
            {
                "username": "legit_user",
                "email": "legit@example.com",
                "password1": PASSWORD,
                "password2": PASSWORD,
                "role": Profile.Role.STUDENT,
                "csrfmiddlewaretoken": token,
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertTrue(User.objects.filter(username="legit_user").exists())

    def test_logout_rejects_post_without_csrf_token(self):
        user = User.objects.create_user(
            username="logout_user",
            email="logout@example.com",
            password=PASSWORD,
        )
        self.csrf_client.force_login(user)

        response = self.csrf_client.post(reverse("accounts:logout"))

        self.assertEqual(response.status_code, 403)
        # Still authenticated: the forged request was rejected.
        self.assertEqual(self.csrf_client.session.get("_auth_user_id"), str(user.pk))
