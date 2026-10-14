"""Campus Nexus Versioned REST API Views (v1).

Implements web/API parity for core platform resources:
- Service Catalogue
- Authentication & Session Management
- User Profile & Safety Stats
- COORDINATE Ride Discovery, Detail, Creation, Join, Leave, and History
"""

import datetime
from django.conf import settings
from django.contrib.auth import authenticate, login, logout
from django.contrib.sessions.models import Session
from django.db import IntegrityError, transaction
from django.db.models import Q
from django.http import HttpRequest, JsonResponse
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_POST, require_http_methods

from accounts.models import User
from accounts.throttling import rate_limit
from accounts.views import enforce_single_session_login
from campus.services import get_all_services, get_service_by_slug
from coordinate.models import RideParticipant, RideRequest
from coordinate.views import (
    _are_friends,
    _parse_date,
    _parse_time,
    _promote_next_waitlist_passenger,
    _user_can_join_ride,
    _user_can_see_ride,
    _user_has_active_ride,
)

from .auth import (
    api_auth_required,
    get_api_user,
    json_error,
    json_success,
    parse_json_body,
)
from .serializers import (
    serialize_ride,
    serialize_ride_detail,
    serialize_user,
)


# ---------------------------------------------------------------------------
# API Root & Service Catalogue
# ---------------------------------------------------------------------------

@require_GET
def api_root(request: HttpRequest) -> JsonResponse:
    """API entry point returning service metadata and versioned endpoints."""
    return json_success({
        "platform": "Campus Nexus",
        "version": "v1",
        "endpoints": {
            "catalogue": "/api/v1/catalogue/",
            "login": "/api/v1/auth/login/",
            "logout": "/api/v1/auth/logout/",
            "me": "/api/v1/me/",
            "rides": "/api/v1/rides/",
            "my_rides": "/api/v1/my-rides/",
        },
    })


@require_GET
def api_catalogue(request: HttpRequest) -> JsonResponse:
    """Return all platform services in the Campus Nexus directory."""
    services = get_all_services()
    return json_success({"services": services})


@require_GET
def api_service_detail(request: HttpRequest, slug: str) -> JsonResponse:
    """Return detailed capability and readiness metadata for a specific service."""
    service = get_service_by_slug(slug)
    if not service:
        return json_error(f"Service '{slug}' not found.", status=404, code="SERVICE_NOT_FOUND")
    return json_success({"service": service})


# ---------------------------------------------------------------------------
# Authentication
# ---------------------------------------------------------------------------

@csrf_exempt
@require_POST
@rate_limit(key_prefix='api_login', limit=10, period_seconds=60)
def api_login(request: HttpRequest) -> JsonResponse:
    """Authenticate student credentials and return a session token."""
    body, err = parse_json_body(request)
    if err:
        return err

    enrollment = str(body.get("enrollment_number", "")).strip().upper()
    password = str(body.get("password", ""))

    if not enrollment or not password:
        return json_error(
            "Both 'enrollment_number' and 'password' are required.",
            status=400,
            code="MISSING_CREDENTIALS",
        )

    user = authenticate(request, username=enrollment, password=password)
    if not user or not user.is_active:
        return json_error(
            "Invalid enrollment number or password, or account unverified.",
            status=401,
            code="INVALID_CREDENTIALS",
        )

    # 2FA Enforcement for students with 2FA enabled
    if user.two_factor_enabled and not (settings.DEBUG and user.is_debug_account):
        otp_code = str(body.get("otp", "")).strip()
        if not otp_code:
            from accounts.two_factor import create_phone_otp
            create_phone_otp(user, purpose="2FA")
            return json_error(
                "Two-factor authentication required. An OTP has been dispatched.",
                status=403,
                code="2FA_REQUIRED",
                details={"two_factor_required": True},
            )
        from accounts.two_factor import verify_phone_otp
        if not verify_phone_otp(user, otp_code, purpose="2FA"):
            return json_error(
                "Invalid or expired 2FA OTP code.",
                status=401,
                code="INVALID_2FA_OTP",
            )

    # Ensure a session is instantiated and single active session is enforced
    if not request.session.session_key:
        request.session.create()
    login(request, user)
    enforce_single_session_login(request, user)
    request.session.save()

    token = request.session.session_key
    return json_success(
        {
            "token": token,
            "token_type": "Bearer",
            "user": serialize_user(user, include_stats=True),
        },
        status=200,
    )


