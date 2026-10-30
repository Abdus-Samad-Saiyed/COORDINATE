"""Campus Nexus Service Registry and Catalogue.

Defines the modular service offerings provided under the Campus Nexus umbrella platform.
Services can be active (e.g. COORDINATE) or in development (e.g. PRINT HUB).
"""

from typing import Any, Dict, List, Optional
from django.core.exceptions import PermissionDenied
from django.http import Http404, HttpRequest, HttpResponse
from django.shortcuts import redirect, render

SERVICE_CATALOGUE: List[Dict[str, Any]] = [
    {
        "id": "coordinate",
        "slug": "coordinate",
        "name": "COORDINATE",
        "tagline": "Campus Ride Sharing & Commute",
        "description": "Coordinate cab shares to Srinagar Airport, Railway Station, or across town with verified NIT peers.",
        "icon": "bi-car-front-fill",
        "route_name": "ride_list",
        "url": "/coordinate/rides/",
        "is_active": True,
        "status_badge": "Live",
        "badge_class": "badge-open",
        "requires_auth": True,
        "features": [
            "Real-time ride discovery & filtering",
            "Gender-specific & friends-only comfort gates",
            "WebSocket live coordination chat",
            "Peer punctuality & attendance tracking",
        ],
    },
    {
        "id": "stationery_print",
        "slug": "print-hub",
        "name": "PRINT HUB",
        "tagline": "Campus Xerox & Queueless Printing",
        "description": "Upload assignments, lab manuals, and research drafts for instant pickup at central campus stationery shops.",
        "icon": "bi-printer-fill",
        "route_name": "service_print_hub",
        "url": "/services/print-hub/",
        "is_active": False,
        "status_badge": "In Development",
        "badge_class": "badge-completed",
        "requires_auth": True,
        "features": [
            "Queueless PDF upload & cloud queueing",
            "Per-page automated billing calculation",
            "Shopkeeper dispatch notifications",
        ],
    },
    {
        "id": "lost_found",
        "slug": "lost-found",
        "name": "LOST & FOUND",
        "tagline": "Campus Property & Document Directory",
        "description": "Report or claim misplaced identity cards, notebooks, and electronics across academic blocks and hostels.",
        "icon": "bi-search",
        "route_name": "service_lost_found",
        "url": "/services/lost-found/",
        "is_active": False,
        "status_badge": "In Development",
        "badge_class": "badge-completed",
        "requires_auth": True,
        "features": [
            "Categorized lost & found photo listings",
            "Security booth verification matching",
            "Direct claimant hand-over logging",
        ],
    },
    {
        "id": "mess_menu",
        "slug": "mess-menu",
        "name": "MESS MATE",
        "tagline": "Hostel Daily Menus & Feedback",
        "description": "Check daily hostel breakfast, lunch, and dinner menus with live student ratings and dietary notices.",
        "icon": "bi-egg-fried",
        "route_name": "service_mess_menu",
        "url": "/services/mess-menu/",
        "is_active": False,
        "status_badge": "In Development",
        "badge_class": "badge-completed",
        "requires_auth": True,
        "features": [
            "Daily updated hostel meal schedules",
            "Special occasion feast alerts",
            "Warden feedback & hygiene review log",
        ],
    },
]


def get_all_services() -> List[Dict[str, Any]]:
    """Return all services in the catalogue."""
    return SERVICE_CATALOGUE


def get_active_services() -> List[Dict[str, Any]]:
    """Return only active/live services."""
    return [svc for svc in SERVICE_CATALOGUE if svc["is_active"]]


def get_service_by_slug(slug: str) -> Optional[Dict[str, Any]]:
    """Lookup a service entry by its slug or ID."""
    for svc in SERVICE_CATALOGUE:
        if svc["slug"] == slug or svc["id"] == slug:
            return svc
    return None


def service_gateway_view(request: HttpRequest, slug: str) -> HttpResponse:
    """Server-authoritative gateway for service access.
    
    Active services are redirected to their root view.
    Inactive/in-development services return HTTP 403 Forbidden with clear diagnostic information,
    preventing direct bypass of catalogue availability state.
    """
    service = get_service_by_slug(slug)
    if not service:
        raise Http404(f"Campus Nexus service '{slug}' not found.")

    if service["is_active"]:
        return redirect(service["url"])

    # Service is in development - enforce server-side 403
    return render(
        request,
        "nexus/service_unavailable.html",
        {
            "service": service,
            "catalogue": SERVICE_CATALOGUE,
        },
        status=403,
    )
