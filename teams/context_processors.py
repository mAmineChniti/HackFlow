from .models import Invitation


def pending_invitations(request):
    user = getattr(request, "user", None)
    if user is None or not user.is_authenticated:
        return {}
    count = Invitation.objects.filter(invitee=user, status=Invitation.Status.PENDING).count()
    return {"pending_invitations_count": count}
