from django.contrib.auth import get_user_model
from django.contrib.auth.backends import ModelBackend
from django.db.models import Q

UserModel = get_user_model()


class EmailOrUsernameBackend(ModelBackend):
    """Authenticate with either a username or an email address (case-insensitive)."""

    def authenticate(self, request, username=None, password=None, **kwargs):
        if username is None:
            username = kwargs.get(UserModel.USERNAME_FIELD)
        if username is None or password is None:
            return None

        username = username.strip()
        query = Q(username__iexact=username) | Q(email__iexact=username)

        try:
            user = UserModel._default_manager.get(query)
        except UserModel.DoesNotExist:
            # Run the default password hasher once to reduce the timing
            # difference between existing and non-existing accounts.
            UserModel().set_password(password)
            return None
        except UserModel.MultipleObjectsReturned:
            # Prefer an exact username match, otherwise use the first match.
            user = (
                UserModel._default_manager.filter(username__iexact=username).first()
                or UserModel._default_manager.filter(query).first()
            )
            if user is None:
                return None

        if user.check_password(password) and self.user_can_authenticate(user):
            return user
        return None
