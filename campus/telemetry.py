"""
Traffic telemetry and operational performance metrics engine for Campus Nexus.
Tracks server traffic, throughput, response latency, and generates operational metrics:
requests today, average daily requests, unique user sign-ins today, and interval telemetry.
"""

import threading
import time
from datetime import datetime, timedelta
from django.core.cache import cache
from django.utils import timezone

_LOCK = threading.Lock()
_START_TIME = time.time()

# Cache keys
KEY_TOTAL_REQUESTS = 'nexus_telemetry_total_requests'
KEY_TOTAL_LATENCY_MS = 'nexus_telemetry_total_latency_ms'
KEY_PEAK_RPS = 'nexus_telemetry_peak_rps'
KEY_LAST_WINDOW_TS = 'nexus_telemetry_window_ts'
KEY_WINDOW_REQ_COUNT = 'nexus_telemetry_window_req_count'


class TrafficTelemetryMiddleware:
    """Lightweight, thread-safe request telemetry middleware."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # Ignore static and media asset requests from traffic count
        path = request.path_info
        if path.startswith('/static/') or path.startswith('/media/') or path == '/favicon.ico':
            return self.get_response(request)

        start_time = time.perf_counter()
        response = self.get_response(request)
        elapsed_ms = (time.perf_counter() - start_time) * 1000.0

        # Record metrics safely without blocking response
        try:
            self._record_request_telemetry(elapsed_ms)
        except Exception:
            pass

        return response

    @staticmethod
    def _record_request_telemetry(latency_ms: float):
        now = timezone.now()
        today_key = f"nexus_reqs_day_{now.strftime('%Y%m%d')}"
        hour_key = f"nexus_reqs_hour_{now.strftime('%Y%m%d%H')}"

        try:
            if not cache.add(KEY_TOTAL_REQUESTS, 1, timeout=None):
                cache.incr(KEY_TOTAL_REQUESTS)

            if not cache.add(today_key, 1, timeout=86400 * 35):
                cache.incr(today_key)

            if not cache.add(hour_key, 1, timeout=3600 * 4):
                cache.incr(hour_key)

            with _LOCK:
                tot_lat = cache.get(KEY_TOTAL_LATENCY_MS, 0.0)
                cache.set(KEY_TOTAL_LATENCY_MS, tot_lat + latency_ms, timeout=None)

                now_sec = int(time.time())
                window_ts = cache.get(KEY_LAST_WINDOW_TS, 0)
                if now_sec == window_ts:
                    win_count = cache.get(KEY_WINDOW_REQ_COUNT, 0) + 1
                    cache.set(KEY_WINDOW_REQ_COUNT, win_count, timeout=10)
                    peak = cache.get(KEY_PEAK_RPS, 0)
                    if win_count > peak:
                        cache.set(KEY_PEAK_RPS, win_count, timeout=None)
                else:
                    cache.set(KEY_LAST_WINDOW_TS, now_sec, timeout=10)
                    cache.set(KEY_WINDOW_REQ_COUNT, 1, timeout=10)
        except Exception:
            pass


def get_traffic_telemetry():
    """Retrieve operational server traffic metrics across time intervals."""
    from accounts.models import AuditEvent, User

    now = timezone.localtime()
    today_date = timezone.localdate()
    today_key = f"nexus_reqs_day_{now.strftime('%Y%m%d')}"
    hour_key = f"nexus_reqs_hour_{now.strftime('%Y%m%d%H')}"

    recorded_total = cache.get(KEY_TOTAL_REQUESTS, 0) or 0
    recorded_today = cache.get(today_key, 0) or 0
    recorded_hour = cache.get(hour_key, 0) or 0

    requests_today = recorded_today
    requests_last_hour = recorded_hour

    requests_7d = 0
    requests_30d = 0
    for i in range(30):
        d = today_date - timedelta(days=i)
        k = f"nexus_reqs_day_{d.strftime('%Y%m%d')}"
        cnt = cache.get(k, 0) or 0
        requests_30d += cnt
        if i < 7:
            requests_7d += cnt

    if recorded_total > requests_30d:
        requests_30d = recorded_total

    avg_daily_requests = round(requests_30d / 30) if requests_30d > 0 else 0

    # Users signed in today
    try:
        active_today_users = User.objects.filter(last_login__date=today_date).count()
        audit_logins_today = AuditEvent.objects.filter(
            event_type='LOGIN_SUCCESS',
            timestamp__date=today_date,
        ).values('actor_enrollment').distinct().count()
        users_signin_today = max(active_today_users, audit_logins_today)
    except Exception:
        users_signin_today = 0

    tot_lat = cache.get(KEY_TOTAL_LATENCY_MS, 0.0)
    avg_latency = round(tot_lat / recorded_total, 1) if recorded_total > 0 else 0.0

    peak_rps = cache.get(KEY_PEAK_RPS, 0)
    uptime_seconds = int(time.time() - _START_TIME)

    return {
        'requests_today': requests_today,
        'requests_last_hour': requests_last_hour,
        'requests_7d': requests_7d,
        'requests_30d': requests_30d,
        'avg_daily_requests': avg_daily_requests,
        'users_signin_today': users_signin_today,
        'total_requests': requests_30d,
        'avg_latency_ms': avg_latency,
        'peak_rps': peak_rps,
        'uptime_seconds': uptime_seconds,
        'uptime_display': f"{max(0, uptime_seconds // 3600)}h {(uptime_seconds % 3600) // 60}m",
    }
