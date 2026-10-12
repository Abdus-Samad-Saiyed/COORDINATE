"""
Views for the coordinate (ride coordination) app.

URL summary:
  /coordinate/                            → ride_list
  /coordinate/create/                     → create_ride
  /coordinate/<id>/                       → ride_detail
  /coordinate/<id>/join/                  → join_ride
  /coordinate/<id>/leave/                 → leave_ride
  /coordinate/<id>/terminate/             → terminate_ride
  /coordinate/<id>/complete/              → complete_ride
  /coordinate/<id>/kick/<participant_id>/ → kick_participant
  /coordinate/<id>/review/<user_id>/      → review_user
  /coordinate/<id>/message/              → send_message (WS fallback)
"""

import datetime

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import IntegrityError, transaction
from django.db.models import Count, Prefetch, Q
from django.http import Http404, HttpResponse, HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from accounts.models import Friendship, User

from .forms import RideMessageForm, RideRequestForm, RideReviewForm
from .models import RideMessage, RideParticipant, RideRequest


# ---------------------------------------------------------------------------
# Access helpers
# ---------------------------------------------------------------------------

def _user_has_active_ride(user) -> bool:
    """True if the user is a participant in any OPEN or FULL ride."""
    return RideParticipant.objects.filter(
        user=user,
        ride__status__in=['OPEN', 'FULL'],
    ).exists()


def _are_friends(user1, user2) -> bool:
    """True if user1 and user2 have a Friendship record in either direction."""
    return Friendship.objects.filter(
        Q(user1=user1, user2=user2) | Q(user1=user2, user2=user1)
    ).exists()


def _user_can_see_ride(user, ride) -> bool:
    """
    Visibility rules:
      MIXED   → everyone
      BOYS    → male users only
      GIRLS   → female users only
      FRIENDS → creator's friends only (creator can always see their own rides)
    Participants and the creator can always see the ride regardless.
    """
    # Creator and existing participants always have access
    if ride.creator_id == user.pk:
        return True
    if RideParticipant.objects.filter(ride=ride, user=user).exists():
        return True

    v = ride.visibility
    if v == 'MIXED':
        return True
    if v == 'BOYS':
        return user.gender == 'M'
    if v == 'GIRLS':
        return user.gender == 'F'
    if v == 'FRIENDS':
        return _are_friends(user, ride.creator)
    return False


def _user_can_join_ride(user, ride) -> bool:
    """
    All conditions that must be satisfied to join:
      1. Ride is OPEN
      2. Departure is in the future
      3. User can see the ride (visibility check)
      4. User is not already a participant
      5. User doesn't have another active ride
    """
    if ride.status != 'OPEN':
        return False
    if ride.departure_time <= timezone.now():
        return False
    if not _user_can_see_ride(user, ride):
        return False
    if RideParticipant.objects.filter(ride=ride, user=user).exists():
        return False
    if _user_has_active_ride(user):
        return False
    return True


def _parse_date(value: str):
    try:
        return datetime.date.fromisoformat(value)
    except (ValueError, TypeError):
        return None


def _parse_time(value: str):
    try:
        return datetime.time.fromisoformat(value)
    except (ValueError, TypeError):
        return None


# ---------------------------------------------------------------------------
# Ride list
# ---------------------------------------------------------------------------

@login_required
def ride_list(request):
    """Browse open rides with optional filters. Applies visibility rules."""
    selected_route = request.GET.get('route', '')
    selected_visibility = request.GET.get('visibility', '')
    selected_date_str = request.GET.get('date', '')
    selected_time_str = request.GET.get('time', '')

    selected_date = _parse_date(selected_date_str) or timezone.now().date()
    selected_time = _parse_time(selected_time_str)

    # Base queryset: open rides in the future
    rides_qs = (
        RideRequest.objects
        .filter(
            status__in=['OPEN', 'FULL'],
            departure_time__date=selected_date,
        )
        .select_related('creator')
        .annotate(participants_total=Count('participants'))
        .order_by('-participants_total', 'departure_time')
    )

    valid_routes = {r[0] for r in RideRequest.ROUTE_CHOICES}
    valid_visibilities = {v[0] for v in RideRequest.VISIBILITY_CHOICES}

    if selected_route and selected_route in valid_routes:
        rides_qs = rides_qs.filter(route=selected_route)
    if selected_visibility and selected_visibility in valid_visibilities:
        rides_qs = rides_qs.filter(visibility=selected_visibility)
    if selected_time:
        rides_qs = rides_qs.filter(departure_time__time__gte=selected_time)

    # Apply Python-level visibility filter (requires friendship lookup)
    rides = [r for r in rides_qs if _user_can_see_ride(request.user, r)]

    joined_ride_ids = set(
        RideParticipant.objects
        .filter(user=request.user, ride__in=rides)
        .values_list('ride_id', flat=True)
    )

    has_active_ride = _user_has_active_ride(request.user)

    # Creator's own active ride (for terminate button)
    my_ride = (
        RideRequest.objects
        .filter(creator=request.user, status__in=['OPEN', 'FULL'])
        .first()
    )

    # Quick-select date strip: 3 days before and 3 after selected date
    date_options = [
        selected_date + datetime.timedelta(days=i)
        for i in range(-3, 4)
    ]

    return render(request, 'coordinate/ride_list.html', {
        'rides': rides,
        'joined_ride_ids': joined_ride_ids,
        'has_active_ride': has_active_ride,
        'my_ride': my_ride,
        'selected_route': selected_route,
        'selected_visibility': selected_visibility,
        'selected_date': selected_date,
        'selected_time': selected_time_str,
        'date_options': date_options,
        'route_choices': RideRequest.ROUTE_CHOICES,
        'visibility_choices': RideRequest.VISIBILITY_CHOICES,
    })