@csrf_exempt
@require_POST
def api_logout(request: HttpRequest) -> JsonResponse:
    """Invalidate session and logout current user."""
    auth_header = request.headers.get("Authorization", "") or request.META.get("HTTP_AUTHORIZATION", "")
    token = None
    if auth_header:
        parts = auth_header.split()
        if len(parts) == 2 and parts[0].lower() in ("bearer", "token"):
            token = parts[1].strip()

    if token:
        try:
            Session.objects.filter(session_key=token).delete()
            user = get_api_user(request)
            if user and user.current_session_key == token:
                user.current_session_key = ""
                user.save(update_fields=["current_session_key"])
        except Exception:
            pass

    logout(request)
    return json_success({"message": "Successfully logged out."})


# ---------------------------------------------------------------------------
# Current User Profile
# ---------------------------------------------------------------------------

@require_GET
@api_auth_required
def api_me(request: HttpRequest) -> JsonResponse:
    """Return profile and active ride for the authenticated user."""
    user = request.api_user
    user_data = serialize_user(user, include_stats=True)

    active_p = (
        RideParticipant.objects
        .filter(user=user, ride__status__in=["OPEN", "FULL"])
        .select_related("ride", "ride__creator")
        .first()
    )

    active_ride_data = None
    if active_p:
        active_ride_data = serialize_ride(active_p.ride, request_user=user)

    return json_success({
        "user": user_data,
        "active_ride": active_ride_data,
    })


# ---------------------------------------------------------------------------
# COORDINATE Ride Endpoints
# ---------------------------------------------------------------------------

@require_GET
def api_ride_list(request: HttpRequest) -> JsonResponse:
    """List open rides respecting filters and audience comfort gates."""
    user = get_api_user(request)
    now = timezone.now()

    rides = (
        RideRequest.objects
        .filter(status="OPEN", departure_time__gt=now)
        .select_related("creator")
        .prefetch_related("participants")
        .order_by("departure_time")
    )

    # Route and location filtering
    route = request.GET.get("route", "").strip().upper()
    if route:
        rides = rides.filter(route=route)

    origin = request.GET.get("origin", "").strip()
    if origin:
        rides = rides.filter(
            Q(custom_from_location__icontains=origin) |
            Q(route__icontains=origin)
        )

    destination = request.GET.get("destination", "").strip()
    if destination:
        rides = rides.filter(
            Q(custom_to_location__icontains=destination) |
            Q(route__icontains=destination)
        )

    visibility = request.GET.get("visibility", "").strip().upper()
    if visibility:
        rides = rides.filter(visibility=visibility)

    # Date-time range filtering
    date_from_str = request.GET.get("date_from", "").strip() or request.GET.get("date", "").strip()
    date_to_str = request.GET.get("date_to", "").strip()
    time_from_str = request.GET.get("time_from", "").strip() or request.GET.get("time", "").strip()
    time_to_str = request.GET.get("time_to", "").strip()

    parsed_date_from = _parse_date(date_from_str)
    parsed_date_to = _parse_date(date_to_str)
    parsed_time_from = _parse_time(time_from_str)
    parsed_time_to = _parse_time(time_to_str)

    current_tz = timezone.get_current_timezone()

    if parsed_date_from:
        start_t = parsed_time_from or datetime.time(0, 0, 0)
        start_dt = timezone.make_aware(datetime.datetime.combine(parsed_date_from, start_t), current_tz)
        rides = rides.filter(departure_time__gte=start_dt)

    if parsed_date_to:
        end_t = parsed_time_to or datetime.time(23, 59, 59)
        end_dt = timezone.make_aware(datetime.datetime.combine(parsed_date_to, end_t), current_tz)
        rides = rides.filter(departure_time__lte=end_dt)
    elif parsed_date_from and not parsed_date_to and not request.GET.get("date_from"):
        # Single 'date' parameter passed: constrain to that day
        end_t = parsed_time_to or datetime.time(23, 59, 59)
        end_dt = timezone.make_aware(datetime.datetime.combine(parsed_date_from, end_t), current_tz)
        rides = rides.filter(departure_time__lte=end_dt)

    # Server-authoritative audience comfort gating
    visible_rides = []
    for ride in rides:
        if user:
            if _user_can_see_ride(user, ride):
                visible_rides.append(serialize_ride(ride, request_user=user))
        else:
            # Unauthenticated browse: only show MIXED rides
            if ride.visibility == "MIXED":
                visible_rides.append(serialize_ride(ride, request_user=None))

    return json_success({
        "count": len(visible_rides),
        "rides": visible_rides,
    })


