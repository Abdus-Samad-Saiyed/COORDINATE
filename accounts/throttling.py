"""Lightweight rate-limiting and anti-abuse utility for COORDINATE.

Protects sensitive endpoints (login, account application, password recovery)
against brute-force and resource exhaustion attacks.
"""

from functools import wraps
from django.core.cache import cache
from django.http import HttpResponse, JsonResponse
from django.shortcuts import render


def get_client_ip(request):
    """Extract client IP address safely from request.
    In reverse-proxied production environments (nginx/gunicorn), intermediate proxies
    append to HTTP_X_FORWARDED_FOR. The rightmost IP represents the client connected
    to our trusted ingress reverse proxy.
    """
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        parts = [p.strip() for p in x_forwarded_for.split(',') if p.strip()]
        if parts:
            return parts[-1]
    return request.META.get('REMOTE_ADDR', '127.0.0.1')


def rate_limit(key_prefix: str, limit: int, period_seconds: int, message: str = None):
    """
    Decorator to rate limit POST requests by client IP and identifier.
    Uses atomic cache.add and cache.incr to prevent race conditions and TTL resets.
    """
    if message is None:
        message = 'Too many requests. Please wait a few minutes before trying again.'

    def decorator(view_func):
        @wraps(view_func)
        def _wrapped_view(request, *args, **kwargs):
            if request.method == 'POST':
                ip = get_client_ip(request)
                cache_key = f'ratelimit:{key_prefix}:{ip}'

                # Atomic counter: cache.add sets initial 1 with period_seconds TTL.
                # If key already exists, cache.incr increments count without resetting TTL.
                if not cache.add(cache_key, 1, timeout=period_seconds):
                    try:
                        current_count = cache.incr(cache_key)
                    except ValueError:
                        current_count = cache.get(cache_key, 1)
                else:
                    current_count = 1

                if current_count > limit:
                    # Check if client expects JSON
                    accept = request.headers.get('accept', '') or ''
                    content_type = request.content_type or ''
                    is_ajax = (
                        request.headers.get('x-requested-with') == 'XMLHttpRequest'
                        or getattr(request, 'htmx', False)
                        or 'application/json' in accept
                        or 'application/json' in content_type
                    )

                    if is_ajax:
                        return JsonResponse(
                            {'success': False, 'error': message, 'code': 'RATE_LIMITED'},
                            status=429,
                        )
                    return render(
                        request,
                        'accounts/throttled.html',
                        {'message': message, 'retry_after': period_seconds},
                        status=429,
                    )

            return view_func(request, *args, **kwargs)

        return _wrapped_view

    return decorator
