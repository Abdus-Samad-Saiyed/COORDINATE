"""Middleware for single active concurrent session enforcement."""

from django.contrib import messages
from django.contrib.auth import logout
from django.http import JsonResponse
from django.shortcuts import redirect
from accounts.two_factor import hash_otp


class SingleSessionMiddleware:
    """Ensure each account can only have one active session at a time.

    If the same account logs in from another device or browser, the previous session is terminated.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.user.is_authenticated:
            if getattr(request.user, 'is_deleted', False) or not request.user.is_active:
                logout(request)
                if request.path_info.startswith('/api/'):
                    return JsonResponse({'status': 'error', 'error': 'Account inactive.', 'code': 'ACCOUNT_INACTIVE'}, status=401)
                messages.error(request, "This account has been closed.")
                return redirect('login')

            expected_key = getattr(request.user, 'current_session_key', '')
            actual_key = request.session.session_key
            if expected_key and actual_key:
                actual_hash = hash_otp(actual_key)
                if expected_key not in (actual_key, actual_hash):
                    logout(request)
                    if request.path_info.startswith('/api/'):
                        return JsonResponse({'status': 'error', 'error': 'Session invalidated.', 'code': 'SESSION_REVOKED'}, status=401)
                    messages.warning(
                        request,
                        "You have been logged out because this account was logged into from another device or browser."
                    )
                    return redirect('login')

        return self.get_response(request)
