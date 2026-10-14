"""Campus Nexus API Serializers.

Provides clean serialization of accounts, rides, and catalogue entries
with strict field minimization and privacy preservation.
"""

from typing import Any, Dict, List, Optional
from accounts.models import User
from coordinate.models import RideRequest


def serialize_user(user: User, include_stats: bool = False) -> Dict[str, Any]:
    """Serialize user profile with sensitive fields redacted."""
    data = {
        "id": user.id,
        "enrollment_number": user.enrollment_number,
        "name": user.display_name,
        "branch": user.branch,
        "degree": user.degree,
        "gender": user.gender,
        "joining_year": user.joining_year,
        "is_verified": user.is_active,
    }
    if include_stats:
        data.update({
            "on_time_percentage": float(user.on_time_percentage),
            "rides_completed": user.rides_completed,
            "on_time_count": user.on_time_count,
            "late_count": user.late_count,
            "no_show_count": user.no_show_count,
        })
    return data


def serialize_ride(ride: RideRequest, request_user: Optional[User] = None) -> Dict[str, Any]:
    """Serialize ride summary for lists and cards."""
    data = {
        "id": ride.id,
        "route": ride.route,
        "route_display": ride.route_display,
        "custom_from_location": ride.custom_from_location or "",
        "custom_to_location": ride.custom_to_location or "",
        "departure_time": ride.departure_time.isoformat(),
        "status": ride.status,
        "visibility": ride.visibility,
        "visibility_display": ride.get_visibility_display(),
        "total_spots": ride.total_spots,
        "available_spots": ride.spots_remaining(),
        "creator": {
            "enrollment_number": ride.creator.enrollment_number,
            "name": ride.creator.display_name,
            "gender": ride.creator.gender,
        },
    }
    if request_user:
        data["is_user_participant"] = ride.participants.filter(pk=request_user.pk).exists()
        data["is_user_creator"] = ride.creator_id == request_user.pk
    return data


def serialize_ride_detail(ride: RideRequest, request_user: Optional[User] = None) -> Dict[str, Any]:
    """Serialize full ride details including confirmed participants."""
    data = serialize_ride(ride, request_user=request_user)
    participants = []
    for p in ride.participants.select_related('user').all():
        u = p.user
        participants.append({
            "enrollment_number": u.enrollment_number,
            "name": u.display_name,
            "gender": u.gender,
            "is_creator": u.pk == ride.creator_id,
        })
    data["participants"] = participants
    return data
