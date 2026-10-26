import logging
from django.conf import settings
from django.core.mail import send_mail

logger = logging.getLogger(__name__)


def send_student_registration_email(registration):
    """
    Confirmation email sent to the student immediately upon registration:
    dates, venue/link, next steps (form a team), or waitlist status notice.
    """
    hackathon = registration.hackathon
    student = registration.participant
    recipient = student.email

    if not recipient:
        return

    is_waitlist = registration.status == "waitlist"

    if is_waitlist:
        subject = f"Waitlist Confirmation — {hackathon.title}"
        message = (
            f"Hi {student.first_name or student.username},\n\n"
            f'Your registration application for "{hackathon.title}" has been received.\n\n'
            f"Because this hackathon has reached its maximum capacity ({hackathon.max_participants} builders), "
            f"you have been placed on the priority waitlist.\n\n"
            f"As soon as a spot opens up due to a cancellation, you will automatically be promoted to confirmed "
            f"and notified right away via email.\n\n"
            f"Event Highlights:\n"
            f"- Dates: {hackathon.start_date.strftime('%b %d, %Y @ %H:%M')} to {hackathon.end_date.strftime('%b %d, %Y @ %H:%M')}\n"
            f"- Venue: {hackathon.location or hackathon.get_mode_display()} ({hackathon.get_mode_display()})\n\n"
            f"Happy Hacking,\n"
            f"The HackFlow Team"
        )
    else:
        subject = f"Registration Confirmed — {hackathon.title}"
        message = (
            f"Hi {student.first_name or student.username},\n\n"
            f'Congratulations! You are officially registered for "{hackathon.title}" 🎉.\n\n'
            f"📅 Event Schedule & Location:\n"
            f"- Competition: {hackathon.start_date.strftime('%b %d, %Y @ %H:%M')} to {hackathon.end_date.strftime('%b %d, %Y @ %H:%M')}\n"
            f"- Venue / Format: {hackathon.location or hackathon.get_mode_display()} ({hackathon.get_mode_display()})\n"
            f"- Registration & team changes lock: {hackathon.registration_deadline.strftime('%b %d, %Y @ %H:%M')}\n\n"
            f"🚀 Next Step: Build your team!\n"
            f"- Permitted team size: {hackathon.min_team_size} to {hackathon.max_team_size} builders.\n"
            f"- You can connect with fellow builders and start brainstorming your project.\n\n"
            f"Good luck and see you at kickoff!\n"
            f"The HackFlow Team"
        )

    try:
        send_mail(
            subject=subject,
            message=message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[recipient],
            fail_silently=False,
        )
    except Exception as exc:
        logger.exception("Error sending student registration email: %s", exc)


def send_waitlist_promoted_email(registration):
    """
    Notification sent to student when a spot opens and they are promoted
    from waitlist to confirmed.
    """
    hackathon = registration.hackathon
    student = registration.participant
    recipient = student.email

    if not recipient:
        return

    subject = f"🎉 Great News: Your spot is now CONFIRMED for {hackathon.title}!"
    message = (
        f"Hi {student.first_name or student.username},\n\n"
        f"Great news! A spot just opened up and you have been promoted from the waitlist "
        f'to CONFIRMED for "{hackathon.title}"!\n\n'
        f"📅 Quick reminder of event details:\n"
        f"- Competition window: {hackathon.start_date.strftime('%b %d, %Y @ %H:%M')} to {hackathon.end_date.strftime('%b %d, %Y @ %H:%M')}\n"
        f"- Venue: {hackathon.location or hackathon.get_mode_display()}\n\n"
        f"🚀 Next Step: Join or form your team ({hackathon.min_team_size} to {hackathon.max_team_size} members)!\n\n"
        f"Best of luck,\n"
        f"The HackFlow Team"
    )

    try:
        send_mail(
            subject=subject,
            message=message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[recipient],
            fail_silently=False,
        )
    except Exception as exc:
        logger.exception("Error sending waitlist promotion email: %s", exc)


def send_organizer_new_registration_email(registration):
    """
    Notification sent to the organizer on each new participant registration.
    """
    hackathon = registration.hackathon
    organizer = hackathon.organizer
    recipients = [email for email in [organizer.email, hackathon.contact_email] if email]

    if not recipients:
        return

    student = registration.participant
    current_count = hackathon.registered_count
    max_count = hackathon.max_participants
    percent = hackathon.registration_progress_percent

    subject = f"New Registration: {student.username} for {hackathon.title}"
    message = (
        f"Hi {organizer.username},\n\n"
        f'A new participant has just registered for your hackathon "{hackathon.title}":\n\n'
        f"👤 Participant: {student.get_full_name() or student.username} ({student.email})\n"
        f"🏫 University / Institution: {registration.university or 'Not specified'}\n"
        f"🎓 Study Level: {registration.get_study_level_display()}\n"
        f"⚡ Experience Level: {registration.get_experience_level_display()}\n"
        f"🛠️ Skills: {registration.skills}\n"
        f"🤝 Looking for a team: {'Yes' if registration.seeking_team else 'No'}\n"
        f"📋 Status: {registration.get_status_display()}\n\n"
        f"📊 Current Capacity: {current_count} / {max_count} confirmed builders ({percent}%)\n\n"
        f"HackFlow Automated Notifications"
    )

    try:
        send_mail(
            subject=subject,
            message=message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=list(set(recipients)),
            fail_silently=False,
        )
    except Exception as exc:
        logger.exception("Error sending organizer registration email: %s", exc)


def check_and_notify_capacity_thresholds(hackathon, previous_count):
    """
    Alert the organizer when the 80% or 100% capacity threshold is crossed.
    """
    organizer = hackathon.organizer
    recipients = [email for email in [organizer.email, hackathon.contact_email] if email]
    if not recipients or hackathon.max_participants <= 0:
        return

    current_count = hackathon.registered_count
    threshold_80 = int(hackathon.max_participants * 0.8)

    # 80% Threshold reached
    if (
        previous_count < threshold_80
        and current_count >= threshold_80
        and current_count < hackathon.max_participants
    ):
        subject = f"⚠️ 80% Capacity Reached: {hackathon.title}"
        message = (
            f"Hi {organizer.username},\n\n"
            f'Your hackathon "{hackathon.title}" has crossed 80% capacity '
            f"({current_count} / {hackathon.max_participants} confirmed builders).\n\n"
            f"Check your mentor assignments and logistics preparations on HackFlow!"
        )
        try:
            send_mail(
                subject=subject,
                message=message,
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=list(set(recipients)),
                fail_silently=True,
            )
        except Exception as exc:
            logger.warning("Error sending 80%% capacity alert email: %s", exc)

    # 100% Full Capacity reached
    elif (
        previous_count < hackathon.max_participants and current_count >= hackathon.max_participants
    ):
        subject = f"🚨 Maximum Capacity Reached (100%): {hackathon.title}"
        message = (
            f"Hi {organizer.username},\n\n"
            f'Congratulations! "{hackathon.title}" is now at 100% maximum capacity '
            f"({current_count} / {hackathon.max_participants} builders).\n\n"
            f"All subsequent registrations will automatically be routed to the priority waitlist."
        )
        try:
            send_mail(
                subject=subject,
                message=message,
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=list(set(recipients)),
                fail_silently=True,
            )
        except Exception as exc:
            logger.warning("Error sending 100%% capacity alert email: %s", exc)
