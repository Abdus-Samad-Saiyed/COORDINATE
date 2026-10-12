from django.urls import path

from .views import (
    dashboard,
    profile_view,
    apply_account,
    application_list,
    approve_application,
    send_friend_request,
    accept_friend_request
)

urlpatterns = [

    path(
        '',
        dashboard,
        name='dashboard'
    ),

    path(
        'profile/<str:enrollment_number>/',
        profile_view,
        name='profile'
    ),

    path(
        'apply/',
        apply_account,
        name='apply_account'
    ),

    path(
        'applications/',
        application_list,
        name='application_list'
    ),

    path(
        'approve/<int:application_id>/',
        approve_application,
        name='approve_application'
    ),

    path(
        'friend-request/<str:enrollment_number>/',
        send_friend_request,
        name='send_friend_request'
    ),

    path(
        'accept-request/<int:request_id>/',
        accept_friend_request,
        name='accept_friend_request'
    ),
]