import uuid

from django.shortcuts import (
    render,
    redirect,
    get_object_or_404
)

from django.contrib.auth.decorators import (
    login_required,
    user_passes_test
)
from django.views.decorators.http import require_POST

from django.contrib.auth.hashers import (
    make_password
)
from django.db import IntegrityError, transaction

from .models import (
    User,
    AccountApplication,
    FriendRequest,
    Friendship
)

from .forms import (
    AccountApplicationForm
)

from coordinate.models import (
    RideParticipant
)


@login_required
def dashboard(request):

    active_participation = (
        RideParticipant.objects
        .filter(
            user=request.user,
            ride__status__in=['OPEN', 'FULL']
        )
        .select_related('ride')
        .first()
    )

    return render(
        request,
        'accounts/dashboard.html',
        {
            'active_participation':
                active_participation
        }
    )


@login_required
def profile_view(
    request,
    enrollment_number
):

    profile_user = get_object_or_404(
        User,
        enrollment_number=enrollment_number
    )

    is_friend = Friendship.objects.filter(
        user1=request.user,
        user2=profile_user
    ).exists() or Friendship.objects.filter(
        user1=profile_user,
        user2=request.user
    ).exists()

    friend_request_sent = FriendRequest.objects.filter(
        sender=request.user,
        receiver=profile_user
    ).exists()

    incoming_request = FriendRequest.objects.filter(
        sender=profile_user,
        receiver=request.user
    ).first()

    return render(
        request,
        'accounts/profile.html',
        {
            'profile_user': profile_user,
            'is_friend': is_friend,
            'friend_request_sent':
                friend_request_sent,
            'incoming_request':
                incoming_request,
        }
    )


def apply_account(request):

    if request.method == 'POST':

        form = AccountApplicationForm(
            request.POST
        )

        if form.is_valid():

            application = form.save(
                commit=False
            )

            application.application_number = (
                str(uuid.uuid4())[:8]
                .upper()
            )

            application.password = (
                make_password(
                    application.password
                )
            )

            application.save()

            return render(
                request,
                'accounts/application_success.html',
                {
                    'application': application
                }
            )

    else:

        form = AccountApplicationForm()

    return render(
        request,
        'accounts/apply.html',
        {
            'form': form
        }
    )


@user_passes_test(
    lambda u: u.is_superuser
)
def application_list(request):

    applications = (
        AccountApplication.objects.all()
    )

    return render(
        request,
        'accounts/application_list.html',
        {
            'applications': applications
        }
    )


@user_passes_test(
    lambda u: u.is_superuser
)
@require_POST
def approve_application(
    request,
    application_id
):

    application = get_object_or_404(
        AccountApplication,
        id=application_id
    )

    with transaction.atomic():

        if User.objects.filter(
            enrollment_number=application.enrollment_number
        ).exists():

            application.delete()

            return redirect(
                'application_list'
            )

        User.objects.create(

            enrollment_number=
                application.enrollment_number,

            username=
                application.full_name,

            gender=
                application.gender,

            phone_number=
                application.phone_number,

            password=
                application.password,

            verified=True
        )

        application.delete()

        return redirect(
            'application_list'
        )


@login_required
@require_POST
def send_friend_request(
    request,
    enrollment_number
):

    receiver = get_object_or_404(
        User,
        enrollment_number=enrollment_number
    )

    already_friends = Friendship.objects.filter(
        user1=request.user,
        user2=receiver
    ).exists() or Friendship.objects.filter(
        user1=receiver,
        user2=request.user
    ).exists()

    if receiver != request.user and not already_friends:

        FriendRequest.objects.get_or_create(
            sender=request.user,
            receiver=receiver
        )

    return redirect(
        'profile',
        enrollment_number=enrollment_number
    )


@login_required
@require_POST
def accept_friend_request(
    request,
    request_id
):

    friend_request = get_object_or_404(
        FriendRequest,
        id=request_id,
        receiver=request.user
    )

    try:

        Friendship.objects.get_or_create(
            user1=friend_request.sender,
            user2=friend_request.receiver
        )

    except IntegrityError:

        pass

    friend_request.delete()

    return redirect(
        'profile',
        enrollment_number=request.user.enrollment_number
    )
