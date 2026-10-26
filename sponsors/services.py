"""
Business services for the Sponsor Management module — HackFlow ESPRIT.

Contains:
1. The single implementation of sponsorship status transitions with transactional locking (select_for_update).
2. Composition and sending of sponsor emails with error handling, audit trail, and rate limiting.
"""

import logging
from typing import Optional, Union, Tuple
from django.conf import settings
from django.contrib.auth.models import User
from django.core.cache import cache
from django.core.mail import send_mail
from django.db import transaction
from .models import Sponsor, Sponsorship, StatusHistory, StatusChoices, SponsorEmailLog

logger = logging.getLogger(__name__)

EMAIL_RATE_LIMIT_MAX = 5
EMAIL_RATE_LIMIT_WINDOW = 60


# ==============================================================================
# STATUS MANAGEMENT (Single source of truth)
# ==============================================================================


def change_sponsorship_status(
    sponsorship: Union[Sponsorship, int],
    new_status: str,
    changed_by: Optional[User] = None,
) -> Optional[StatusHistory]:
    """
    Unique implementation of sponsorship status change in the application.

    Guarantees:
    1. Strict validation of status against StatusChoices.
    2. Concurrency: pessimistic locking via select_for_update() in transaction.atomic().
    3. Idempotence: if new status equals current status, no write is performed
       and the function returns None (no duplicate in StatusHistory).
    4. Traceability: creation of a StatusHistory entry atomically linked to the update.
    """
    valid_statuses = dict(StatusChoices.choices)
    if new_status not in valid_statuses:
        raise ValueError(
            f'Invalid status "{new_status}". Valid choices: {list(valid_statuses.keys())}'
        )

    sponsorship_id = sponsorship.pk if isinstance(sponsorship, Sponsorship) else sponsorship

    with transaction.atomic():
        # Pessimistic locking of the database row
        locked_sponsorship = Sponsorship.objects.select_for_update().get(pk=sponsorship_id)

        # If status is identical, no modification or history
        if locked_sponsorship.status == new_status:
            return None

        old_status = locked_sponsorship.status
        locked_sponsorship.status = new_status
        locked_sponsorship.save(update_fields=["status", "updated_at"])

        history = StatusHistory.objects.create(
            sponsorship=locked_sponsorship,
            old_status=old_status,
            new_status=new_status,
            changed_by=changed_by,
        )

        # Update the in-memory instance if it was provided
        if isinstance(sponsorship, Sponsorship):
            sponsorship.status = new_status

        return history


# ==============================================================================
# EMAIL COMPOSITION AND SENDING
# ==============================================================================
EMAIL_TEMPLATES = {
    "invitation": {
        "label": "Sponsorship invitation",
        "subject": "Invitation to support {hackathon_name} — HackFlow ESPRIT",
        "body": (
            "Hello {contact_salutation},\n\n"
            "On behalf of the organizing committee of {hackathon_name}, we would be honored "
            "to welcome {sponsor_name} as an official partner and sponsor.\n\n"
            "This event brings ESPRIT's most promising talent together to tackle substantial technical challenges. "
            "Our Platinum, Gold, Silver, and Bronze sponsorship packages offer strong visibility "
            "and opportunities to connect with our engineering students.\n\n"
            "Would you be available for a brief call to discuss the partnership proposal?\n\n"
            "Best regards,\n"
            "The HackFlow ESPRIT organizing team"
        ),
    },
    "relance": {
        "label": "Sponsorship proposal follow-up",
        "subject": "Following up on our sponsorship proposal for {hackathon_name}",
        "body": (
            "Hello {contact_salutation},\n\n"
            "I am following up on our previous message about {hackathon_name}.\n\n"
            "Registration is progressing, and we are finalizing our list of partner companies. "
            "We would be delighted to confirm {sponsor_name}'s participation.\n\n"
            "Please let us know if you would like any additional information.\n\n"
            "Have a great day,\n"
            "The HackFlow ESPRIT team"
        ),
    },
    "remerciement": {
        "label": "Partnership thank-you",
        "subject": "Thank you for supporting {hackathon_name}!",
        "body": (
            "Hello {contact_salutation},\n\n"
            "The entire HackFlow team would like to thank {sponsor_name} "
            "for your invaluable support of {hackathon_name}.\n\n"
            "Your contribution helped our students tackle exciting challenges and bring innovative projects to life. "
            "We hope to work together again at future events.\n\n"
            "Sincerely,\n"
            "The HackFlow ESPRIT team"
        ),
    },
}


