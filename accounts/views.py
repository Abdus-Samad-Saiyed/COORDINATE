"""
Views for the accounts app.

URL summary:
  /                           → landing (public)
  /dashboard/                 → dashboard (@login_required)
  /profile/<enrollment>/      → profile view
  /apply/                     → application form
  /apply/success/             → success page
  /applications/              → superuser: list applications
  /applications/<id>/approve/ → superuser: approve application
  /analytics/                 → superuser: analytics dashboard
  /friends/<enrollment>/request/  → send friend request
  /friends/<id>/accept/           → accept friend request
"""

import uuid

from django.contrib import messages
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib.auth.hashers import make_password
from django.core.mail import send_mail
from django.db import IntegrityError, transaction
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect, render

from coordinate.models import RideParticipant, RideRequest

from .forms import AccountApplicationForm
from .models import AccountApplication, Friendship, FriendRequest, User


# ---------------------------------------------------------------------------
# Access helpers
# ---------------------------------------------------------------------------

def _is_superuser(user):
    return user.is_superuser


# ---------------------------------------------------------------------------
# Public views
# ---------------------------------------------------------------------------

def landing(request):
    """Public landing page. Authenticated users go straight to dashboard."""
    if request.user.is_authenticated:
        return redirect('dashboard')
    return render(request, 'landing.html')


def apply_account(request):
    """Anyone can submit an application for a verified student account."""
    if request.user.is_authenticated:
        return redirect('dashboard')

    if request.method == 'POST':
        form = AccountApplicationForm(request.POST)
        if form.is_valid():
            application = form.save(commit=False)
            application.application_number = uuid.uuid4().hex[:8].upper()
            application.password = make_password(form.cleaned_data['password'])
            application.save()
            return redirect('application_success')
    else:
        form = AccountApplicationForm()

    return render(request, 'accounts/apply.html', {'form': form})


def application_success(request):
    return render(request, 'accounts/application_success.html')


# ---------------------------------------------------------------------------
# Authenticated views
# ---------------------------------------------------------------------------

@login_required
def dashboard(request):
    """User's home page. Shows their active ride if they have one."""
    active_participation = (
        RideParticipant.objects
        .filter(user=request.user, ride__status__in=['OPEN', 'FULL'])
        .select_related('ride', 'ride__creator')
        .first()
    )
    return render(request, 'accounts/dashboard.html', {
        'active_participation': active_participation,
    })


@login_required
def profile_view(request, enrollment_number):
    """View any verified user's profile."""
    profile_user = get_object_or_404(User, enrollment_number=enrollment_number)

    is_self = profile_user == request.user
    is_friend = False
    friend_request_sent = False
    incoming_request = None

    if not is_self:
        is_friend = Friendship.objects.filter(
            Q(user1=request.user, user2=profile_user) |
            Q(user1=profile_user, user2=request.user)
        ).exists()

        if not is_friend:
            friend_request_sent = FriendRequest.objects.filter(
                sender=request.user, receiver=profile_user
            ).exists()
            incoming_request = FriendRequest.objects.filter(
                sender=profile_user, receiver=request.user
            ).first()

    # Recent completed rides together (shared history)
    recent_reviews = (
        profile_user.received_reviews
        .select_related('reviewer', 'ride')
        .order_by('-created_at')[:5]
    )

    return render(request, 'accounts/profile.html', {
        'profile_user': profile_user,
        'is_self': is_self,
        'is_friend': is_friend,
        'friend_request_sent': friend_request_sent,
        'incoming_request': incoming_request,
        'recent_reviews': recent_reviews,
    })


# ---------------------------------------------------------------------------
# Admin: Applications
# ---------------------------------------------------------------------------

@login_required
@user_passes_test(_is_superuser)
def application_list(request):
    """List all pending (unapproved) applications."""
    applications = AccountApplication.objects.filter(approved=False)
    return render(request, 'accounts/application_list.html', {
        'applications': applications,
    })


