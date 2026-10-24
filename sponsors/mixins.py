"""Access-control mixins for sponsor management views."""

from django.contrib import messages
from django.contrib.auth.mixins import UserPassesTestMixin
from django.shortcuts import redirect

from sponsors.permissions import user_has_sponsor_permission


class SponsorPermissionRequiredMixin(UserPassesTestMixin):
    required_permission = "manage"

    def test_func(self):
        return user_has_sponsor_permission(
            self.request.user,
            self.required_permission,
        )

    def handle_no_permission(self):
        if not self.request.user.is_authenticated:
            return redirect(f"/accounts/login/?next={self.request.path}")

        messages.error(
            self.request,
            "Access to this sponsor feature is not permitted for your role."
        )
        return redirect("sponsors:public_list")
