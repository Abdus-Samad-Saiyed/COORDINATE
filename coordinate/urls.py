from django.urls import path

from .views import (
    ride_list,
    create_ride,
    join_ride,
    leave_ride,
    terminate_ride,
    ride_detail,
    kick_participant,
    complete_ride,
    review_user,
    send_message
)

urlpatterns = [

    path(
        '',
        ride_list,
        name='ride_list'
    ),

    path(
        'create/',
        create_ride,
        name='create_ride'
    ),

    path(
        'join/<int:ride_id>/',
        join_ride,
        name='join_ride'
    ),

    path(
        'leave/<int:ride_id>/',
        leave_ride,
        name='leave_ride'
    ),

    path(
        'terminate/<int:ride_id>/',
        terminate_ride,
        name='terminate_ride'
    ),

    path(
        'ride/<int:ride_id>/',
        ride_detail,
        name='ride_detail'
    ),

    path(
        'ride/<int:ride_id>/kick/<int:participant_id>/',
        kick_participant,
        name='kick_participant'
    ),

    path(
        'ride/<int:ride_id>/complete/',
        complete_ride,
        name='complete_ride'
    ),

    path(
        'ride/<int:ride_id>/review/<int:user_id>/',
        review_user,
        name='review_user'
    ),

    path(
        'ride/<int:ride_id>/message/',
        send_message,
        name='send_message'
    ),
]
