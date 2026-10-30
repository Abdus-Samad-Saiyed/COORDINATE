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

    def user_can_authenticate(self, user):
        """
        Reject inactive users, soft-deleted users, and reject 20XX synthetic
        debug accounts when running in production.
        """
        is_active = super().user_can_authenticate(user)
        if not is_active:
            return False
        if getattr(user, 'is_deleted', False):
            return False
        from accounts.utils import is_debug_enrollment, is_production_environment
        if is_production_environment() and is_debug_enrollment(getattr(user, 'enrollment_number', '')):
            return False
        return True
