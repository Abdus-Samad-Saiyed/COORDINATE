"""Root URL configuration for COORDINATE."""

from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.urls import include, path

from accounts.forms import EnrollmentAuthenticationForm
from accounts.views import (
    custom_login_view,
    landing,
    passkey_auth_challenge,
    passkey_auth_verify,
    passkey_reg_challenge,
    passkey_reg_verify,
    service_catalogue,
    two_factor_verify,
)
from campus.operations import (
    admin_delete_account,
    admin_resolve_physical_verification,
    admin_update_phone,
    export_applications_csv,
    export_rides_csv,
    export_users_csv,
    health_check,
    manage_superusers,
    operational_dashboard,
)
from campus.services import service_gateway_view
from campus.views import about_view, contact_view, contributors_view, feedback_view, nominate_contributor, remove_contributor

urlpatterns = [
    # Django admin & Operational Dashboard
    path('admin/', admin.site.urls),
    path('operations/', operational_dashboard, name='operational_dashboard'),
    path('operations/superusers/', manage_superusers, name='manage_superusers'),
    path('operations/users/<int:user_id>/update-phone/', admin_update_phone, name='admin_update_phone'),
    path('operations/users/<int:user_id>/delete/', admin_delete_account, name='admin_delete_account'),
    path('operations/physical-verification/<int:request_id>/resolve/', admin_resolve_physical_verification, name='admin_resolve_physical_verification'),
    path('operations/export/rides/', export_rides_csv, name='export_rides_csv'),
    path('operations/export/users/', export_users_csv, name='export_users_csv'),
    path('operations/export/applications/', export_applications_csv, name='export_applications_csv'),

    # System Health Check
    path('health/', health_check, name='health_check'),

    # Campus Nexus Platform Shell, Info & Community
    path('', landing, name='landing'),
    path('about/', about_view, name='about'),
    path('contact/', contact_view, name='contact'),
    path('contributors/', contributors_view, name='contributors'),
    path('contributors/nominate/', nominate_contributor, name='nominate_contributor'),
    path('contributors/<int:contributor_id>/remove/', remove_contributor, name='remove_contributor'),
    path('feedback/', feedback_view, name='feedback'),
    path('report-bug/', feedback_view, name='report_bug'),
    path('services/', service_catalogue, name='service_catalogue'),
    path('services/<slug:slug>/', service_gateway_view, name='service_gateway'),

    # Versioned REST API (v1)
    path('api/v1/', include('campus.api.urls')),

    # 2-Factor Authentication & Biometric / Windows Hello Passkey Engine
    path('login/', custom_login_view, name='login'),
    path('login/2fa/', two_factor_verify, name='two_factor_verify'),
    path('auth/passkey/authenticate/challenge/', passkey_auth_challenge, name='passkey_auth_challenge'),
    path('auth/passkey/authenticate/verify/', passkey_auth_verify, name='passkey_auth_verify'),
    path('auth/passkey/register/challenge/', passkey_reg_challenge, name='passkey_reg_challenge'),
    path('auth/passkey/register/verify/', passkey_reg_verify, name='passkey_reg_verify'),
    path(
        'logout/',
        auth_views.LogoutView.as_view(),
        name='logout',
    ),
    path(
        'password_change/',
        auth_views.PasswordChangeView.as_view(
            template_name='registration/password_change_form.html',
            success_url='/password_change/done/',
        ),
        name='password_change',
    ),
    path(
        'password_change/done/',
        auth_views.PasswordChangeDoneView.as_view(
            template_name='registration/password_change_done.html',
        ),
        name='password_change_done',
    ),

    # Accounts app (dashboard, profile, apply, friends, analytics…)
    path('', include('accounts.urls')),

    # Coordinate app (rides)
    path('coordinate/', include('coordinate.urls')),
]

from django.conf import settings
from django.urls import re_path
from django.views.static import serve

urlpatterns += [
    re_path(r'^media/(?P<path>.*)$', serve, {'document_root': settings.MEDIA_ROOT}),
]

