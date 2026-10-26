import logging

from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode

from .models import Profile
from .tokens import email_verification_token

logger = logging.getLogger(__name__)


def build_verification_url(request, user):
    uidb64 = urlsafe_base64_encode(force_bytes(user.pk))
    token = email_verification_token.make_token(user)
    path = reverse(
        "accounts:verify_email",
        kwargs={"uidb64": uidb64, "token": token},
    )
    return request.build_absolute_uri(path)


def send_verification_email(request, user):
    """Send a verification link to the user's current email address.

    Returns True when an email was handed to the backend, False when the
    address is missing/already verified or the backend raised an error.
    """
    profile, _ = Profile.objects.get_or_create(user=user)
    if profile.email_verified or not user.email:
        return False

    verification_url = build_verification_url(request, user)
    context = {
        "user": user,
        "verification_url": verification_url,
        "expires_days": max(1, settings.PASSWORD_RESET_TIMEOUT // (60 * 60 * 24)),
    }
    subject = render_to_string("accounts/emails/verify_email_subject.txt", context).strip()
    text_body = render_to_string("accounts/emails/verify_email.txt", context)
    html_body = render_to_string("accounts/emails/verify_email.html", context)

    message = EmailMultiAlternatives(
        subject=subject,
        body=text_body,
        from_email=settings.DEFAULT_FROM_EMAIL,
        to=[user.email],
    )
    message.attach_alternative(html_body, "text/html")

    try:
        sent = message.send()
    except Exception:
        logger.exception("Could not send verification email for user %s", user.pk)
        return False
    if not sent:
        logger.warning("Verification email was not sent for user %s", user.pk)
        return False
    return True
