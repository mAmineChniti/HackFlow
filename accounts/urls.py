from django.urls import path

from . import views

app_name = "accounts"

urlpatterns = [
    path("login/", views.LoginView.as_view(), name="login"),
    path("signup/", views.SignupView.as_view(), name="signup"),
    path("logout/", views.LogoutView.as_view(), name="logout"),
    path("profile/", views.ProfileView.as_view(), name="profile"),
    path(
        "password/change/",
        views.PasswordChangeView.as_view(),
        name="password_change",
    ),
    path(
        "delete/",
        views.DeleteAccountView.as_view(),
        name="delete_account",
    ),
    path(
        "verify-email/resend/",
        views.ResendVerificationView.as_view(),
        name="resend_verification",
    ),
    path(
        "verify-email/<uidb64>/<token>/",
        views.VerifyEmailView.as_view(),
        name="verify_email",
    ),
    path("password-reset/", views.PasswordResetView.as_view(), name="password_reset"),
    path(
        "password-reset/done/",
        views.PasswordResetDoneView.as_view(),
        name="password_reset_done",
    ),
    path(
        "password-reset/confirm/<uidb64>/<token>/",
        views.PasswordResetConfirmView.as_view(),
        name="password_reset_confirm",
    ),
    path(
        "password-reset/complete/",
        views.PasswordResetCompleteView.as_view(),
        name="password_reset_complete",
    ),
]