def compose_email(
    sponsor: Sponsor,
    hackathon=None,
    template_key: str = "invitation",
) -> dict:
    """
    Generates a pre-filled email subject and body based on the chosen template.
    This function is designed to be connected to an AI service later.
    """
    hackathon_name = hackathon.title if hackathon else "our next hackathon"
    contact_salutation = sponsor.contact_name or sponsor.name

    template_data = EMAIL_TEMPLATES.get(template_key, EMAIL_TEMPLATES["invitation"])

    subject = template_data["subject"].format(
        sponsor_name=sponsor.name,
        hackathon_name=hackathon_name,
    )
    body = template_data["body"].format(
        contact_salutation=contact_salutation,
        sponsor_name=sponsor.name,
        hackathon_name=hackathon_name,
    )

    return {
        "subject": subject,
        "body": body,
        "recipient": sponsor.contact_email,
    }


def check_and_increment_email_rate_limit(user_id: int) -> bool:
    """
    Checks and enforces the anti-abuse limit: max 5 emails per minute per user.
    Returns True if sending is allowed, False if limit is exceeded.
    """
    cache_key = f"sponsor_email_throttle_{user_id}"
    current_count = cache.get(cache_key, 0)

    if current_count >= EMAIL_RATE_LIMIT_MAX:
        return False

    cache.set(cache_key, current_count + 1, timeout=EMAIL_RATE_LIMIT_WINDOW)
    return True


def send_sponsor_contact_email(
    sponsor: Sponsor,
    sent_by: User,
    subject: str,
    body: str,
    ai_generated: bool = False,
) -> Tuple[SponsorEmailLog, bool]:
    """
    Sends an email to the sponsor's contact_email and records the audit log in SponsorEmailLog.

    Security and resilience:
    - Recipient is STRICTLY sponsor.contact_email.
    - Enforces the 5 emails per minute limit.
    - Captures exceptions without crashing: success=False recorded in log.
    - Tracks ai_generated flag in SponsorEmailLog.
    - Returns tuple (log, success).
    """
    recipient = (sponsor.contact_email or "").strip()
    if not recipient:
        log = SponsorEmailLog.objects.create(
            sponsor=sponsor,
            sent_by=sent_by,
            subject=subject,
            body=body,
            ai_generated=ai_generated,
            success=False,
            error_message="No contact email address is provided for this sponsor.",
        )
        return log, False

    # Rate limit check (5/min)
    if not check_and_increment_email_rate_limit(sent_by.pk):
        log = SponsorEmailLog.objects.create(
            sponsor=sponsor,
            sent_by=sent_by,
            subject=subject,
            body=body,
            ai_generated=ai_generated,
            success=False,
            error_message="Rate limit exceeded (maximum 5 emails per minute).",
        )
        return log, False

    from_email = getattr(settings, "DEFAULT_FROM_EMAIL", "HackFlow <hello@hackflow.dev>")

    try:
        send_mail(
            subject=subject,
            message=body,
            from_email=from_email,
            recipient_list=[recipient],
            fail_silently=False,
        )
        log = SponsorEmailLog.objects.create(
            sponsor=sponsor,
            sent_by=sent_by,
            subject=subject,
            body=body,
            ai_generated=ai_generated,
            success=True,
            error_message="",
        )
        return log, True
    except Exception as exc:
        logger.exception("Failed to send email to sponsor %s (%s)", sponsor.pk, recipient)
        log = SponsorEmailLog.objects.create(
            sponsor=sponsor,
            sent_by=sent_by,
            subject=subject,
            body=body,
            ai_generated=ai_generated,
            success=False,
            error_message=str(exc),
        )
        return log, False
