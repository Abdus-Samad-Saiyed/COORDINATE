"""Campus Nexus API Serializers.

Provides clean serialization of accounts, rides, and catalogue entries
with strict field minimization and privacy preservation.
"""

from typing import Any, Dict, List, Optional
from accounts.models import User
from coordinate.models import RideRequest
from coordinate.policies import can_view_ride_identity


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
        "is_verified": user.verified,
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
            "enrollment_number": ride.creator.enrollment_number if not request_user or can_view_ride_identity(request_user, ride, ride.creator) else "PROTECTED",
            "name": ride.creator.display_name if not request_user or can_view_ride_identity(request_user, ride, ride.creator) else (f"Student ({ride.creator.gender})" if ride.creator.gender else "Student"),
            "gender": ride.creator.gender,
        },
    }
    if request_user:
        data["is_user_participant"] = ride.participants.filter(user=request_user).exists()
        data["is_user_creator"] = ride.creator_id == request_user.pk
    return data


def serialize_ride_detail(ride: RideRequest, request_user: Optional[User] = None) -> Dict[str, Any]:
    """Serialize full ride details including confirmed participants with affirmative consent contact controls."""
    from coordinate.policies import can_view_ride_contact

    data = serialize_ride(ride, request_user=request_user)
    participants = []
    for p in ride.participants.select_related('user').all():
        u = p.user
        can_see_id = not request_user or can_view_ride_identity(request_user, ride, u)
        p_info = {
            "enrollment_number": u.enrollment_number if can_see_id else "PROTECTED",
            "name": u.display_name if can_see_id else (f"Student ({u.gender})" if u.gender else "Student"),
            "gender": u.gender,
            "is_creator": u.pk == ride.creator_id,
        }
        if request_user and can_view_ride_contact(request_user, ride, u):
            p_info["phone_number"] = u.phone_number
            p_info["email"] = u.email

        participants.append(p_info)
    data["participants"] = participants
    return data
