"""
Client request identity tracking and console log enrichment for Daphne and Django.

Maintains a thread-safe registry of in-flight client requests keyed by client connection address
(host:port). Enriches HTTP and WebSocket request logs with:
  [duration, client_ip:port, enrollment_number, full_name]
where unauthenticated requests display N.A. for enrollment and name.
"""

import collections
import logging
import threading
import time

logger = logging.getLogger("django.channels.server")

# Maximum lifetime of a queued client record in seconds (prevents memory accumulation on dropped sockets)
CLIENT_META_TTL_SECONDS = 120

# Thread-safe mapping: client_key (e.g. '127.0.0.1:65521') -> collections.deque of request metadata dicts
_CLIENT_REGISTRY = collections.defaultdict(collections.deque)
_REGISTRY_LOCK = threading.Lock()


def resolve_client_display(client_key: str | None, real_ip: str | None = None) -> str:
    """Format client connection address to reflect the client IP (and port if known).
    
    If real_ip is provided (from headers like CF-Connecting-IP or X-Forwarded-For) and is not
    loopback, it replaces the loopback IP while preserving the client connection port.
    """
    if not client_key:
        return real_ip or "127.0.0.1"

    port = None
    if ":" in client_key:
        parts = client_key.rsplit(":", 1)
        if parts[1].isdigit():
            port = parts[1]

    if real_ip and real_ip not in ("127.0.0.1", "::1", "localhost"):
        return f"{real_ip}:{port}" if port else real_ip

    return client_key


def _clean_expired_entries_locked(now: float):
    """Prune stale request records older than CLIENT_META_TTL_SECONDS."""
    to_delete = []
    for key, q in _CLIENT_REGISTRY.items():
        while q and (now - q[0]["ts"] > CLIENT_META_TTL_SECONDS):
            q.popleft()
        if not q:
            to_delete.append(key)
    for key in to_delete:
        _CLIENT_REGISTRY.pop(key, None)


def seed_client_request(
    client_key: str | None,
    enrollment: str = "N.A.",
    name: str = "N.A.",
    real_client: str | None = None,
):
    """Pre-seed client metadata when an ASGI connection or request scope is initialized."""
    if not client_key:
        client_key = "DEFAULT"

    now = time.time()
    with _REGISTRY_LOCK:
        _clean_expired_entries_locked(now)
        _CLIENT_REGISTRY[client_key].append({
            "enrollment": enrollment or "N.A.",
            "name": name or "N.A.",
            "real_client": real_client or client_key,
            "ts": now,
        })


def update_or_record_client_request(
    client_key: str | None,
    enrollment: str = "N.A.",
    name: str = "N.A.",
    real_client: str | None = None,
):
    """Update the in-flight request entry with authenticated user details from Django middleware."""
    if not client_key:
        client_key = "DEFAULT"

    now = time.time()
    with _REGISTRY_LOCK:
        _clean_expired_entries_locked(now)
        queue = _CLIENT_REGISTRY[client_key]
        if queue:
            latest = queue[-1]
            if enrollment and enrollment != "N.A.":
                latest["enrollment"] = enrollment
            elif not latest.get("enrollment"):
                latest["enrollment"] = "N.A."

            if name and name != "N.A.":
                latest["name"] = name
            elif not latest.get("name"):
                latest["name"] = "N.A."

            if real_client:
                latest["real_client"] = real_client
            latest["ts"] = now
        else:
            queue.append({
                "enrollment": enrollment or "N.A.",
                "name": name or "N.A.",
                "real_client": real_client or client_key,
                "ts": now,
            })


def pop_client_request(client_key: str | None) -> dict:
    """Retrieve and pop the earliest recorded metadata for the client connection."""
    if not client_key:
        client_key = "DEFAULT"

    now = time.time()
    with _REGISTRY_LOCK:
        _clean_expired_entries_locked(now)
        queue = _CLIENT_REGISTRY.get(client_key)
        if queue and len(queue) > 0:
            item = queue.popleft()
            if not queue:
                _CLIENT_REGISTRY.pop(client_key, None)
            return item

    return {
        "enrollment": "N.A.",
        "name": "N.A.",
        "real_client": client_key if client_key != "DEFAULT" else "127.0.0.1",
        "ts": now,
    }


class ClientLoggingASGIWrapper:
    """ASGI application wrapper that seeds client identity metadata before
    the request reaches static file handlers or Django middleware.
    """

    def __init__(self, inner):
        self.inner = inner

    async def __call__(self, scope, receive, send):
        if scope.get("type") in ("http", "websocket"):
            client = scope.get("client")
            if client:
                client_key = f"{client[0]}:{client[1]}"
                headers = dict(scope.get("headers", []))
                real_ip = None
                if b"cf-connecting-ip" in headers:
                    real_ip = headers[b"cf-connecting-ip"].decode("latin1").strip()
                elif b"x-forwarded-for" in headers:
                    real_ip = headers[b"x-forwarded-for"].decode("latin1").split(",")[0].strip()

                real_client = resolve_client_display(client_key, real_ip)
                user = scope.get("user")
                enrollment = "N.A."
                name = "N.A."
                if user and getattr(user, "is_authenticated", False):
                    enrollment = getattr(user, "enrollment_number", "") or getattr(user, "username", "N.A.") or "N.A."
                    full_name = user.get_full_name() if hasattr(user, "get_full_name") else ""
                    name = full_name.strip() or getattr(user, "display_name", "") or getattr(user, "username", "") or enrollment
                    if not name:
                        name = "N.A."

                seed_client_request(client_key, enrollment=enrollment, name=name, real_client=real_client)

        return await self.inner(scope, receive, send)
