"""Root URL configuration for COORDINATE."""

from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.urls import include, path

from accounts.views import landing

urlpatterns = [
    # Django admin
    path('admin/', admin.site.urls),

    # Landing page (public)
    path('', landing, name='landing'),

    # Auth — provided by Django: /login/, /logout/, /password_change/, etc.
    path(
        'login/',
        auth_views.LoginView.as_view(template_name='registration/login.html'),
        name='login',
    ),
    path(
        'logout/',
        auth_views.LogoutView.as_view(),
        name='logout',
    ),

    # Accounts app (dashboard, profile, apply, friends, analytics…)
    path('', include('accounts.urls')),

    # Coordinate app (rides)
    path('coordinate/', include('coordinate.urls')),
]
