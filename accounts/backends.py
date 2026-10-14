"""Custom authentication backend for COORDINATE.

Supports authenticating by enrollment_number (case-insensitive) or username,
and prevents timing attacks when users do not exist.
"""

from django.contrib.auth import get_user_model
from django.contrib.auth.backends import ModelBackend


class EnrollmentBackend(ModelBackend):
    """
    Authenticate against accounts.User using enrollment_number.
    Normalizes input to uppercase so logins are case-insensitive.
    Accepts both 'username' and 'enrollment_number' keyword arguments.
    """

    def authenticate(self, request, username=None, password=None, enrollment_number=None, **kwargs):
        UserModel = get_user_model()
        ident = enrollment_number or username

        if not ident or not password:
            return None

        ident = ident.strip().upper()

        try:
            user = UserModel.objects.get(enrollment_number=ident)
        except UserModel.DoesNotExist:
            # Run the default password hasher once to mitigate timing differences
            UserModel().set_password(password)
            return None
        else:
            if user.check_password(password) and self.user_can_authenticate(user):
                return user

        return None
