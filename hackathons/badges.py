"""
Participant Badge & Check-in Pass Generator for HackFlow.
Provides verifiable QR code check-in tokens and pass metadata.
"""
import io
import base64
import qrcode
from django.urls import reverse


def generate_badge_qr(request, registration) -> str:
    """
    Generates a base64 encoded PNG QR code pointing to the official check-in URL.
    """
    checkin_url = request.build_absolute_uri(
        reverse("hackathons:organizer_checkin", kwargs={
            "slug": registration.hackathon.slug,
            "ticket_code": registration.ticket_code
        })
    )

    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=10,
        border=2,
    )
    qr.add_data(checkin_url)
    qr.make(fit=True)

    img = qr.make_image(fill_color="#090D16", back_color="#FFFFFF")
    buffer = io.BytesIO()
    img.save(buffer)
    b64_img = base64.b64encode(buffer.getvalue()).decode("utf-8")
    return f"data:image/png;base64,{b64_img}"