# ---------------------------------------------------------------------------
# Create ride
# ---------------------------------------------------------------------------

@login_required
def create_ride(request):
    if _user_has_active_ride(request.user):
        messages.error(request, 'You already have an active ride. Leave it first.')
        return redirect('ride_list')

    if request.method == 'POST':
        form = RideRequestForm(request.POST)
        if form.is_valid():
            with transaction.atomic():
                ride = form.save(commit=False)
                ride.creator = request.user
                ride.save()
                RideParticipant.objects.create(ride=ride, user=request.user)
                ride.sync_status()
            messages.success(request, 'Ride created! Share the details with your classmates.')
            return redirect('ride_detail', ride_id=ride.id)
    else:
        form = RideRequestForm()

    return render(request, 'coordinate/create_ride.html', {'form': form})


# ---------------------------------------------------------------------------
# Join / leave / terminate
# ---------------------------------------------------------------------------

@login_required
@require_POST
def join_ride(request, ride_id):
    with transaction.atomic():
        ride = get_object_or_404(
            RideRequest.objects.select_for_update(),
            id=ride_id,
        )
        if not _user_can_join_ride(request.user, ride):
            messages.error(request, 'You cannot join this ride.')
            if request.htmx:
                return HttpResponse(status=204)
            return redirect('ride_list')

        try:
            RideParticipant.objects.create(ride=ride, user=request.user)
            ride.sync_status()
        except IntegrityError:
            pass  # Already a participant — harmless race condition

    if request.htmx:
        # Return the updated action buttons partial
        ride.refresh_from_db()
        return render(request, 'coordinate/partials/ride_actions.html', {
            'ride': ride,
            'joined': True,
            'has_active_ride': True,
        })

    return redirect('ride_list')


@login_required
@require_POST
def leave_ride(request, ride_id):
    with transaction.atomic():
        ride = get_object_or_404(
            RideRequest.objects.select_for_update(),
            id=ride_id,
        )
        RideParticipant.objects.filter(ride=ride, user=request.user).delete()

        remaining = RideParticipant.objects.filter(ride=ride).count()
        if remaining == 0:
            ride.delete()
            if request.htmx:
                return HttpResponse(status=204)
            return redirect('ride_list')

        ride.sync_status()

    if request.htmx:
        ride.refresh_from_db()
        return render(request, 'coordinate/partials/ride_actions.html', {
            'ride': ride,
            'joined': False,
            'has_active_ride': _user_has_active_ride(request.user),
        })

    return redirect('ride_list')


@login_required
@require_POST
def terminate_ride(request, ride_id):
    """Creator can delete their own ride entirely."""
    ride = get_object_or_404(RideRequest, id=ride_id, creator=request.user)
    ride.delete()
    messages.success(request, 'Ride terminated.')
    return redirect('ride_list')


# ---------------------------------------------------------------------------
# Ride detail
# ---------------------------------------------------------------------------

@login_required
def ride_detail(request, ride_id):
    ride = get_object_or_404(
        RideRequest.objects.select_related('creator'),
        id=ride_id,
    )

    # Only creator and participants can access the detail page
    is_creator = ride.creator == request.user
    is_participant = RideParticipant.objects.filter(ride=ride, user=request.user).exists()

    if not (is_creator or is_participant):
        raise Http404

    participants = (
        RideParticipant.objects
        .filter(ride=ride)
        .select_related('user')
        .order_by('joined_at')
    )

    chat_messages = (
        RideMessage.objects
        .filter(ride=ride)
        .select_related('author')
        .order_by('created_at')
    )

    can_message = (
        is_participant
        and ride.status != 'COMPLETED'
        and ride.departure_time > timezone.now()
    )

    # Which participants the current user can still review
    reviewable_user_ids = set()
    if ride.status == 'COMPLETED' and is_participant:
        already_reviewed = set(
            RideReview.objects
            .filter(ride=ride, reviewer=request.user)
            .values_list('reviewed_user_id', flat=True)
        )
        reviewable_user_ids = {
            p.user_id for p in participants
            if p.user != request.user and p.user_id not in already_reviewed
        }

    return render(request, 'coordinate/ride_detail.html', {
        'ride': ride,
        'is_creator': is_creator,
        'is_participant': is_participant,
        'participants': participants,
        'chat_messages': chat_messages,
        'message_form': RideMessageForm(),
        'can_message': can_message,
        'reviewable_user_ids': reviewable_user_ids,
    })


