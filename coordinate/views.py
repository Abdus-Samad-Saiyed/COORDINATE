"""Views for the coordinate (ride coordination) app.

URL summary:
  /coordinate/                            → ride_list
  /coordinate/my-rides/                   → my_rides (history and active rides)
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
from django.db.models import Count, F, Prefetch, Q
from django.http import Http404, HttpResponse, HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer

from accounts.models import Friendship, User

from .forms import RideMessageForm, RideRequestForm, RideReviewForm
from .models import (
    RideIncidentReport,
    RideJoinRequest,
    RideMessage,
    RideParticipant,
    RideRequest,
    RideReview,
    RideWaitlist,
)


# ---------------------------------------------------------------------------
# Access helpers
# ---------------------------------------------------------------------------

def _user_has_active_ride(user) -> bool:
    """True if the user is a participant in any non-expired OPEN or FULL ride."""
    threshold = timezone.now() - datetime.timedelta(hours=2)
    return RideParticipant.objects.filter(
        user=user,
        ride__status__in=['OPEN', 'FULL'],
        ride__departure_time__gt=threshold,
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
    All conditions that must be satisfied to join / request to join:
      1. Ride is OPEN
      2. Departure is in the future
      3. User can see the ride (visibility check)
      4. User is not already a participant
      5. User doesn't have another active ride
      6. User was not kicked from this ride
      7. User does not already have a pending join request
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
    if ride.kicked_users.filter(id=user.id).exists():
        return False
    if RideJoinRequest.objects.filter(ride=ride, user=user, status='PENDING').exists():
        return False
    return True


def _user_can_waitlist(user, ride) -> bool:
    """
    Conditions to join standby waitlist:
      1. User is authenticated
      2. Ride is FULL (or all spots filled)
      3. Departure is in future
      4. User can see the ride
      5. User is not creator and not already a participant
      6. User is not already on waitlist
      7. User doesn't have another active ride
      8. User was not kicked
    """
    if not user or not user.is_authenticated:
        return False
    if ride.status not in ['FULL', 'OPEN'] or not ride.is_full():
        return False
    if ride.departure_time <= timezone.now():
        return False
    if not _user_can_see_ride(user, ride):
        return False
    if ride.creator_id == user.pk:
        return False
    if RideParticipant.objects.filter(ride=ride, user=user).exists():
        return False
    if RideWaitlist.objects.filter(ride=ride, user=user).exists():
        return False
    if _user_has_active_ride(user):
        return False
    if ride.kicked_users.filter(id=user.id).exists():
        return False
    return True


def _broadcast_ride_teardown(ride, action: str):
    """Notify all connected WebSocket clients that ride has concluded, closing connections."""
    try:
        channel_layer = get_channel_layer()
        if channel_layer:
            async_to_sync(channel_layer.group_send)(
                f'ride_{ride.id}',
                {
                    'type': 'system.notice',
                    'action': action,
                    'content': f"This ride was marked {action}. Chat session ended.",
                }
            )
    except Exception:
        pass


def _promote_next_waitlist_passenger(ride):
    """
    If ride has an open spot and waitlist is non-empty,
    promotes earliest waitlisted student to RideParticipant atomically.
    """
    if ride.status in ['COMPLETED', 'CANCELLED']:
        return None

    if ride.participant_count() < ride.total_spots:
        with transaction.atomic():
            next_entry = (
                RideWaitlist.objects
                .select_for_update()
                .filter(ride=ride)
                .order_by('joined_at')
                .first()
            )
            if next_entry:
                promoted_user = next_entry.user
                next_entry.delete()
                RideParticipant.objects.get_or_create(
                    ride=ride,
                    user=promoted_user,
                )
                ride.sync_status()

                # Post system chat announcement
                RideMessage.objects.create(
                    ride=ride,
                    author=promoted_user,
                    content=f"🔔 Standby Promotion: {promoted_user.enrollment_number} was automatically moved from standby to confirmed passenger."
                )

                try:
                    channel_layer = get_channel_layer()
                    if channel_layer:
                        async_to_sync(channel_layer.group_send)(
                            f'ride_{ride.id}',
                            {
                                'type': 'system.notice',
                                'action': 'waitlist_promoted',
                                'user': promoted_user.enrollment_number,
                                'content': f"🔔 Standby Promotion: {promoted_user.enrollment_number} joined the ride from standby.",
                            }
                        )
                except Exception:
                    pass

                return promoted_user
    return None


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
# Ride list & My Rides
# ---------------------------------------------------------------------------

@login_required
def ride_list(request):
    """Browse open rides with optional date-time range, ordering, queue filters, and date density."""
    selected_route = request.GET.get('route', '')
    selected_visibility = request.GET.get('visibility', '')
    order_by_param = request.GET.get('order_by', 'time_asc')
    queue_only = request.GET.get('queue_only', '')

    # Date-time range parameters (with backward-compatible fallbacks)
    date_from_str = request.GET.get('date_from', '') or request.GET.get('date', '')
    date_to_str = request.GET.get('date_to', '')
    time_from_str = request.GET.get('time_from', '') or request.GET.get('time', '')
    time_to_str = request.GET.get('time_to', '')

    today = timezone.now().date()
    chosen_date = _parse_date(date_from_str)
    date_to = _parse_date(date_to_str)
    time_from = _parse_time(time_from_str)
    time_to = _parse_time(time_to_str)

    current_tz = timezone.get_current_timezone()

    # Determine date range boundaries
    has_date_filter = bool(chosen_date or date_to or time_from or time_to)
    is_custom_range = bool(chosen_date and date_to and date_to != chosen_date)

    if chosen_date and date_to:
        if date_to < chosen_date:
            date_to = chosen_date
        start_date = chosen_date
        end_date = date_to
    elif chosen_date:
        start_date = chosen_date
        end_date = chosen_date
    elif date_to:
        start_date = today
        end_date = date_to
    else:
        start_date = today
        end_date = None

    start_time_val = time_from or datetime.time(0, 0, 0)
    end_time_val = time_to or datetime.time(23, 59, 59)

    # Base queryset: open and full rides
    rides_qs = (
        RideRequest.objects
        .filter(status__in=['OPEN', 'FULL'])
        .select_related('creator')
        .annotate(participants_total=Count('participants'))
    )

    if has_date_filter:
        start_dt = timezone.make_aware(datetime.datetime.combine(start_date, start_time_val), current_tz)
        rides_qs = rides_qs.filter(departure_time__gte=start_dt)
        if end_date:
            end_dt = timezone.make_aware(datetime.datetime.combine(end_date, end_time_val), current_tz)
            rides_qs = rides_qs.filter(departure_time__lte=end_dt)
    else:
        # Default: all future rides, un-clamped by default
        rides_qs = rides_qs.filter(departure_time__gte=timezone.now())

    if selected_route:
        rides_qs = rides_qs.filter(route=selected_route)
    if selected_visibility:
        rides_qs = rides_qs.filter(visibility=selected_visibility)
    if queue_only in ['1', 'true', 'True']:
        rides_qs = rides_qs.filter(status='FULL')

    # Ordering
    if order_by_param == 'time_desc':
        rides_qs = rides_qs.order_by('-departure_time', '-participants_total')
    elif order_by_param == 'spots_desc':
        rides_qs = rides_qs.order_by('-total_spots', 'departure_time')
    elif order_by_param == 'created_desc':
        rides_qs = rides_qs.order_by('-created_at')
    elif order_by_param == 'rating_desc':
        rides_qs = rides_qs.order_by('-creator__on_time_count', 'departure_time')
    else:  # time_asc default
        rides_qs = rides_qs.order_by('departure_time', '-participants_total')

    # Filter visibility per user
    visible_rides = [r for r in rides_qs if _user_can_see_ride(request.user, r)]

    # Attach spots remaining and join eligibility
    user_pending_request_ride_ids = set(
        RideJoinRequest.objects.filter(
            user=request.user,
            status='PENDING',
        ).values_list('ride_id', flat=True)
    )

    for ride in visible_rides:
        ride.spots_left = max(0, ride.total_spots - ride.participants_total)
        ride.has_pending_request = ride.id in user_pending_request_ride_ids
        ride.can_join = _user_can_join_ride(request.user, ride)
        ride.is_participant = RideParticipant.objects.filter(
            ride=ride, user=request.user
        ).exists()
        ride.is_waitlisted = RideWaitlist.objects.filter(
            ride=ride, user=request.user
        ).exists()
        ride.can_waitlist = _user_can_waitlist(request.user, ride)
        ride.waitlist_count = ride.waitlist_entries.count()
        ride.pending_request_count = ride.join_requests.filter(status='PENDING').count() if ride.creator_id == request.user.id else 0

    # Density calculation across next 14 days
    density_raw = (
        RideRequest.objects
        .filter(
            status__in=['OPEN', 'FULL'],
            departure_time__gte=timezone.now(),
            departure_time__lte=timezone.now() + datetime.timedelta(days=14),
        )
        .values('departure_time')
    )
    counts_by_date = {}
    for r in density_raw:
        dt = r['departure_time']
        if timezone.is_aware(dt):
            dt = timezone.localtime(dt)
        d_key = dt.date()
        counts_by_date[d_key] = counts_by_date.get(d_key, 0) + 1

    max_density = max(counts_by_date.values()) if counts_by_date else 1
    density_data = []
    for i in range(14):
        d = today + datetime.timedelta(days=i)
        c = counts_by_date.get(d, 0)
        pct = max(10, int((c / max(1, max_density)) * 100)) if c > 0 else 6
        density_data.append({
            'date': d,
            'date_str': d.strftime('%Y-%m-%d'),
            'day_name': d.strftime('%a'),
            'day_num': d.strftime('%d'),
            'count': c,
            'height_pct': pct,
            'is_today': d == today,
            'is_selected': (chosen_date == d) if chosen_date else False,
        })

    # User's active ride
    has_active_ride = _user_has_active_ride(request.user)
    my_ride = None
    if has_active_ride:
        my_ride_part = (
            RideParticipant.objects
            .filter(user=request.user, ride__status__in=['OPEN', 'FULL'])
            .select_related('ride', 'ride__creator')
            .first()
        )
        if my_ride_part:
            my_ride = my_ride_part.ride

    # Quick-select date strip: dynamically moving window centered around chosen_date
    ref_date = chosen_date or today
    if ref_date < today:
        ref_date = today

    if ref_date > today:
        window_start = max(today, ref_date - datetime.timedelta(days=2))
    else:
        window_start = today

    date_options = []
    for i in range(7):
        d = window_start + datetime.timedelta(days=i)
        date_options.append({
            'date': d,
            'date_str': d.strftime('%Y-%m-%d'),
            'label': d.strftime('%a, %b %d'),
            'day_name': d.strftime('%a'),
            'day_num': d.strftime('%d'),
            'is_selected': d == ref_date and has_date_filter,
            'is_today': d == today,
        })

    prev_date = (ref_date - datetime.timedelta(days=1)) if ref_date > today else None
    next_date = ref_date + datetime.timedelta(days=1)

    return render(request, 'coordinate/ride_list.html', {
        'rides': visible_rides,
        'has_active_ride': has_active_ride,
        'my_ride': my_ride,
        'selected_route': selected_route,
        'selected_visibility': selected_visibility,
        'selected_date': chosen_date,
        'date_from': date_from_str,
        'date_to': date_to_str,
        'time_from': time_from_str,
        'time_to': time_to_str,
        'has_date_filter': has_date_filter,
        'is_custom_range': is_custom_range,
        'order_by': order_by_param,
        'queue_only': queue_only in ['1', 'true', 'True'],
        'density_data': density_data,
        'max_density': max_density,
        'date_options': date_options,
        'prev_date': prev_date.strftime('%Y-%m-%d') if prev_date else None,
        'next_date': next_date.strftime('%Y-%m-%d'),
        'route_choices': RideRequest.ROUTE_CHOICES,
        'visibility_choices': RideRequest.VISIBILITY_CHOICES,
    })


@login_required
def my_rides(request):
    """RIDE-03: Dedicated Ride History and active participations interface."""
    participations = (
        RideParticipant.objects
        .filter(user=request.user)
        .select_related('ride', 'ride__creator')
        .prefetch_related('ride__participants')
        .order_by('-ride__departure_time')
    )

    active_rides = []
    past_rides = []

    for p in participations:
        ride = p.ride
        if ride.status in ['OPEN', 'FULL'] and ride.departure_time > timezone.now() - datetime.timedelta(hours=2):
            active_rides.append(ride)
        else:
            past_rides.append(ride)

    created_rides = (
        RideRequest.objects
        .filter(creator=request.user)
        .order_by('-departure_time')
    )

    return render(request, 'coordinate/my_rides.html', {
        'active_rides': active_rides,
        'past_rides': past_rides,
        'created_rides': created_rides,
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
            visibility = form.cleaned_data.get('visibility')

            # SEC-03: Gender-restricted creator validation
            if visibility == 'GIRLS' and request.user.gender != 'F':
                form.add_error('visibility', 'Only female students can create Girls Only rides.')
                return render(request, 'coordinate/create_ride.html', {'form': form})
            if visibility == 'BOYS' and request.user.gender != 'M':
                form.add_error('visibility', 'Only male students can create Boys Only rides.')
                return render(request, 'coordinate/create_ride.html', {'form': form})

            with transaction.atomic():
                ride = form.save(commit=False)
                ride.creator = request.user
                ride.save()
                RideParticipant.objects.create(ride=ride, user=request.user)
                ride.sync_status()

            messages.success(request, 'Ride created! Share the details with your classmates.')
            return redirect('ride_list')
    else:
        form = RideRequestForm()

    return render(request, 'coordinate/create_ride.html', {'form': form})


# ---------------------------------------------------------------------------
# Join / leave / terminate
# ---------------------------------------------------------------------------

@login_required
@require_POST
def join_ride(request, ride_id):
    """
    RIDE-JOIN-REQ: Students submit a join request that requires host approval.
    """
    with transaction.atomic():
        ride = get_object_or_404(
            RideRequest.objects.select_for_update(),
            id=ride_id,
        )
        if not _user_can_join_ride(request.user, ride):
            messages.error(request, 'You cannot request to join this ride.')
            if request.htmx:
                return HttpResponse(status=204)
            return redirect('ride_list')

        join_req, created = RideJoinRequest.objects.get_or_create(
            ride=ride,
            user=request.user,
            status='PENDING',
        )
        if created:
            messages.success(request, f'Join request submitted to host {ride.creator.enrollment_number}! Awaiting host approval.')
            try:
                channel_layer = get_channel_layer()
                if channel_layer:
                    async_to_sync(channel_layer.group_send)(
                        f'ride_{ride.id}',
                        {
                            'type': 'system.notice',
                            'action': 'join_request',
                            'content': f"🔔 {request.user.enrollment_number} submitted a request to join the ride.",
                        }
                    )
            except Exception:
                pass
        else:
            messages.info(request, 'You already have a pending join request for this ride.')

    if request.htmx:
        return HttpResponse(status=204)

    return redirect('ride_list')


@login_required
@require_POST
def approve_join_request(request, ride_id, request_id):
    """Host approves a pending join request, atomically adding the participant."""
    with transaction.atomic():
        ride = get_object_or_404(
            RideRequest.objects.select_for_update(),
            id=ride_id,
            creator=request.user,
        )
        join_req = get_object_or_404(
            RideJoinRequest.objects.select_for_update(),
            id=request_id,
            ride=ride,
            status='PENDING',
        )

        if ride.is_full():
            messages.error(request, 'Cannot approve request: ride is already full.')
            return redirect('ride_detail', ride_id=ride.id)

        if _user_has_active_ride(join_req.user):
            messages.warning(request, f'{join_req.user.enrollment_number} already joined another active ride.')
            join_req.status = 'DECLINED'
            join_req.reviewed_at = timezone.now()
            join_req.save(update_fields=['status', 'reviewed_at'])
            return redirect('ride_detail', ride_id=ride.id)

        RideParticipant.objects.get_or_create(ride=ride, user=join_req.user)
        join_req.status = 'APPROVED'
        join_req.reviewed_at = timezone.now()
        join_req.save(update_fields=['status', 'reviewed_at'])

        # Remove from waitlist if present
        RideWaitlist.objects.filter(ride=ride, user=join_req.user).delete()

        ride.sync_status()

        try:
            channel_layer = get_channel_layer()
            if channel_layer:
                async_to_sync(channel_layer.group_send)(
                    f'ride_{ride.id}',
                    {
                        'type': 'system.notice',
                        'action': 'approved',
                        'content': f"🎉 Host approved {join_req.user.enrollment_number} to join the ride!",
                    }
                )
        except Exception:
            pass

    messages.success(request, f'Approved {join_req.user.enrollment_number} to join.')
    return redirect('ride_detail', ride_id=ride.id)


@login_required
@require_POST
def decline_join_request(request, ride_id, request_id):
    """Host declines a pending join request."""
    ride = get_object_or_404(RideRequest, id=ride_id, creator=request.user)
    join_req = get_object_or_404(RideJoinRequest, id=request_id, ride=ride, status='PENDING')

    join_req.status = 'DECLINED'
    join_req.reviewed_at = timezone.now()
    join_req.save(update_fields=['status', 'reviewed_at'])

    messages.info(request, f'Declined request from {join_req.user.enrollment_number}.')
    return redirect('ride_detail', ride_id=ride.id)


@login_required
@require_POST
def cancel_join_request(request, ride_id):
    """Student cancels their own pending join request."""
    ride = get_object_or_404(RideRequest, id=ride_id)
    deleted, _ = RideJoinRequest.objects.filter(ride=ride, user=request.user, status='PENDING').delete()
    if deleted:
        messages.info(request, 'Your join request was cancelled.')
    return redirect('ride_list')


@login_required
@require_POST
def leave_ride(request, ride_id):
    with transaction.atomic():
        ride = get_object_or_404(
            RideRequest.objects.select_for_update(),
            id=ride_id,
        )
        if ride.status in ['COMPLETED', 'CANCELLED']:
            messages.error(request, 'Cannot leave a completed or cancelled ride.')
            return redirect('ride_detail', ride_id=ride.id)

        RideParticipant.objects.filter(ride=ride, user=request.user).delete()
        ride.left_users.add(request.user)

        remaining = RideParticipant.objects.filter(ride=ride).count()
        if remaining == 0:
            # Preserve ride if it has chat history or completed; otherwise clean up
            if ride.messages.exists() or ride.status == 'COMPLETED':
                ride.status = 'CANCELLED'
                ride.save(update_fields=['status'])
                _broadcast_ride_teardown(ride, 'cancelled')
            else:
                _broadcast_ride_teardown(ride, 'cancelled')
                ride.delete()

            if request.htmx:
                return HttpResponse(status=204)
            return redirect('ride_list')

        ride.sync_status()
        _promote_next_waitlist_passenger(ride)

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
    """Creator terminates their own ride. Cancels rather than deletes if history exists."""
    ride = get_object_or_404(RideRequest, id=ride_id, creator=request.user)

    if ride.status == 'COMPLETED':
        messages.error(request, 'Completed rides cannot be terminated.')
        return redirect('ride_detail', ride_id=ride.id)

    if ride.messages.exists():
        ride.status = 'CANCELLED'
        ride.save(update_fields=['status'])
        _broadcast_ride_teardown(ride, 'cancelled')
        messages.info(request, 'Ride cancelled.')
    else:
        _broadcast_ride_teardown(ride, 'cancelled')
        ride.delete()
        messages.success(request, 'Ride terminated.')

    return redirect('ride_list')


@login_required
@require_POST
def reschedule_ride(request, ride_id):
    """Host reschedules ride departure time without cancelling it."""
    ride = get_object_or_404(RideRequest, id=ride_id, creator=request.user)

    if ride.status in ['COMPLETED', 'CANCELLED']:
        messages.error(request, 'Completed or cancelled rides cannot be rescheduled.')
        return redirect('ride_detail', ride_id=ride.id)

    new_time_raw = request.POST.get('departure_time')
    if not new_time_raw:
        messages.error(request, 'Please provide a new departure date and time.')
        return redirect('ride_detail', ride_id=ride.id)

    try:
        new_dep_time = datetime.datetime.fromisoformat(new_time_raw)
        if timezone.is_naive(new_dep_time):
            new_dep_time = timezone.make_aware(new_dep_time, timezone.get_current_timezone())
    except (ValueError, TypeError):
        messages.error(request, 'Invalid date/time format.')
        return redirect('ride_detail', ride_id=ride.id)

    now = timezone.now()
    if new_dep_time <= now:
        messages.error(request, 'Departure time must be in the future.')
        return redirect('ride_detail', ride_id=ride.id)

    if new_dep_time > now + datetime.timedelta(days=30):
        messages.error(request, 'Cannot schedule more than 30 days in advance.')
        return redirect('ride_detail', ride_id=ride.id)

    ride.departure_time = new_dep_time
    ride.save(update_fields=['departure_time'])

    formatted_time = new_dep_time.strftime('%b %d, %Y at %I:%M %p')

    # Record system message in chat
    RideMessage.objects.create(
        ride=ride,
        author=request.user,
        content=f"⏰ Ride Rescheduled: Host updated departure time to {formatted_time}."
    )

    try:
        channel_layer = get_channel_layer()
        if channel_layer:
            async_to_sync(channel_layer.group_send)(
                f'ride_{ride.id}',
                {
                    'type': 'system.notice',
                    'action': 'rescheduled',
                    'departure_time': formatted_time,
                    'content': f"⏰ Departure time was rescheduled to {formatted_time} by host.",
                }
            )
    except Exception:
        pass

    messages.success(request, f'Ride successfully rescheduled to {formatted_time}.')
    return redirect('ride_detail', ride_id=ride.id)


@login_required
@require_POST
def join_waitlist(request, ride_id):
    """Join the standby queue for a full ride."""
    ride = get_object_or_404(RideRequest, id=ride_id)
    if not _user_can_waitlist(request.user, ride):
        messages.error(request, 'You cannot join the standby list for this ride.')
        return redirect('ride_list')

    try:
        RideWaitlist.objects.create(ride=ride, user=request.user)
        pos = ride.waitlist_entries.count()
        messages.success(request, f'Joined standby list (Position #{pos}). You will be automatically added if a spot opens up!')
    except IntegrityError:
        messages.info(request, 'You are already on the standby list for this ride.')

    return redirect('ride_detail', ride_id=ride.id)


@login_required
@require_POST
def leave_waitlist(request, ride_id):
    """Leave the standby queue."""
    ride = get_object_or_404(RideRequest, id=ride_id)
    deleted, _ = RideWaitlist.objects.filter(ride=ride, user=request.user).delete()
    if deleted:
        messages.info(request, 'You have left the standby list.')
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

    is_creator = ride.creator == request.user
    is_participant = RideParticipant.objects.filter(ride=ride, user=request.user).exists()
    is_waitlisted = RideWaitlist.objects.filter(ride=ride, user=request.user).exists()
    has_join_request = RideJoinRequest.objects.filter(ride=ride, user=request.user, status='PENDING').exists()

    if not (is_creator or is_participant or is_waitlisted or has_join_request):
        raise Http404

    participants = (
        RideParticipant.objects
        .filter(ride=ride)
        .select_related('user')
        .order_by('joined_at')
    )

    waitlist_entries = (
        RideWaitlist.objects
        .filter(ride=ride)
        .select_related('user')
        .order_by('joined_at')
    )

    pending_join_requests = (
        ride.join_requests
        .filter(status='PENDING')
        .select_related('user')
        .order_by('created_at')
    ) if is_creator else []

    chat_messages = (
        RideMessage.objects
        .filter(ride=ride)
        .select_related('author')
        .order_by('created_at')
    )

    can_message = (
        is_participant
        and ride.status not in ['COMPLETED', 'CANCELLED']
        and ride.departure_time + datetime.timedelta(hours=2) > timezone.now()
    )

    can_waitlist = _user_can_waitlist(request.user, ride)
    can_join = _user_can_join_ride(request.user, ride)

    user_waitlist_pos = None
    if is_waitlisted:
        entry = RideWaitlist.objects.filter(ride=ride, user=request.user).first()
        if entry:
            user_waitlist_pos = RideWaitlist.objects.filter(ride=ride, joined_at__lte=entry.joined_at).count()

    reviewable_user_ids = set()
    already_reviewed = set(
        RideReview.objects
        .filter(ride=ride, reviewer=request.user)
        .values_list('reviewed_user_id', flat=True)
    )

    if ride.status == 'COMPLETED' and is_participant:
        reviewable_user_ids.update({
            p.user_id for p in participants
            if p.user != request.user and p.user_id not in already_reviewed
        })

    # Immediate reviews for kicked users or users who left early
    for u in ride.kicked_users.all():
        if (is_creator or is_participant) and u != request.user and u.id not in already_reviewed:
            reviewable_user_ids.add(u.id)
        if request.user == u and ride.creator_id not in already_reviewed:
            reviewable_user_ids.add(ride.creator_id)

    for u in ride.left_users.all():
        if (is_creator or is_participant) and u != request.user and u.id not in already_reviewed:
            reviewable_user_ids.add(u.id)
        if request.user == u and ride.creator_id not in already_reviewed:
            reviewable_user_ids.add(ride.creator_id)

    return render(request, 'coordinate/ride_detail.html', {
        'ride': ride,
        'is_creator': is_creator,
        'is_participant': is_participant,
        'is_waitlisted': is_waitlisted,
        'has_join_request': has_join_request,
        'can_waitlist': can_waitlist,
        'can_join': can_join,
        'user_waitlist_pos': user_waitlist_pos,
        'participants': participants,
        'waitlist_entries': waitlist_entries,
        'pending_join_requests': pending_join_requests,
        'chat_messages': chat_messages,
        'message_form': RideMessageForm(),
        'can_message': can_message,
        'reviewable_user_ids': reviewable_user_ids,
        'kicked_users': ride.kicked_users.all(),
        'left_users': ride.left_users.all(),
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

        # RIDE-04: Record kick so removed user cannot rejoin and can be reviewed immediately
        ride.kicked_users.add(participant.user)
        participant.delete()
        ride.sync_status()
        _promote_next_waitlist_passenger(ride)

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
        _broadcast_ride_teardown(ride, 'completed')

        # RIDE-05: Update attendance and reliability statistics
        participant_users = (
            RideParticipant.objects
            .filter(ride=ride)
            .select_related('user')
        )
        for rp in participant_users:
            rp.user.rides_completed = F('rides_completed') + 1
            rp.user.on_time_count = F('on_time_count') + 1
            rp.user.save(update_fields=['rides_completed', 'on_time_count'])

    messages.success(request, 'Ride marked as completed. You can now review your fellow passengers.')
    return redirect('ride_detail', ride_id=ride.id)


# ---------------------------------------------------------------------------
# Review
# ---------------------------------------------------------------------------

@login_required
def review_user(request, ride_id, user_id):
    ride = get_object_or_404(RideRequest, id=ride_id)
    reviewed_user = get_object_or_404(User, id=user_id)

    if reviewed_user == request.user:
        return HttpResponseForbidden('You cannot review yourself.')

    # Check eligibility:
    # 1. Standard: Ride completed and both are/were participants
    # 2. Immediate grievance: reviewed_user was kicked or left, OR reviewer was kicked/left and reviewing host
    is_kicked_or_left = (
        ride.kicked_users.filter(id=reviewed_user.id).exists()
        or ride.left_users.filter(id=reviewed_user.id).exists()
    )
    reviewer_was_kicked_or_left = (
        ride.kicked_users.filter(id=request.user.id).exists()
        or ride.left_users.filter(id=request.user.id).exists()
    )

    reviewer_was_there = (
        RideParticipant.objects.filter(ride=ride, user=request.user).exists()
        or reviewer_was_kicked_or_left
    )
    reviewed_was_there = (
        RideParticipant.objects.filter(ride=ride, user=reviewed_user).exists()
        or is_kicked_or_left
    )

    is_completed_review = (ride.status == 'COMPLETED' and reviewer_was_there and reviewed_was_there)
    is_immediate_grievance_review = (
        (is_kicked_or_left and reviewer_was_there)
        or (reviewer_was_kicked_or_left and reviewed_user == ride.creator)
    )

    if not (is_completed_review or is_immediate_grievance_review):
        return HttpResponseForbidden('You are not eligible to review this user for this ride at this time.')

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

            update_fields = []
            if review.grievance == 'LATE' or review.punctuality_rating <= 2:
                reviewed_user.late_count = F('late_count') + 1
                update_fields.append('late_count')
            elif review.grievance == 'NO_SHOW':
                reviewed_user.no_show_count = F('no_show_count') + 1
                update_fields.append('no_show_count')

            if review.grievance != 'NONE' or (review.complaint and review.complaint.strip()):
                reviewed_user.behavior_reports = F('behavior_reports') + 1
                update_fields.append('behavior_reports')

            if update_fields:
                reviewed_user.save(update_fields=update_fields)

            messages.success(request, 'Review submitted successfully.')
            return redirect('ride_detail', ride_id=ride.id)
    else:
        form = RideReviewForm()

    return render(request, 'coordinate/review_user.html', {
        'form': form,
        'ride': ride,
        'reviewed_user': reviewed_user,
        'is_immediate_grievance': is_immediate_grievance_review,
    })


# ---------------------------------------------------------------------------
# Message (HTTP fallback — real-time is via WebSocket)
# ---------------------------------------------------------------------------

@login_required
@require_POST
def send_message(request, ride_id):
    ride = get_object_or_404(RideRequest, id=ride_id)

    is_participant = RideParticipant.objects.filter(ride=ride, user=request.user).exists()
    if not is_participant or ride.status in ['COMPLETED', 'CANCELLED'] or ride.departure_time + datetime.timedelta(hours=2) <= timezone.now():
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


# ---------------------------------------------------------------------------
# Incident Escalation to Institute Proctorial Board
# ---------------------------------------------------------------------------

@login_required
@require_POST
def report_incident(request, ride_id):
    """File a formal misconduct incident report.
    
    Escalated directly to the Institute Proctorial Board / Dean of Students Welfare.
    Optionally captures the chronological in-ride chat transcript as official evidence.
    """
    import uuid
    from accounts.models import log_audit_event
    from coordinate.models import RideIncidentReport

    ride = get_object_or_404(RideRequest, id=ride_id)
    is_participant = RideParticipant.objects.filter(ride=ride, user=request.user).exists()
    if not is_participant:
        return HttpResponseForbidden("Only confirmed participants in this ride can file an incident report.")

    category = request.POST.get('category', 'OTHER').strip()
    statement = request.POST.get('statement', '').strip()
    reported_enrollment = request.POST.get('reported_user', '').strip().upper()
    include_chat = request.POST.get('include_chat_log') in ['on', 'true', '1', True]

    if not statement:
        messages.error(request, "A detailed statement describing the incident is required.")
        return redirect('ride_detail', ride_id=ride.id)

    reported_user = None
    if reported_enrollment:
        reported_user = User.objects.filter(enrollment_number=reported_enrollment).first()

    chat_transcript = ""
    if include_chat:
        messages_qs = RideMessage.objects.filter(ride=ride).select_related('author').order_by('created_at')
        lines = []
        for m in messages_qs:
            lines.append(f"[{m.created_at.strftime('%Y-%m-%d %H:%M:%S')}] {m.author.enrollment_number}: {m.content}")
        chat_transcript = "\n".join(lines) if lines else "(No chat messages in this ride session)"

    current_year = timezone.now().year
    reference_id = f"ESC-{current_year}-{uuid.uuid4().hex[:6].upper()}"

    report = RideIncidentReport.objects.create(
        reference_id=reference_id,
        ride=ride,
        reporter=request.user,
        reported_user=reported_user,
        category=category,
        statement=statement,
        include_chat_log=include_chat,
        chat_transcript=chat_transcript,
        escalated_to_institute=True,
        status='ESCALATED',
    )

    log_audit_event(
        event_type="INCIDENT_ESCALATED",
        actor_enrollment=request.user.enrollment_number,
        description=f"Incident {reference_id} filed in Ride #{ride.id} ({report.get_category_display()}) for Proctorial review",
        target_id=reference_id,
    )

    messages.warning(
        request,
        f"Formal incident report filed (Ref: {reference_id}). "
        f"Your statement {'and chat transcript ' if include_chat else ''}have been compiled for the "
        f"Institute Proctorial Board. Platform staff do not mediate disputes internally."
    )
    return redirect('ride_detail', ride_id=ride.id)