@require_GET
def api_ride_detail(request: HttpRequest, ride_id: int) -> JsonResponse:
    """Return full details and participant list for a specific ride."""
    user = get_api_user(request)
    ride = (
        RideRequest.objects
        .filter(pk=ride_id)
        .select_related("creator")
        .prefetch_related("participants")
        .first()
    )
    if not ride:
        return json_error("Ride not found.", status=404, code="RIDE_NOT_FOUND")

    # Visibility check
    if user and not _user_can_see_ride(user, ride):
        return json_error("You do not have permission to view this ride.", status=403, code="FORBIDDEN")
    if not user and ride.visibility != "MIXED":
        return json_error("Authentication required to view restricted rides.", status=401, code="AUTH_REQUIRED")

    return json_success({"ride": serialize_ride_detail(ride, request_user=user)})


@csrf_exempt
@require_POST
@api_auth_required
def api_ride_create(request: HttpRequest) -> JsonResponse:
    """Create a new ride request adhering to all domain invariants."""
    user = request.api_user

    # One active ride invariant
    if _user_has_active_ride(user):
        return json_error(
            "You already have an active ride. Leave or complete it first.",
            status=409,
            code="ACTIVE_RIDE_EXISTS",
        )

    body, err = parse_json_body(request)
    if err:
        return err

    route = str(body.get("route", "")).strip().upper()
    origin = str(body.get("origin", "")).strip()
    destination = str(body.get("destination", "")).strip()
    custom_from = str(body.get("custom_from_location", "")).strip() or origin
    custom_to = str(body.get("custom_to_location", "")).strip() or destination
    dep_str = str(body.get("departure_time", "")).strip()
    total_spots = body.get("total_spots", 3)
    visibility = str(body.get("visibility", "MIXED")).strip().upper()

    if not dep_str:
        return json_error(
            "'departure_time' is required.",
            status=400,
            code="MISSING_DEPARTURE",
        )

    valid_routes = [c[0] for c in RideRequest.ROUTE_CHOICES]
    if route in valid_routes:
        resolved_route = route
    elif "AIRPORT" in custom_to.upper() and ("NIT" in custom_from.upper() or not custom_from):
        resolved_route = "NIT_TO_AIRPORT"
    elif "AIRPORT" in custom_from.upper() and ("NIT" in custom_to.upper() or not custom_to):
        resolved_route = "AIRPORT_TO_NIT"
    elif ("STATION" in custom_to.upper() or "RAILWAY" in custom_to.upper()) and ("NIT" in custom_from.upper() or not custom_from):
        resolved_route = "NIT_TO_STATION"
    elif ("STATION" in custom_from.upper() or "RAILWAY" in custom_from.upper()) and ("NIT" in custom_to.upper() or not custom_to):
        resolved_route = "STATION_TO_NIT"
    elif custom_from and custom_to:
        resolved_route = "CUSTOM"
    else:
        resolved_route = "NIT_TO_AIRPORT"

    if resolved_route == "CUSTOM" and (not custom_from or not custom_to):
        return json_error(
            "For custom routes, both origin and destination are required.",
            status=400,
            code="MISSING_FIELDS",
        )

    # Validate departure_time
    dep_time = parse_datetime(dep_str)
    if not dep_time:
        return json_error(
            "Invalid 'departure_time' format. Use ISO 8601 (YYYY-MM-DDTHH:MM[:SS]).",
            status=400,
            code="INVALID_DATETIME",
        )

    if timezone.is_naive(dep_time):
        dep_time = timezone.make_aware(dep_time, timezone.get_current_timezone())

    now = timezone.now()
    if dep_time <= now:
        return json_error("Departure time must be in the future.", status=400, code="PAST_DEPARTURE")

    max_horizon = now + datetime.timedelta(days=30)
    if dep_time > max_horizon:
        return json_error("Departure cannot be scheduled more than 30 days in advance.", status=400, code="HORIZON_EXCEEDED")

    # Validate spots
    try:
        total_spots = int(total_spots)
        if not (1 <= total_spots <= 6):
            raise ValueError()
    except (ValueError, TypeError):
        return json_error("'total_spots' must be an integer between 1 and 6.", status=400, code="INVALID_SPOTS")

    # Validate visibility choices & creator eligibility
    valid_vis = [c[0] for c in RideRequest.VISIBILITY_CHOICES]
    if visibility not in valid_vis:
        return json_error(f"'visibility' must be one of {valid_vis}.", status=400, code="INVALID_VISIBILITY")

    if visibility == "GIRLS" and user.gender != "F":
        return json_error("Only female students can create Girls Only rides.", status=403, code="GENDER_MISMATCH")
    if visibility == "BOYS" and user.gender != "M":
        return json_error("Only male students can create Boys Only rides.", status=403, code="GENDER_MISMATCH")

    with transaction.atomic():
        ride = RideRequest.objects.create(
            creator=user,
            route=resolved_route,
            custom_from_location=custom_from if resolved_route == "CUSTOM" else "",
            custom_to_location=custom_to if resolved_route == "CUSTOM" else "",
            departure_time=dep_time,
            total_spots=total_spots,
            visibility=visibility,
            status="OPEN",
        )
        RideParticipant.objects.create(ride=ride, user=user)
        ride.sync_status()

    return json_success({"ride": serialize_ride_detail(ride, request_user=user)}, status=201)