# ---------------------------------------------------------------------------
# Kick / complete
# ---------------------------------------------------------------------------

@login_required
@require_POST
def kick_participant(request, ride_id, participant_id):
    with transaction.atomic():
        ride = get_object_or_404(
            RideRequest.objects.select_for_update(),
            id=ride_id,
            creator=request.user,
        )
        participant = get_object_or_404(RideParticipant, id=participant_id, ride=ride)

        if participant.user == request.user:
            messages.error(request, "You can't kick yourself. Use 'Leave Ride' instead.")
            return redirect('ride_detail', ride_id=ride.id)

        participant.delete()
        ride.sync_status()

    messages.success(request, f'{participant.user} has been removed from the ride.')
    return redirect('ride_detail', ride_id=ride.id)


@login_required
@require_POST
def complete_ride(request, ride_id):
    ride = get_object_or_404(RideRequest, id=ride_id, creator=request.user)

    if ride.status == 'COMPLETED':
        return redirect('ride_detail', ride_id=ride.id)

    with transaction.atomic():
        ride.status = 'COMPLETED'
        ride.save(update_fields=['status'])

        # Increment rides_completed for every participant
        participant_users = (
            RideParticipant.objects
            .filter(ride=ride)
            .select_related('user')
        )
        for rp in participant_users:
            rp.user.rides_completed += 1
            rp.user.save(update_fields=['rides_completed'])

    messages.success(request, 'Ride marked as completed. You can now review your fellow passengers.')
    return redirect('ride_detail', ride_id=ride.id)


# ---------------------------------------------------------------------------
# Review
# ---------------------------------------------------------------------------

@login_required
def review_user(request, ride_id, user_id):
    ride = get_object_or_404(RideRequest, id=ride_id, status='COMPLETED')
    reviewed_user = get_object_or_404(User, id=user_id)

    # Gate checks
    reviewer_was_there = RideParticipant.objects.filter(ride=ride, user=request.user).exists()
    reviewed_was_there = RideParticipant.objects.filter(ride=ride, user=reviewed_user).exists()

    if not reviewer_was_there or not reviewed_was_there or reviewed_user == request.user:
        return HttpResponseForbidden('You cannot review this participant.')

    already_reviewed = RideReview.objects.filter(
        ride=ride, reviewer=request.user, reviewed_user=reviewed_user
    ).exists()
    if already_reviewed:
        messages.info(request, 'You have already reviewed this participant.')
        return redirect('ride_detail', ride_id=ride.id)

    if request.method == 'POST':
        form = RideReviewForm(request.POST)
        if form.is_valid():
            review = form.save(commit=False)
            review.ride = ride
            review.reviewer = request.user
            review.reviewed_user = reviewed_user
            review.save()

            if review.complaint.strip():
                reviewed_user.behavior_reports += 1
                reviewed_user.save(update_fields=['behavior_reports'])

            messages.success(request, 'Review submitted.')
            return redirect('ride_detail', ride_id=ride.id)
    else:
        form = RideReviewForm()

    return render(request, 'coordinate/review_user.html', {
        'form': form,
        'ride': ride,
        'reviewed_user': reviewed_user,
    })


# ---------------------------------------------------------------------------
# Message (HTTP fallback — real-time is via WebSocket)
# ---------------------------------------------------------------------------

@login_required
@require_POST
def send_message(request, ride_id):
    ride = get_object_or_404(RideRequest, id=ride_id)

    is_participant = RideParticipant.objects.filter(ride=ride, user=request.user).exists()
    if not is_participant or ride.status == 'COMPLETED' or ride.departure_time <= timezone.now():
        return HttpResponseForbidden('You cannot send messages for this ride.')

    form = RideMessageForm(request.POST)
    if form.is_valid():
        msg = form.save(commit=False)
        msg.ride = ride
        msg.author = request.user
        msg.save()
    else:
        messages.error(request, 'Message could not be sent.')

    return redirect('ride_detail', ride_id=ride.id)


# Import needed for review_user
from .models import RideReview  # noqa: E402
