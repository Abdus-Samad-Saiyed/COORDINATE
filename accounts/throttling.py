"""Lightweight rate-limiting and anti-abuse utility for COORDINATE.

Protects sensitive endpoints (login, account application, password recovery)
against brute-force and resource exhaustion attacks.
"""

from functools import wraps
from django.core.cache import cache
from django.http import HttpResponse, JsonResponse
from django.shortcuts import render


def get_client_ip(request):
    """Extract client IP address from request, taking proxy headers into account."""
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        return x_forwarded_for.split(',')[0].strip()
    return request.META.get('REMOTE_ADDR', '127.0.0.1')


def rate_limit(key_prefix: str, limit: int, period_seconds: int, message: str = None):
    """
    Decorator to rate limit POST requests by client IP and identifier.

    Args:
        key_prefix: Unique namespace for this rate limiter (e.g. 'login', 'apply').
        limit: Maximum number of attempts allowed in the period.
        period_seconds: Sliding window duration in seconds.
        message: Custom error message to show when throttled.
    """
    if message is None:
        message = 'Too many requests. Please wait a few minutes before trying again.'

    def decorator(view_func):
        @wraps(view_func)
        def _wrapped_view(request, *args, **kwargs):
            if request.method == 'POST':
                ip = get_client_ip(request)
                # Key on IP
                cache_key = f'ratelimit:{key_prefix}:{ip}'

                current_count = cache.get(cache_key, 0)
                if current_count >= limit:
                    # Exceeded limit
                    if request.headers.get('x-requested-with') == 'XMLHttpRequest' or getattr(request, 'htmx', False):
                        return JsonResponse({'error': message}, status=429)
                    return render(
                        request,
                        'accounts/throttled.html',
                        {'message': message, 'retry_after': period_seconds},
                        status=429,
                    )

                cache.set(cache_key, current_count + 1, timeout=period_seconds)

            return view_func(request, *args, **kwargs)

        return _wrapped_view

    return decorator
