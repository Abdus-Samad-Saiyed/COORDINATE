from datetime import datetime, time, timedelta

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import IntegrityError, transaction
from django.db.models import Count
from django.http import Http404, HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from accounts.models import Friendship, User

from .forms import RideMessageForm, RideRequestForm, RideReviewForm
from .models import RideMessage, RideParticipant, RideRequest, RideReview


def user_has_active_ride(user):

    return RideParticipant.objects.filter(
        user=user,
        ride__status__in=['OPEN', 'FULL']
    ).exists()


def are_friends(user1, user2):

    return Friendship.objects.filter(
        user1=user1,
        user2=user2
    ).exists() or Friendship.objects.filter(
        user1=user2,
        user2=user1
    ).exists()


def user_can_see_ride(user, ride):

    if ride.creator_id == user.id:

        return True

    if RideParticipant.objects.filter(
        ride=ride,
        user=user
    ).exists():

        return True

    if ride.visibility == 'MIXED':

        return True

    if ride.visibility == 'BOYS':

        return user.gender == 'M'

    if ride.visibility == 'GIRLS':

        return user.gender == 'F'

    if ride.visibility == 'FRIENDS':

        return are_friends(user, ride.creator)

    return False


def user_can_join_ride(user, ride):

    return (
        ride.status == 'OPEN' and
        ride.departure_time > timezone.now() and
        user_can_see_ride(user, ride) and
        not RideParticipant.objects.filter(
            ride=ride,
            user=user
        ).exists() and
        not user_has_active_ride(user)
    )


def user_can_access_private_ride(user, ride):

    return (
        ride.creator_id == user.id or
        RideParticipant.objects.filter(
            ride=ride,
            user=user
        ).exists()
    )


def parse_date(value):

    if not value:

        return None

    try:

        return datetime.strptime(value, '%Y-%m-%d').date()

    except ValueError:

        return None


def parse_time(value):

    if not value:

        return None

    try:

        return datetime.strptime(value, '%H:%M').time()

    except ValueError:

        return None


@login_required
def ride_list(request):

    selected_route = request.GET.get('route', '')
    selected_visibility = request.GET.get('visibility', '')
    selected_date = request.GET.get('date', '')
    selected_time = request.GET.get('time', '')

    now = timezone.localtime()
    filter_date = parse_date(selected_date)
    filter_time = parse_time(selected_time)

    rides = (
        RideRequest.objects
        .filter(
            status='OPEN',
            departure_time__gt=timezone.now()
        )
        .select_related('creator')
        .annotate(participants_total=Count('rideparticipant'))
    )

    valid_routes = {
        value for value, _label in RideRequest.ROUTE_CHOICES
    }

    valid_visibilities = {
        value for value, _label in RideRequest.VISIBILITY_CHOICES
    }

    if selected_route in valid_routes:

        rides = rides.filter(route=selected_route)

    else:

        selected_route = ''

    if selected_visibility in valid_visibilities:

        rides = rides.filter(visibility=selected_visibility)

    else:

        selected_visibility = ''

    if filter_date:

        start = timezone.make_aware(
            datetime.combine(filter_date, time.min)
        )

        end = start + timedelta(days=1)

        rides = rides.filter(
            departure_time__gte=start,
            departure_time__lt=end
        )

    else:

        selected_date = ''

    if filter_time:

        rides = rides.filter(
            departure_time__time__gte=filter_time
        )

    else:

        selected_time = ''

    filtered_rides = [
        ride for ride in rides
        if user_can_see_ride(request.user, ride)
    ]

    filtered_rides.sort(
        key=lambda ride: (
            -ride.participants_total,
            ride.departure_time
        )
    )

    joined_rides = RideParticipant.objects.filter(
        user=request.user
    ).values_list(
        'ride_id',
        flat=True
    )

    anchor_date = filter_date or now.date()

    date_options = [
        anchor_date + timedelta(days=i)
        for i in range(-3, 4)
    ]

    my_ride = RideRequest.objects.filter(
        rideparticipant__user=request.user,
        status__in=['OPEN', 'FULL']
    ).first()

    return render(
        request,
        'coordinate/ride_list.html',
        {
            'rides': filtered_rides,
            'joined_rides': joined_rides,
            'has_active_ride':
                user_has_active_ride(request.user),
            'route_choices':
                RideRequest.ROUTE_CHOICES,
            'selected_route':
                selected_route,
            'selected_visibility':
                selected_visibility,
            'selected_date':
                selected_date,
            'selected_time':
                selected_time,
            'date_options':
                date_options,
            'my_ride':
                my_ride,
        }
    )


@login_required
def create_ride(request):

    if user_has_active_ride(request.user):

        return redirect('ride_list')

    if request.method == 'POST':

        form = RideRequestForm(request.POST)

        if form.is_valid():

            with transaction.atomic():

                ride = form.save(commit=False)
                ride.creator = request.user
                ride.save()

                RideParticipant.objects.create(
                    ride=ride,
                    user=request.user
                )

                ride.sync_status()

            return redirect('ride_list')

    else:

        form = RideRequestForm()

    return render(
        request,
        'coordinate/create_ride.html',
        {
            'form': form
        }
    )


