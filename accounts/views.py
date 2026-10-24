import hashlib

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import login, logout
from django.contrib.auth import views as auth_views
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.models import User
from django.core.cache import cache
from django.db import DataError, transaction
from django.shortcuts import redirect, render
from django.urls import reverse_lazy
from django.utils.encoding import force_str
from django.utils.http import urlsafe_base64_decode
from django.views import View
from django.views.generic import FormView

from .emails import send_verification_email
from .forms import (
    AccountSettingsForm,
    DeleteAccountForm,
    HackFlowAuthenticationForm,
    HackFlowPasswordChangeForm,
    HackFlowPasswordResetForm,
    HackFlowSetPasswordForm,
    HackFlowSignupForm,
)
from .models import Profile
from .tokens import email_verification_token


class LoginView(auth_views.LoginView):
    template_name = "accounts/login.html"
    authentication_form = HackFlowAuthenticationForm
    redirect_authenticated_user = True

    def dispatch(self, request, *args, **kwargs):
        if request.method == "POST" and settings.LOGIN_MAX_ATTEMPTS > 0:
            key = self._rate_limit_key(request)
            if cache.get(key, 0) >= settings.LOGIN_MAX_ATTEMPTS:
                form = self.get_form()
                form.add_error(None, self._lockout_message())
                response = self.render_to_response(
                    self.get_context_data(form=form),
                    status=429,
                )
                response["Retry-After"] = str(settings.LOGIN_LOCKOUT_SECONDS)
                return response
        return super().dispatch(request, *args, **kwargs)

    def form_valid(self, form):
        cache.delete(self._rate_limit_key(self.request))
        response = super().form_valid(form)
        if form.cleaned_data.get("remember_me"):
            self.request.session.set_expiry(60 * 60 * 24 * 30)
        else:
            self.request.session.set_expiry(0)
        messages.success(
            self.request,
            f"Welcome back, {self.request.user.get_username()}.",
        )
        return response

    def form_invalid(self, form):
        if settings.LOGIN_MAX_ATTEMPTS > 0:
            key = self._rate_limit_key(self.request)
            attempts = cache.get(key, 0)
            cache.set(key, attempts + 1, settings.LOGIN_LOCKOUT_SECONDS)
        return super().form_invalid(form)

    def _rate_limit_key(self, request):
        username = (request.POST.get("username") or "").strip().lower()
        remote_addr = request.META.get("REMOTE_ADDR", "")
        digest = hashlib.sha256(f"{remote_addr}:{username}".encode()).hexdigest()
        return f"login-attempts:{digest}"

    def _lockout_message(self):
        minutes = max(1, settings.LOGIN_LOCKOUT_SECONDS // 60)
        return (
            "Too many failed sign-in attempts. "
            f"Try again in {minutes} minutes."
        )


class SignupView(FormView):
    template_name = "accounts/signup.html"
    form_class = HackFlowSignupForm
    success_url = reverse_lazy("core:home")

    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated:
            return redirect("core:home")
        return super().dispatch(request, *args, **kwargs)

    def form_valid(self, form):
        with transaction.atomic():
            user = form.save()
        login(
            self.request,
            user,
            backend="accounts.backends.EmailOrUsernameBackend",
        )
        if send_verification_email(self.request, user):
            messages.success(
                self.request,
                f"Welcome to HackFlow, {user.get_username()}. "
                "Check your inbox to verify your email.",
            )
        else:
            messages.warning(
                self.request,
                f"Welcome to HackFlow, {user.get_username()}. "
                "We couldn't send the verification email — resend it from "
                "account settings.",
            )
        return super().form_valid(form)


class LogoutView(auth_views.LogoutView):
    next_page = reverse_lazy("core:home")

    def post(self, request, *args, **kwargs):
        response = super().post(request, *args, **kwargs)
        messages.success(request, "You've been signed out. See you next build.")
        return response


def _password_reset_expiry_days():
    return max(1, settings.PASSWORD_RESET_TIMEOUT // (60 * 60 * 24))


class PasswordExpiryContextMixin:
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["expires_days"] = _password_reset_expiry_days()
        return context


class PasswordResetView(PasswordExpiryContextMixin, auth_views.PasswordResetView):
    template_name = "accounts/password_reset_form.html"
    email_template_name = "accounts/emails/password_reset_email.txt"
    html_email_template_name = "accounts/emails/password_reset_email.html"
    subject_template_name = "accounts/emails/password_reset_subject.txt"
    form_class = HackFlowPasswordResetForm
    success_url = reverse_lazy("accounts:password_reset_done")

    @property
    def extra_email_context(self):
        return {"expires_days": _password_reset_expiry_days()}


class PasswordResetDoneView(PasswordExpiryContextMixin, auth_views.PasswordResetDoneView):
    template_name = "accounts/password_reset_done.html"


class PasswordResetConfirmView(
    PasswordExpiryContextMixin, auth_views.PasswordResetConfirmView
):
    template_name = "accounts/password_reset_confirm.html"
    form_class = HackFlowSetPasswordForm
    success_url = reverse_lazy("accounts:password_reset_complete")


class PasswordResetCompleteView(auth_views.PasswordResetCompleteView):
    template_name = "accounts/password_reset_complete.html"


class ProfileView(LoginRequiredMixin, View):
    template_name = "accounts/profile.html"

    def get_profile(self):
        profile, _ = Profile.objects.get_or_create(user=self.request.user)
        return profile

    def get(self, request):
        return render(
            request,
            self.template_name,
            {
                "form": AccountSettingsForm(instance=request.user),
                "profile": self.get_profile(),
            },
        )

    def post(self, request):
        form = AccountSettingsForm(request.POST, instance=request.user)
        if form.is_valid():
            email_changed = form.email_changed
            with transaction.atomic():
                user = form.save()
                if email_changed:
                    profile = self.get_profile()
                    profile.reset_email_verification()

            if email_changed:
                if send_verification_email(request, user):
                    messages.success(
                        request,
                        "Account updated. Check your inbox to verify your "
                        "new email address.",
                    )
                else:
                    messages.warning(
                        request,
                        "Account updated, but we couldn't send the "
                        "verification email. Try resending it below.",
                    )
            else:
                messages.success(request, "Account updated.")
            return redirect("accounts:profile")

        return render(
            request,
            self.template_name,
            {"form": form, "profile": self.get_profile()},
        )


class PasswordChangeView(LoginRequiredMixin, auth_views.PasswordChangeView):
    template_name = "accounts/password_change.html"
    form_class = HackFlowPasswordChangeForm
    success_url = reverse_lazy("accounts:profile")

    def form_valid(self, form):
        response = super().form_valid(form)
        messages.success(self.request, "Password updated.")
        return response


class DeleteAccountView(LoginRequiredMixin, FormView):
    template_name = "accounts/delete_account.html"
    form_class = DeleteAccountForm
    success_url = reverse_lazy("core:home")

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["user"] = self.request.user
        return kwargs

    def form_valid(self, form):
        user = self.request.user
        logout(self.request)
        user.delete()
        messages.success(self.request, "Your account has been deleted.")
        return super().form_valid(form)


class VerifyEmailView(View):
    template_name = "accounts/verify_email_invalid.html"

    @staticmethod
    def get_user(uidb64):
        try:
            uid = force_str(urlsafe_base64_decode(uidb64))
            return User.objects.get(pk=uid)
        except (TypeError, ValueError, OverflowError, DataError, User.DoesNotExist):
            return None

    def get(self, request, uidb64, token):
        user = self.get_user(uidb64)
        if user is not None and email_verification_token.check_token(user, token):
            profile, _ = Profile.objects.get_or_create(user=user)
            if profile.email_verified:
                messages.info(request, "Your email is already verified.")
            else:
                profile.mark_email_verified()
                messages.success(request, "Email verified. Welcome to HackFlow.")

            if request.user.is_authenticated and request.user.pk == user.pk:
                return redirect("accounts:profile")
            if request.user.is_authenticated:
                return redirect("core:home")
            return redirect("accounts:login")

        return render(request, self.template_name, status=400)


class ResendVerificationView(LoginRequiredMixin, View):
    http_method_names = ["post"]

    def post(self, request):
        profile, _ = Profile.objects.get_or_create(user=request.user)

        if profile.email_verified:
            messages.info(request, "Your email is already verified.")
            return redirect("accounts:profile")

        if not request.user.email:
            messages.error(
                request,
                "Add an email address before requesting verification.",
            )
            return redirect("accounts:profile")

        cooldown = settings.EMAIL_VERIFICATION_RESEND_COOLDOWN
        cache_key = f"email-verification-resend:{request.user.pk}"
        if cooldown > 0 and not cache.add(cache_key, True, cooldown):
            messages.warning(
                request,
                "Please wait before requesting another verification email.",
            )
            return redirect("accounts:profile")

        if send_verification_email(request, request.user):
            messages.success(
                request,
                f"Verification email sent to {request.user.email}.",
            )
        else:
            if cooldown > 0:
                cache.delete(cache_key)
            messages.error(
                request,
                "We couldn't send the verification email. Try again later.",
            )
        return redirect("accounts:profile")
