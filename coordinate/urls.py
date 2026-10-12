"""URL patterns for the coordinate app."""

from django.urls import path

from .views import (
    complete_ride,
    create_ride,
    join_ride,
    kick_participant,
    leave_ride,
    review_user,
    ride_detail,
    ride_list,
    send_message,
    terminate_ride,
)

urlpatterns = [
    path('',                                            ride_list,          name='ride_list'),
    path('create/',                                     create_ride,        name='create_ride'),
    path('<int:ride_id>/',                              ride_detail,        name='ride_detail'),
    path('<int:ride_id>/join/',                         join_ride,          name='join_ride'),
    path('<int:ride_id>/leave/',                        leave_ride,         name='leave_ride'),
    path('<int:ride_id>/terminate/',                    terminate_ride,     name='terminate_ride'),
    path('<int:ride_id>/complete/',                     complete_ride,      name='complete_ride'),
    path('<int:ride_id>/kick/<int:participant_id>/',    kick_participant,   name='kick_participant'),
    path('<int:ride_id>/review/<int:user_id>/',         review_user,        name='review_user'),
    path('<int:ride_id>/message/',                      send_message,       name='send_message'),
]
