"""URL configuration for Campus Nexus REST API (v1)."""

from django.urls import path

from .views import (
    api_catalogue,
    api_login,
    api_logout,
    api_me,
    api_my_rides,
    api_ride_create,
    api_ride_detail,
    api_ride_join,
    api_ride_leave,
    api_ride_list,
    api_root,
    api_service_detail,
)

urlpatterns = [
    # API entry point & service directory
    path("", api_root, name="api_root"),
    path("catalogue/", api_catalogue, name="api_catalogue"),
    path("catalogue/<slug:slug>/", api_service_detail, name="api_service_detail"),

    # Auth
    path("auth/login/", api_login, name="api_login"),
    path("auth/logout/", api_logout, name="api_logout"),

    # User profile & stats
    path("me/", api_me, name="api_me"),

    # COORDINATE Rides
    path("rides/", api_ride_list, name="api_ride_list"),
    path("rides/create/", api_ride_create, name="api_ride_create"),
    path("rides/<int:ride_id>/", api_ride_detail, name="api_ride_detail"),
    path("rides/<int:ride_id>/join/", api_ride_join, name="api_ride_join"),
    path("rides/<int:ride_id>/leave/", api_ride_leave, name="api_ride_leave"),
    path("my-rides/", api_my_rides, name="api_my_rides"),
]
