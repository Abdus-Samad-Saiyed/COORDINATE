"""
Centralized state transition engine for ride participation.
Enforces the lifecycle state machine, validation rules, and atomic row locking.
"""

from typing import Any, Dict, Optional
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from coordinate.models import ParticipantStatus, RideParticipant, RideRequest


# Allowed source statuses for each target status
ALLOWED_TRANSITIONS: Dict[str, list] = {
    # Entry transitions (None means row did not exist yet)
    ParticipantStatus.PENDING: [None, ParticipantStatus.LEFT, ParticipantStatus.DECLINED, ParticipantStatus.CANCELLED],
    ParticipantStatus.WAITLISTED: [None, ParticipantStatus.LEFT, ParticipantStatus.DECLINED, ParticipantStatus.CANCELLED],
    ParticipantStatus.CONFIRMED: [None, ParticipantStatus.PENDING, ParticipantStatus.WAITLISTED],

    # Moderation / host actions
    ParticipantStatus.DECLINED: [ParticipantStatus.PENDING],
    ParticipantStatus.KICKED: [ParticipantStatus.CONFIRMED],

    # Student voluntary exits
    ParticipantStatus.LEFT: [ParticipantStatus.CONFIRMED],
    ParticipantStatus.CANCELLED: [ParticipantStatus.PENDING, ParticipantStatus.WAITLISTED],
}


@transaction.atomic
def transition_participant_state(
    ride: RideRequest,
    user: Any,
    target_status: str,
    *,
    note: str = '',
    consent_data: Optional[Dict[str, Any]] = None,
    actor: Optional[Any] = None,
) -> RideParticipant:
    """
    Executes an atomic, validated state transition for a ride participant under row locking.
    Follows lock order: User (caller) -> RideRequest (caller) -> RideParticipant (locked here).
    """
    row = RideParticipant.all_rows.select_for_update().filter(ride=ride, user=user).first()
    current_status = row.status if row else None

    # Validate transition against state machine
    allowed_sources = ALLOWED_TRANSITIONS.get(target_status, [])
    if current_status not in allowed_sources:
        raise ValidationError(
            f"Illegal state transition from {current_status or 'NONE'} to {target_status} "
            f"for user {user.pk} on ride {ride.pk}."
        )

    now = timezone.now()
    if not row:
        row = RideParticipant(ride=ride, user=user)

    row.status = target_status

    if note:
        row.note = note

    # Reset FIFO queue key whenever entering a queue
    if target_status in (ParticipantStatus.PENDING, ParticipantStatus.WAITLISTED):
        row.queued_at = now
        row.reviewed_at = None

    if target_status in (ParticipantStatus.CONFIRMED, ParticipantStatus.DECLINED):
        row.reviewed_at = now

    # Apply consent attributes if provided
    if consent_data:
        if 'consent_version' in consent_data:
            row.consent_version = consent_data['consent_version']
        if 'disclose_ride_identity' in consent_data:
            row.disclose_ride_identity = consent_data['disclose_ride_identity']
        if 'share_contact_details' in consent_data:
            row.share_contact_details = consent_data['share_contact_details']
        if 'ip_address' in consent_data:
            row.ip_address = consent_data['ip_address']
        row.consent_granted_at = now
        row.is_revoked = False
        row.revoked_at = None

    # If exiting or kicked, revoke consent flags
    if target_status in (ParticipantStatus.LEFT, ParticipantStatus.KICKED, ParticipantStatus.CANCELLED):
        row.is_revoked = True
        row.revoked_at = now

    row.full_clean()
    row.save()
    return row
