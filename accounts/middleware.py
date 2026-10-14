"""Middleware for single active concurrent session enforcement."""

from django.contrib import messages
from django.contrib.auth import logout
from django.shortcuts import redirect
from django.urls import reverse


class SingleSessionMiddleware:
    """Ensure each account can only have one active session at a time.

    If the same account logs in from another device or browser, the previous session is terminated.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.path_info.startswith('/api/'):
            return self.get_response(request)

        if request.user.is_authenticated:
            expected_key = getattr(request.user, 'current_session_key', '')
            actual_key = request.session.session_key
            if expected_key and actual_key and expected_key != actual_key:
                logout(request)
                messages.warning(
                    request,
                    "You have been logged out because this account was logged into from another device or browser."
                )
                return redirect('login')

        return self.get_response(request)
