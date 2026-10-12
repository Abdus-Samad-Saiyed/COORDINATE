"""URL patterns for the accounts app."""

from django.urls import path

from .views import (
    accept_friend_request,
    admin_analytics,
    application_list,
    application_success,
    approve_application,
    dashboard,
    profile_view,
    apply_account,
    send_friend_request,
)

urlpatterns = [
    path('dashboard/',                                  dashboard,              name='dashboard'),
    path('profile/<str:enrollment_number>/',            profile_view,           name='profile'),
    path('apply/',                                      apply_account,          name='apply_account'),
    path('apply/success/',                              application_success,    name='application_success'),
    path('applications/',                               application_list,       name='application_list'),
    path('applications/<int:application_id>/approve/',  approve_application,    name='approve_application'),
    path('analytics/',                                  admin_analytics,        name='admin_analytics'),
    path('friends/<str:enrollment_number>/request/',    send_friend_request,    name='send_friend_request'),
    path('friends/<int:request_id>/accept/',            accept_friend_request,  name='accept_friend_request'),
]