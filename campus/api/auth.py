"""Campus Nexus API Authentication and Response Helpers.

Provides token and session authentication for versioned REST API endpoints.
Mobile clients use Bearer tokens (Django session keys) in the Authorization header.
Web clients can use either Bearer tokens or standard session cookies.
"""

import json
from functools import wraps
from typing import Any, Callable, Dict, Optional, Tuple

from django.contrib.auth import get_user_model
from django.contrib.sessions.models import Session
from django.http import HttpRequest, JsonResponse
from django.utils import timezone

User = get_user_model()


def json_success(data: Any = None, status: int = 200, **kwargs) -> JsonResponse:
    """Return a standardized JSON success response."""
    payload: Dict[str, Any] = {
        "status": "success",
    }
    if data is not None:
        payload["data"] = data
    for k, v in kwargs.items():
        payload[k] = v
    return JsonResponse(payload, status=status)


def json_error(
    message: str,
    status: int = 400,
    code: Optional[str] = None,
    details: Optional[Any] = None,
) -> JsonResponse:
    """Return a standardized JSON error response."""
    payload: Dict[str, Any] = {
        "status": "error",
        "error": message,
        "code": code or f"ERR_{status}",
    }
    if details is not None:
        payload["details"] = details
    return JsonResponse(payload, status=status)


def get_api_user(request: HttpRequest) -> Optional[Any]:
    """Resolve user from Authorization header or standard session."""
    # 1. Check Authorization header: 'Bearer <token>' or 'Token <token>'
    auth_header = request.headers.get("Authorization", "") or request.META.get("HTTP_AUTHORIZATION", "")
    if auth_header:
        parts = auth_header.split()
        if len(parts) == 2 and parts[0].lower() in ("bearer", "token"):
            token = parts[1].strip()
            try:
                session = Session.objects.filter(session_key=token).first()
                if session and session.expire_date > timezone.now():
                    session_data = session.get_decoded()
                    user_id = session_data.get("_auth_user_id")
                    if user_id:
                        user = User.objects.filter(pk=user_id, is_active=True).first()
                        if user:
                            return user
            except Exception:
                pass
        return None

    # 2. Check standard cookie session authentication
    if getattr(request, "user", None) and request.user.is_authenticated and request.user.is_active:
        return request.user

    return None


def api_auth_required(view_func: Callable) -> Callable:
    """Decorator requiring valid user authentication for API endpoints."""
    @wraps(view_func)
    def wrapped_view(request: HttpRequest, *args, **kwargs):
        user = get_api_user(request)
        if not user:
            return json_error("Authentication required.", status=401, code="AUTH_REQUIRED")
        request.api_user = user
        return view_func(request, *args, **kwargs)

    return wrapped_view


def parse_json_body(request: HttpRequest) -> Tuple[Optional[Dict[str, Any]], Optional[JsonResponse]]:
    """Helper to parse JSON request bodies safely."""
    if not request.body:
        return {}, None
    try:
        data = json.loads(request.body.decode("utf-8"))
        if not isinstance(data, dict):
            return None, json_error("Request body must be a JSON object.", status=400, code="INVALID_JSON")
        return data, None
    except (json.JSONDecodeError, UnicodeDecodeError):
        return None, json_error("Malformed JSON payload.", status=400, code="MALFORMED_JSON")