@login_required
@user_passes_test(_is_superuser)
def approve_application(request, application_id):
    """
    POST only. Creates a verified User from the application, sends a
    notification email, and removes the application from the queue.
    """
    if request.method != 'POST':
        return redirect('application_list')

    with transaction.atomic():
        application = get_object_or_404(AccountApplication, id=application_id, approved=False)

        # If a user with that enrollment already exists, just clean up.
        if User.objects.filter(enrollment_number=application.enrollment_number).exists():
            application.delete()
            messages.warning(request, 'A user with that enrollment number already exists.')
            return redirect('application_list')

        user = User.objects.create(
            enrollment_number=application.enrollment_number,
            username=application.enrollment_number,
            first_name=application.full_name.split()[0] if application.full_name else '',
            last_name=' '.join(application.full_name.split()[1:]) if application.full_name else '',
            phone_number=application.phone_number,
            gender=application.gender,
            password=application.password,   # already hashed
            verified=True,
        )
        application.approved = True
        application.save()
        application.delete()

    # Send approval email (fire-and-forget; console backend in dev)
    try:
        send_mail(
            subject='COORDINATE — Your account has been approved',
            message=(
                f'Hi {user.first_name},\n\n'
                f'Your account for enrollment number {user.enrollment_number} '
                f'has been verified and approved.\n\n'
                f'You can now log in at https://coordinate.nitsri.ac.in/login/\n\n'
                f'— The COORDINATE team'
            ),
            from_email=None,   # uses DEFAULT_FROM_EMAIL
            recipient_list=[],  # add user.email here if collected
            fail_silently=True,
        )
    except Exception:
        pass

    if request.htmx:
        # Return empty content — HTMX will swap out the row
        from django.http import HttpResponse
        return HttpResponse('')

    messages.success(request, f'Account approved for {user.enrollment_number}.')
    return redirect('application_list')


# ---------------------------------------------------------------------------
# Admin: Analytics
# ---------------------------------------------------------------------------

@login_required
@user_passes_test(_is_superuser)
def admin_analytics(request):
    """Superuser analytics dashboard."""
    from datetime import timedelta
    from django.utils import timezone

    now = timezone.now()
    week_ago = now - timedelta(days=7)

    ride_stats = RideRequest.objects.aggregate(
        total=Count('id'),
        open=Count('id', filter=Q(status='OPEN')),
        full=Count('id', filter=Q(status='FULL')),
        completed=Count('id', filter=Q(status='COMPLETED')),
        recent=Count('id', filter=Q(created_at__gte=week_ago)),
    )

    user_stats = User.objects.aggregate(
        total=Count('id'),
        verified=Count('id', filter=Q(verified=True)),
    )

    pending_count = AccountApplication.objects.filter(approved=False).count()

    popular_routes = (
        RideRequest.objects
        .values('route')
        .annotate(count=Count('id'))
        .order_by('-count')[:5]
    )
    # Attach human-readable label
    route_label = dict(RideRequest.ROUTE_CHOICES)
    for r in popular_routes:
        r['label'] = route_label.get(r['route'], r['route'])

    top_users = (
        User.objects
        .filter(verified=True)
        .order_by('-rides_completed')[:10]
    )

    flagged_users = (
        User.objects
        .filter(behavior_reports__gt=0)
        .order_by('-behavior_reports')[:10]
    )

    return render(request, 'accounts/admin_analytics.html', {
        'ride_stats': ride_stats,
        'user_stats': user_stats,
        'pending_count': pending_count,
        'popular_routes': popular_routes,
        'top_users': top_users,
        'flagged_users': flagged_users,
    })


# ---------------------------------------------------------------------------
# Social: Friends
# ---------------------------------------------------------------------------

@login_required
def send_friend_request(request, enrollment_number):
    if request.method != 'POST':
        return redirect('profile', enrollment_number=enrollment_number)

    target = get_object_or_404(User, enrollment_number=enrollment_number)

    if target == request.user:
        messages.error(request, "You can't send a friend request to yourself.")
        return redirect('profile', enrollment_number=enrollment_number)

    already_friends = Friendship.objects.filter(
        Q(user1=request.user, user2=target) |
        Q(user1=target, user2=request.user)
    ).exists()

    if already_friends:
        messages.info(request, 'You are already friends.')
        return redirect('profile', enrollment_number=enrollment_number)

    FriendRequest.objects.get_or_create(sender=request.user, receiver=target)
    messages.success(request, f'Friend request sent to {enrollment_number}.')
    return redirect('profile', enrollment_number=enrollment_number)


@login_required
def accept_friend_request(request, request_id):
    if request.method != 'POST':
        return redirect('dashboard')

    friend_request = get_object_or_404(
        FriendRequest,
        id=request_id,
        receiver=request.user,
    )

    try:
        with transaction.atomic():
            Friendship.objects.create(
                user1=friend_request.sender,
                user2=friend_request.receiver,
            )
            friend_request.delete()
        messages.success(request, f'You are now friends with {friend_request.sender}.')
    except IntegrityError:
        friend_request.delete()
        messages.info(request, 'Friendship already exists.')

    return redirect('profile', enrollment_number=request.user.enrollment_number)