@login_required
@require_POST
def join_ride(request, ride_id):

    with transaction.atomic():

        ride = get_object_or_404(
            RideRequest.objects.select_for_update(),
            id=ride_id
        )

        if not user_can_join_ride(request.user, ride):

            return redirect('ride_list')

        try:

            RideParticipant.objects.create(
                ride=ride,
                user=request.user
            )

        except IntegrityError:

            return redirect('ride_list')

        ride.sync_status()

    return redirect('ride_list')


@login_required
@require_POST
def leave_ride(request, ride_id):

    with transaction.atomic():

        ride = get_object_or_404(
            RideRequest.objects.select_for_update(),
            id=ride_id
        )

        RideParticipant.objects.filter(
            ride=ride,
            user=request.user
        ).delete()

        if ride.participant_count() == 0:

            ride.delete()

        else:

            ride.sync_status()

    return redirect('ride_list')


@login_required
@require_POST
def terminate_ride(request, ride_id):

    ride = get_object_or_404(
        RideRequest,
        id=ride_id,
        creator=request.user
    )

    ride.delete()

    return redirect('ride_list')


@login_required
def ride_detail(request, ride_id):

    ride = get_object_or_404(
        RideRequest.objects.select_related('creator'),
        id=ride_id
    )

    if not user_can_access_private_ride(request.user, ride):

        raise Http404

    participants = RideParticipant.objects.filter(
        ride=ride
    ).select_related('user')

    is_creator = (
        ride.creator == request.user
    )

    can_message = (
        RideParticipant.objects.filter(
            ride=ride,
            user=request.user
        ).exists() and
        ride.status != 'COMPLETED' and
        ride.departure_time > timezone.now()
    )

    message_form = RideMessageForm()

    messages_qs = RideMessage.objects.filter(
        ride=ride
    ).select_related('author').order_by('created_at')

    return render(
        request,
        'coordinate/ride_detail.html',
        {
            'ride': ride,
            'participants': participants,
            'is_creator': is_creator,
            'messages': messages_qs,
            'message_form': message_form,
            'can_message': can_message,
        }
    )


@login_required
@require_POST
def kick_participant(request, ride_id, participant_id):

    with transaction.atomic():

        ride = get_object_or_404(
            RideRequest.objects.select_for_update(),
            id=ride_id,
            creator=request.user
        )

        participant = get_object_or_404(
            RideParticipant,
            id=participant_id,
            ride=ride
        )

        if participant.user != request.user:

            participant.delete()
            ride.sync_status()

    return redirect(
        'ride_detail',
        ride_id=ride.id
    )


@login_required
@require_POST
def complete_ride(request, ride_id):

    ride = get_object_or_404(
        RideRequest,
        id=ride_id,
        creator=request.user
    )

    if ride.status != 'COMPLETED':

        ride.status = 'COMPLETED'
        ride.save(update_fields=['status'])

        for participant in RideParticipant.objects.filter(ride=ride):

            participant.user.rides_completed += 1
            participant.user.save(update_fields=['rides_completed'])

    return redirect(
        'ride_detail',
        ride_id=ride.id
    )


@login_required
def review_user(request, ride_id, user_id):

    ride = get_object_or_404(RideRequest, id=ride_id)
    reviewed_user = get_object_or_404(User, id=user_id)

    reviewer_participated = RideParticipant.objects.filter(
        ride=ride,
        user=request.user
    ).exists()

    reviewed_participated = RideParticipant.objects.filter(
        ride=ride,
        user=reviewed_user
    ).exists()

    if (
        ride.status != 'COMPLETED' or
        not reviewer_participated or
        not reviewed_participated or
        reviewed_user == request.user
    ):

        return HttpResponseForbidden(
            'You cannot review this participant.'
        )

    if request.method == 'POST':

        form = RideReviewForm(request.POST)

        if RideReview.objects.filter(
            ride=ride,
            reviewer=request.user,
            reviewed_user=reviewed_user
        ).exists():

            form.add_error(
                None,
                'You have already reviewed this participant for this ride.'
            )

            return render(
                request,
                'coordinate/review_user.html',
                {
                    'form': form,
                    'ride': ride,
                    'reviewed_user': reviewed_user,
                }
            )

        if form.is_valid():

            review = form.save(commit=False)
            review.ride = ride
            review.reviewer = request.user
            review.reviewed_user = reviewed_user
            review.save()

            if review.complaint.strip():

                reviewed_user.behavior_reports += 1
                reviewed_user.save(update_fields=['behavior_reports'])

            return redirect(
                'ride_detail',
                ride_id=ride.id
            )

    else:

        form = RideReviewForm()

    return render(
        request,
        'coordinate/review_user.html',
        {
            'form': form,
            'ride': ride,
            'reviewed_user': reviewed_user,
        }
    )


@login_required
@require_POST
def send_message(request, ride_id):

    ride = get_object_or_404(RideRequest, id=ride_id)

    is_participant = RideParticipant.objects.filter(
        ride=ride,
        user=request.user
    ).exists()

    if (
        not is_participant or
        ride.status == 'COMPLETED' or
        ride.departure_time <= timezone.now()
    ):

        return HttpResponseForbidden(
            'You cannot send messages for this ride.'
        )

    form = RideMessageForm(request.POST)

    if form.is_valid():

        message = form.save(commit=False)
        message.ride = ride
        message.author = request.user
        message.save()

    else:

        messages.error(request, 'Message could not be sent.')

    return redirect(
        'ride_detail',
        ride_id=ride.id
    )
