from django import forms
from django.contrib.auth.forms import (
    AuthenticationForm,
    PasswordChangeForm,
    PasswordResetForm,
    SetPasswordForm,
    UserCreationForm,
)
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.db.models import Q
from django.utils.translation import gettext_lazy as _


class HackFlowAuthenticationForm(AuthenticationForm):
    username = forms.CharField(
        label=_("Email or username"),
        max_length=254,
        widget=forms.TextInput(
            attrs={
                "autofocus": True,
                "autocomplete": "username",
                "placeholder": "you@example.com",
            }
        ),
    )
    password = forms.CharField(
        label=_("Password"),
        strip=False,
        widget=forms.PasswordInput(
            attrs={
                "autocomplete": "current-password",
                "placeholder": "Your password",
            }
        ),
    )
    remember_me = forms.BooleanField(
        label=_("Remember me for 30 days"),
        required=False,
        widget=forms.CheckboxInput,
    )

    error_messages = {
        "invalid_login": _(
            "That email/username and password don't match. Check them and try again."
        ),
        "inactive": _("This account has been disabled."),
    }


class HackFlowSignupForm(UserCreationForm):
    email = forms.EmailField(
        label=_("Email"),
        required=True,
        widget=forms.EmailInput(
            attrs={
                "autocomplete": "email",
                "placeholder": "you@example.com",
            }
        ),
    )

    class Meta(UserCreationForm.Meta):
        model = User
        fields = ("username", "email")
        widgets = {
            "username": forms.TextInput(
                attrs={
                    "autocomplete": "username",
                    "placeholder": "your-handle",
                }
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["username"].label = _("Username")
        self.fields["username"].help_text = _(
            "Letters, digits and @/./+/-/_ only. This is your public handle."
        )
        self.fields["password1"].label = _("Password")
        self.fields["password1"].widget.attrs.update(
            {"autocomplete": "new-password", "placeholder": "Create a strong password"}
        )
        self.fields["password2"].label = _("Confirm password")
        self.fields["password2"].widget.attrs.update(
            {"autocomplete": "new-password", "placeholder": "Repeat your password"}
        )
        self.fields["password2"].help_text = _("Re-enter your password to confirm.")

    def clean_username(self):
        username = self.cleaned_data["username"]
        if User.objects.filter(
            Q(username__iexact=username) | Q(email__iexact=username)
        ).exists():
            raise ValidationError(
                _("That username is already taken. Try another one."),
                code="username_taken",
            )
        return username

    def clean_email(self):
        email = self.cleaned_data["email"].strip().lower()
        if User.objects.filter(
            Q(email__iexact=email) | Q(username__iexact=email)
        ).exists():
            raise ValidationError(
                _("An account with that email already exists."),
                code="email_taken",
            )
        return email

    def save(self, commit=True):
        user = super().save(commit=False)
        user.email = self.cleaned_data["email"]
        if commit:
            user.save()
        return user


class HackFlowPasswordResetForm(PasswordResetForm):
    email = forms.EmailField(
        label=_("Email"),
        max_length=254,
        widget=forms.EmailInput(
            attrs={
                "autocomplete": "email",
                "placeholder": "you@example.com",
                "autofocus": True,
            }
        ),
    )


class HackFlowSetPasswordForm(SetPasswordForm):
    new_password1 = forms.CharField(
        label=_("New password"),
        widget=forms.PasswordInput(
            attrs={
                "autocomplete": "new-password",
                "placeholder": "Create a new password",
                "autofocus": True,
            }
        ),
        strip=False,
        help_text=SetPasswordForm.base_fields["new_password1"].help_text,
    )
    new_password2 = forms.CharField(
        label=_("Confirm new password"),
        strip=False,
        widget=forms.PasswordInput(
            attrs={
                "autocomplete": "new-password",
                "placeholder": "Repeat your new password",
            }
        ),
        help_text=_("Re-enter your new password to confirm."),
    )


class AccountSettingsForm(forms.ModelForm):
    """Update public account details. Email changes trigger re-verification."""

    class Meta:
        model = User
        fields = ("username", "email", "first_name", "last_name")
        widgets = {
            "username": forms.TextInput(
                attrs={
                    "autocomplete": "username",
                    "placeholder": "your-handle",
                }
            ),
            "email": forms.EmailInput(
                attrs={
                    "autocomplete": "email",
                    "placeholder": "you@example.com",
                }
            ),
            "first_name": forms.TextInput(
                attrs={
                    "autocomplete": "given-name",
                    "placeholder": "Ada",
                }
            ),
            "last_name": forms.TextInput(
                attrs={
                    "autocomplete": "family-name",
                    "placeholder": "Lovelace",
                }
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.original_email = (self.instance.email or "").strip().lower()
        self.fields["email"].required = True
        self.fields["email"].help_text = _(
            "Changing your email requires verifying the new address."
        )
        self.fields["username"].help_text = _(
            "Letters, digits and @/./+/-/_ only. This is your public handle."
        )
        self.fields["first_name"].label = _("First name")
        self.fields["last_name"].label = _("Last name")

    def clean_username(self):
        username = self.cleaned_data["username"]
        query = User.objects.filter(
            Q(username__iexact=username) | Q(email__iexact=username)
        )
        if self.instance.pk:
            query = query.exclude(pk=self.instance.pk)
        if query.exists():
            raise ValidationError(
                _("That username is already taken. Try another one."),
                code="username_taken",
            )
        return username

    def clean_email(self):
        email = self.cleaned_data["email"].strip().lower()
        query = User.objects.filter(
            Q(email__iexact=email) | Q(username__iexact=email)
        )
        if self.instance.pk:
            query = query.exclude(pk=self.instance.pk)
        if query.exists():
            raise ValidationError(
                _("An account with that email already exists."),
                code="email_taken",
            )
        return email

    @property
    def email_changed(self):
        if not self.is_valid():
            return False
        return self.cleaned_data.get("email", "").lower() != self.original_email


class HackFlowPasswordChangeForm(PasswordChangeForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["old_password"].label = _("Current password")
        self.fields["old_password"].widget.attrs.update(
            {
                "autocomplete": "current-password",
                "placeholder": "Your current password",
                "autofocus": True,
            }
        )
        self.fields["new_password1"].label = _("New password")
        self.fields["new_password1"].widget.attrs.update(
            {
                "autocomplete": "new-password",
                "placeholder": "Create a new password",
            }
        )
        self.fields["new_password2"].label = _("Confirm new password")
        self.fields["new_password2"].widget.attrs.update(
            {
                "autocomplete": "new-password",
                "placeholder": "Repeat your new password",
            }
        )
        self.fields["new_password2"].help_text = _(
            "Re-enter your new password to confirm."
        )


class DeleteAccountForm(forms.Form):
    password = forms.CharField(
        label=_("Password"),
        strip=False,
        widget=forms.PasswordInput(
            attrs={
                "autocomplete": "current-password",
                "placeholder": "Confirm your password",
                "autofocus": True,
            }
        ),
        help_text=_("Enter your password to confirm this irreversible action."),
    )
    confirm = forms.BooleanField(
        label=_("I understand this permanently deletes my account and data."),
        error_messages={
            "required": _("Please confirm that you understand this is permanent.")
        },
    )

    def __init__(self, user, *args, **kwargs):
        self.user = user
        super().__init__(*args, **kwargs)

    def clean_password(self):
        password = self.cleaned_data["password"]
        if not self.user.check_password(password):
            raise ValidationError(_("That password is incorrect."), code="wrong_password")
        return password
