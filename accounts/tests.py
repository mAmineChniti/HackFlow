import re

from django.contrib.auth import get_user_model
from django.core import mail
from django.core.cache import cache
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode

from .models import Profile
from .tokens import email_verification_token

User = get_user_model()


@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
class AuthenticationTests(TestCase):
    password = "S3curePassw0rd!"

    def setUp(self):
        cache.clear()
        mail.outbox.clear()
        self.user = User.objects.create_user(
            username="flowhacker",
            email="hacker@example.com",
            password=self.password,
        )
        self.profile = self.user.profile

    def verification_url(self, user=None):
        user = user or self.user
        return reverse(
            "accounts:verify_email",
            kwargs={
                "uidb64": urlsafe_base64_encode(force_bytes(user.pk)),
                "token": email_verification_token.make_token(user),
            },
        )

    def test_auth_pages_render(self):
        cases = {
            "login": "accounts/login.html",
            "signup": "accounts/signup.html",
            "password_reset": "accounts/password_reset_form.html",
        }
        for url_name, template_name in cases.items():
            with self.subTest(url_name=url_name):
                response = self.client.get(reverse(f"accounts:{url_name}"))
                self.assertEqual(response.status_code, 200)
                self.assertTemplateUsed(response, template_name)
                self.assertNotContains(response, "{%")
                self.assertNotContains(response, "field.field")

    def test_signup_creates_and_logs_in_user(self):
        response = self.client.post(
            reverse("accounts:signup"),
            {
                "username": "newbuilder",
                "email": "NewBuilder@Example.com",
                "password1": "An0therStrongPass!",
                "password2": "An0therStrongPass!",
            },
        )
        self.assertRedirects(response, reverse("core:home"))

        user = User.objects.get(username="newbuilder")
        self.assertEqual(user.email, "newbuilder@example.com")
        self.assertEqual(int(self.client.session["_auth_user_id"]), user.pk)

    def test_signup_rejects_duplicate_email(self):
        response = self.client.post(
            reverse("accounts:signup"),
            {
                "username": "someoneelse",
                "email": "HACKER@example.com",
                "password1": "An0therStrongPass!",
                "password2": "An0therStrongPass!",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "An account with that email already exists.")

    def test_signup_rejects_duplicate_username_case_insensitively(self):
        response = self.client.post(
            reverse("accounts:signup"),
            {
                "username": "FlowHacker",
                "email": "another@example.com",
                "password1": "An0therStrongPass!",
                "password2": "An0therStrongPass!",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "That username is already taken.")

    def test_signup_rejects_username_matching_existing_email(self):
        response = self.client.post(
            reverse("accounts:signup"),
            {
                "username": self.user.email,
                "email": "another@example.com",
                "password1": "An0therStrongPass!",
                "password2": "An0therStrongPass!",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "That username is already taken.")

    def test_signup_rejects_email_matching_existing_username(self):
        User.objects.create_user(
            username="alias@example.com",
            email="alias-account@example.com",
            password=self.password,
        )

        response = self.client.post(
            reverse("accounts:signup"),
            {
                "username": "anotherbuilder",
                "email": "alias@example.com",
                "password1": "An0therStrongPass!",
                "password2": "An0therStrongPass!",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "An account with that email already exists.")

    def test_login_with_username(self):
        response = self.client.post(
            reverse("accounts:login"),
            {"username": "flowhacker", "password": self.password},
        )
        self.assertRedirects(response, reverse("core:home"))
        self.assertEqual(int(self.client.session["_auth_user_id"]), self.user.pk)

    def test_login_with_email_case_insensitively(self):
        response = self.client.post(
            reverse("accounts:login"),
            {"username": "HACKER@EXAMPLE.COM", "password": self.password},
        )
        self.assertRedirects(response, reverse("core:home"))
        self.assertEqual(int(self.client.session["_auth_user_id"]), self.user.pk)

    def test_login_honors_next_url(self):
        response = self.client.post(
            reverse("accounts:login") + "?next=" + reverse("accounts:password_reset"),
            {"username": "flowhacker", "password": self.password},
        )
        self.assertRedirects(response, reverse("accounts:password_reset"))

    def test_invalid_login_shows_error(self):
        response = self.client.post(
            reverse("accounts:login"),
            {"username": "flowhacker", "password": "wrong-password"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "don&#x27;t match")

    def test_invalid_forms_do_not_echo_passwords(self):
        secret = "DontEchoThisSecret!"

        response = self.client.post(
            reverse("accounts:login"),
            {"username": self.user.username, "password": secret},
        )
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, secret)

        self.client.force_login(self.user)
        response = self.client.post(
            reverse("accounts:password_change"),
            {
                "old_password": secret,
                "new_password1": secret,
                "new_password2": secret,
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, secret)

        response = self.client.post(
            reverse("accounts:delete_account"),
            {"password": secret, "confirm": "on"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, secret)

    def test_logout_is_post_only_and_clears_session(self):
        self.client.force_login(self.user)

        response = self.client.get(reverse("accounts:logout"))
        self.assertEqual(response.status_code, 405)
        self.assertIn("_auth_user_id", self.client.session)

        response = self.client.post(reverse("accounts:logout"))
        self.assertRedirects(
            response,
            reverse("core:home"),
            fetch_redirect_response=False,
        )
        self.assertNotIn("_auth_user_id", self.client.session)

        response = self.client.get(reverse("core:home"))
        self.assertContains(response, "See you next build.")

    def test_password_reset_sends_link_and_updates_password(self):
        response = self.client.post(
            reverse("accounts:password_reset"),
            {"email": self.user.email},
        )
        self.assertRedirects(response, reverse("accounts:password_reset_done"))
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("This link expires in 3 days.", mail.outbox[0].body)

        response = self.client.get(reverse("accounts:password_reset"))
        self.assertContains(response, "Reset links expire after 3 days.")

        alternatives = mail.outbox[0].alternatives
        self.assertTrue(
            any(content_type == "text/html" for _, content_type in alternatives)
        )
        html_body = next(
            content
            for content, content_type in alternatives
            if content_type == "text/html"
        )
        self.assertIn("Reset your password", html_body)

        match = re.search(
            r"http://testserver(/accounts/password-reset/confirm/[^\s]+)",
            mail.outbox[0].body,
        )
        self.assertIsNotNone(match)

        response = self.client.get(match.group(1), follow=True)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["validlink"])
        self.assertEqual(response.context["expires_days"], 3)

        new_password = "R3setAndStronger!"
        response = self.client.post(
            response.request["PATH_INFO"],
            {"new_password1": new_password, "new_password2": new_password},
        )
        self.assertRedirects(response, reverse("accounts:password_reset_complete"))

        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password(new_password))

    def test_password_reset_does_not_leak_unknown_email(self):
        response = self.client.post(
            reverse("accounts:password_reset"),
            {"email": "nobody@example.com"},
        )
        self.assertRedirects(response, reverse("accounts:password_reset_done"))
        self.assertEqual(len(mail.outbox), 0)

    def test_navbar_reflects_authentication_state(self):
        response = self.client.get(reverse("core:home"))
        self.assertContains(response, reverse("accounts:login"))
        self.assertContains(response, reverse("accounts:signup"))

        self.client.force_login(self.user)
        response = self.client.get(reverse("core:home"))
        self.assertContains(response, self.user.username)
        self.assertContains(response, reverse("accounts:logout"))
        self.assertContains(response, reverse("accounts:profile"))
        self.assertContains(response, "Account settings")
        self.assertContains(response, "Verify email")

    def test_signup_sends_verification_email_and_verifies_address(self):
        response = self.client.post(
            reverse("accounts:signup"),
            {
                "username": "newbuilder",
                "email": "NewBuilder@Example.com",
                "password1": "An0therStrongPass!",
                "password2": "An0therStrongPass!",
            },
        )
        self.assertRedirects(response, reverse("core:home"))

        user = User.objects.get(username="newbuilder")
        self.assertFalse(user.profile.email_verified)
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ["newbuilder@example.com"])
        self.assertIn("Verify your HackFlow email", mail.outbox[0].subject)

        match = re.search(
            r"http://testserver(/accounts/verify-email/[^\s]+)",
            mail.outbox[0].body,
        )
        self.assertIsNotNone(match)

        response = self.client.get(match.group(1))
        self.assertRedirects(response, reverse("accounts:profile"))

        user.profile.refresh_from_db()
        self.assertTrue(user.profile.email_verified)
        self.assertIsNotNone(user.profile.email_verified_at)

        response = self.client.get(reverse("core:home"))
        self.assertNotContains(
            response,
            "Verify your email to secure your account",
        )

    def test_verification_link_works_for_logged_out_user(self):
        self.client.logout()
        response = self.client.get(self.verification_url())
        self.assertRedirects(
            response,
            reverse("accounts:login"),
            fetch_redirect_response=False,
        )

        self.profile.refresh_from_db()
        self.assertTrue(self.profile.email_verified)

        response = self.client.get(reverse("accounts:login"))
        self.assertContains(response, "Email verified. Welcome to HackFlow.")

    def test_invalid_verification_link_shows_friendly_page(self):
        uidb64 = urlsafe_base64_encode(force_bytes(self.user.pk))
        response = self.client.get(
            reverse(
                "accounts:verify_email",
                kwargs={"uidb64": uidb64, "token": "invalid-token"},
            )
        )
        self.assertEqual(response.status_code, 400)
        self.assertTemplateUsed(response, "accounts/verify_email_invalid.html")
        self.assertContains(
            response,
            "This link is invalid or expired",
            status_code=400,
        )
        self.profile.refresh_from_db()
        self.assertFalse(self.profile.email_verified)

        huge_uid = urlsafe_base64_encode(force_bytes(10**100))
        response = self.client.get(
            reverse(
                "accounts:verify_email",
                kwargs={"uidb64": huge_uid, "token": "invalid-token"},
            )
        )
        self.assertEqual(response.status_code, 400)
        self.assertTemplateUsed(response, "accounts/verify_email_invalid.html")

    def test_verification_token_is_invalidated_when_email_changes(self):
        old_url = self.verification_url()
        self.user.email = "changed@example.com"
        self.user.save()

        response = self.client.get(old_url)
        self.assertEqual(response.status_code, 400)
        self.profile.refresh_from_db()
        self.assertFalse(self.profile.email_verified)

    def test_account_pages_render(self):
        self.client.force_login(self.user)
        cases = {
            "profile": "accounts/profile.html",
            "password_change": "accounts/password_change.html",
            "delete_account": "accounts/delete_account.html",
        }
        for url_name, template_name in cases.items():
            with self.subTest(url_name=url_name):
                response = self.client.get(reverse(f"accounts:{url_name}"))
                self.assertEqual(response.status_code, 200)
                self.assertTemplateUsed(response, template_name)
                self.assertNotContains(response, "{%")
                self.assertNotContains(response, "field.field")

    def test_account_pages_require_login(self):
        for url_name in ("profile", "password_change", "delete_account"):
            with self.subTest(url_name=url_name):
                response = self.client.get(reverse(f"accounts:{url_name}"))
                self.assertEqual(response.status_code, 302)
                self.assertIn(reverse("accounts:login"), response.url)
                self.assertIn("next=", response.url)

    def test_profile_update_changes_details_and_reverifies_email(self):
        self.client.force_login(self.user)
        old_verification_url = self.verification_url()

        response = self.client.post(
            reverse("accounts:profile"),
            {
                "username": "flowhacker2",
                "email": "new-hacker@example.com",
                "first_name": "Ada",
                "last_name": "Lovelace",
            },
        )
        self.assertRedirects(response, reverse("accounts:profile"))

        self.user.refresh_from_db()
        self.assertEqual(self.user.username, "flowhacker2")
        self.assertEqual(self.user.email, "new-hacker@example.com")
        self.assertEqual(self.user.first_name, "Ada")
        self.assertEqual(self.user.last_name, "Lovelace")

        self.profile.refresh_from_db()
        self.assertFalse(self.profile.email_verified)
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ["new-hacker@example.com"])

        response = self.client.get(old_verification_url)
        self.assertEqual(response.status_code, 400)

        match = re.search(
            r"http://testserver(/accounts/verify-email/[^\s]+)",
            mail.outbox[0].body,
        )
        self.assertIsNotNone(match)
        response = self.client.get(match.group(1))
        self.assertRedirects(response, reverse("accounts:profile"))

        self.profile.refresh_from_db()
        self.assertTrue(self.profile.email_verified)

    def test_profile_update_without_email_change_does_not_send_mail(self):
        self.profile.mark_email_verified()
        self.client.force_login(self.user)

        response = self.client.post(
            reverse("accounts:profile"),
            {
                "username": self.user.username,
                "email": self.user.email,
                "first_name": "Updated",
                "last_name": "",
            },
        )
        self.assertRedirects(response, reverse("accounts:profile"))

        self.user.refresh_from_db()
        self.assertEqual(self.user.first_name, "Updated")
        self.assertEqual(len(mail.outbox), 0)

        self.profile.refresh_from_db()
        self.assertTrue(self.profile.email_verified)

    def test_profile_update_rejects_duplicate_details(self):
        User.objects.create_user(
            username="otherbuilder",
            email="other@example.com",
            password=self.password,
        )
        self.client.force_login(self.user)

        response = self.client.post(
            reverse("accounts:profile"),
            {
                "username": "OtherBuilder",
                "email": "OTHER@example.com",
                "first_name": "",
                "last_name": "",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "That username is already taken.")
        self.assertContains(response, "An account with that email already exists.")
        self.assertEqual(len(mail.outbox), 0)

    def test_profile_update_rejects_cross_field_collisions(self):
        User.objects.create_user(
            username="alias@example.com",
            email="alias-account@example.com",
            password=self.password,
        )
        self.client.force_login(self.user)

        response = self.client.post(
            reverse("accounts:profile"),
            {
                "username": "alias@example.com",
                "email": self.user.email,
                "first_name": "",
                "last_name": "",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "That username is already taken.")
        self.assertEqual(len(mail.outbox), 0)

        response = self.client.post(
            reverse("accounts:profile"),
            {
                "username": self.user.username,
                "email": "alias@example.com",
                "first_name": "",
                "last_name": "",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "An account with that email already exists.")
        self.assertEqual(len(mail.outbox), 0)

    def test_password_change_updates_password_and_keeps_session(self):
        self.client.force_login(self.user)
        new_password = "N3wStrongPass!"

        response = self.client.post(
            reverse("accounts:password_change"),
            {
                "old_password": self.password,
                "new_password1": new_password,
                "new_password2": new_password,
            },
        )
        self.assertRedirects(response, reverse("accounts:profile"))

        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password(new_password))
        self.assertEqual(
            int(self.client.session["_auth_user_id"]),
            self.user.pk,
        )

    def test_password_change_rejects_wrong_current_password(self):
        self.client.force_login(self.user)

        response = self.client.post(
            reverse("accounts:password_change"),
            {
                "old_password": "not-the-password",
                "new_password1": "N3wStrongPass!",
                "new_password2": "N3wStrongPass!",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "old password was entered incorrectly")

        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password(self.password))

    def test_delete_account_requires_password_and_removes_user(self):
        user_pk = self.user.pk
        self.client.force_login(self.user)

        response = self.client.get(reverse("accounts:delete_account"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "This action is permanent")

        response = self.client.post(
            reverse("accounts:delete_account"),
            {"password": "wrong-password", "confirm": "on"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "That password is incorrect.")
        self.assertTrue(User.objects.filter(pk=user_pk).exists())

        response = self.client.post(
            reverse("accounts:delete_account"),
            {"password": self.password, "confirm": "on"},
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("core:home"))

        self.assertFalse(User.objects.filter(pk=user_pk).exists())
        self.assertFalse(Profile.objects.filter(user_id=user_pk).exists())
        self.assertNotIn("_auth_user_id", self.client.session)

        response = self.client.get(reverse("core:home"))
        self.assertContains(response, "Your account has been deleted.")

    def test_resend_verification_email_is_throttled(self):
        self.client.force_login(self.user)

        response = self.client.post(reverse("accounts:resend_verification"))
        self.assertRedirects(response, reverse("accounts:profile"))
        self.assertEqual(len(mail.outbox), 1)

        response = self.client.post(
            reverse("accounts:resend_verification"),
            follow=True,
        )
        self.assertContains(
            response,
            "Please wait before requesting another verification email.",
        )
        self.assertEqual(len(mail.outbox), 1)

    def test_resend_verification_skips_verified_users(self):
        self.profile.mark_email_verified()
        self.client.force_login(self.user)

        response = self.client.post(
            reverse("accounts:resend_verification"),
            follow=True,
        )
        self.assertContains(response, "Your email is already verified.")
        self.assertEqual(len(mail.outbox), 0)

    def test_verification_banner_links_to_resend(self):
        self.client.force_login(self.user)

        response = self.client.get(reverse("core:home"))
        self.assertContains(
            response,
            "Verify your email to secure your account",
        )
        self.assertContains(response, reverse("accounts:resend_verification"))

        self.profile.mark_email_verified()
        response = self.client.get(reverse("core:home"))
        self.assertNotContains(
            response,
            "Verify your email to secure your account",
        )

    def test_login_is_throttled_after_repeated_failures(self):
        login_url = reverse("accounts:login")
        wrong_credentials = {
            "username": self.user.username,
            "password": "wrong-password",
        }

        for _ in range(5):
            response = self.client.post(login_url, wrong_credentials)
            self.assertEqual(response.status_code, 200)

        response = self.client.post(login_url, wrong_credentials)
        self.assertEqual(response.status_code, 429)
        self.assertContains(
            response,
            "Too many failed sign-in attempts",
            status_code=429,
        )

        response = self.client.post(
            login_url,
            {"username": self.user.username, "password": self.password},
        )
        self.assertEqual(response.status_code, 429)

        response = self.client.post(
            login_url,
            {"username": "someone-else", "password": "wrong-password"},
        )
        self.assertEqual(response.status_code, 200)

        cache.clear()
        response = self.client.post(
            login_url,
            {"username": self.user.username, "password": self.password},
        )
        self.assertRedirects(response, reverse("core:home"))