@csrf_exempt
@require_POST
@api_auth_required
def api_ride_join(request: HttpRequest, ride_id: int) -> JsonResponse:
    """Atomically join an open ride."""
    user = request.api_user

    with transaction.atomic():
        ride = (
            RideRequest.objects
            .select_for_update()
            .filter(pk=ride_id)
            .first()
        )
        if not ride:
            return json_error("Ride not found.", status=404, code="RIDE_NOT_FOUND")

        if not _user_can_join_ride(user, ride):
            # Detailed diagnostics
            if ride.kicked_users.filter(id=user.id).exists():
                return json_error("You were previously removed from this ride.", status=403, code="USER_KICKED")
            if _user_has_active_ride(user):
                return json_error("You already have an active ride.", status=409, code="ACTIVE_RIDE_EXISTS")
            if ride.status != "OPEN":
                return json_error(f"Cannot join ride in '{ride.status}' status.", status=409, code="RIDE_NOT_OPEN")
            if not _user_can_see_ride(user, ride):
                return json_error("You do not meet the audience criteria for this ride.", status=403, code="AUDIENCE_MISMATCH")
            return json_error("Unable to join ride.", status=400, code="JOIN_REJECTED")

        try:
            RideParticipant.objects.create(ride=ride, user=user)
            ride.sync_status()
        except IntegrityError:
            return json_error("You are already a participant in this ride.", status=409, code="ALREADY_PARTICIPANT")

    ride.refresh_from_db()
    return json_success({
        "message": "Successfully joined ride.",
        "ride": serialize_ride_detail(ride, request_user=user),
    })


@csrf_exempt
@require_POST
@api_auth_required
def api_ride_leave(request: HttpRequest, ride_id: int) -> JsonResponse:
    """Atomically leave or cancel a ride."""
    user = request.api_user

    with transaction.atomic():
        ride = (
            RideRequest.objects
            .select_for_update()
            .filter(pk=ride_id)
            .first()
        )
        if not ride:
            return json_error("Ride not found.", status=404, code="RIDE_NOT_FOUND")

        if ride.status in ["COMPLETED", "CANCELLED"]:
            return json_error("Cannot leave a completed or cancelled ride.", status=409, code="RIDE_CONCLUDED")

        if ride.creator == user:
            return json_error("Hosts cannot leave their own ride. Cancel or terminate the ride instead.", status=400, code="HOST_CANNOT_LEAVE")

        participant = RideParticipant.objects.filter(ride=ride, user=user).first()
        if not participant:
            return json_error("You are not a participant in this ride.", status=400, code="NOT_A_PARTICIPANT")

        participant.delete()
        ride.left_users.add(user)

        remaining = RideParticipant.objects.filter(ride=ride).count()
        if remaining == 0:
            if ride.messages.exists() or ride.status == "COMPLETED":
                ride.status = "CANCELLED"
                ride.save(update_fields=["status"])
            else:
                ride.delete()
                return json_success({"message": "Ride cancelled and cleared."})
        else:
            ride.sync_status()
            _promote_next_waitlist_passenger(ride)

    ride.refresh_from_db()
    return json_success({
        "message": "Successfully left ride.",
        "ride": serialize_ride(ride, request_user=user),
    })


@require_GET
@api_auth_required
def api_my_rides(request: HttpRequest) -> JsonResponse:
    """Return user's active ride and historical rides."""
    user = request.api_user
    participations = (
        RideParticipant.objects
        .filter(user=user)
        .select_related("ride", "ride__creator")
        .order_by("-ride__departure_time")
    )

    now = timezone.now()
    two_hours_ago = now - datetime.timedelta(hours=2)

    active_rides = []
    past_rides = []

    for p in participations:
        ride = p.ride
        serialized = serialize_ride(ride, request_user=user)
        if ride.status in ["OPEN", "FULL"] and ride.departure_time > two_hours_ago:
            active_rides.append(serialized)
        else:
            past_rides.append(serialized)

    return json_success({
        "active_rides": active_rides,
        "past_rides": past_rides,
    })
