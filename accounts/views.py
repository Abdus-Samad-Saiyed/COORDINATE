"""Views for the accounts app.

URL summary:
  /                           → landing (public)
  /dashboard/                 → dashboard (@login_required)
  /profile/<enrollment>/      → profile view (@login_required)
  /apply/                     → application form (public, throttled)
  /apply/success/             → success page (public)
  /applications/              → superuser: list applications
  /applications/<id>/approve/ → superuser: approve application (POST only)
  /applications/<id>/reject/  → superuser: reject application (POST only)
  /analytics/                 → superuser: analytics dashboard
  /friends/<enrollment>/request/  → send friend request (POST only)
  /friends/<id>/accept/           → accept friend request (POST only)
"""

import json
import os
import sys
import uuid
from datetime import timedelta
from PIL import Image

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import login as auth_login, update_session_auth_hash
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib.auth.hashers import make_password
from django.contrib.auth.password_validation import validate_password
from django.contrib.sessions.models import Session
from django.core.exceptions import ValidationError
from django.core.mail import send_mail
from django.db import IntegrityError, transaction
from django.db.models import Count, Q
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from coordinate.models import RideParticipant, RideRequest

from .forms import AccountApplicationForm, EnrollmentAuthenticationForm
from .models import (
    AccountApplication,
    AuditEvent,
    DirectMessage,
    Friendship,
    FriendRequest,
    PasskeyCredential,
    PhoneOTP,
    PhysicalVerificationRequest,
    User,
    log_audit_event,
)
from .throttling import rate_limit
from .two_factor import (
    can_resend_otp,
    create_phone_otp,
    generate_webauthn_challenge,
    verify_passkey_assertion,
    verify_phone_otp,
)

from campus.services import get_all_services

# ---------------------------------------------------------------------------
# Access helpers
# ---------------------------------------------------------------------------

def _is_superuser(user):
    return user.is_active and user.is_superuser


# ---------------------------------------------------------------------------
# Public views
# ---------------------------------------------------------------------------

def landing(request):
    """Public landing page presenting the Campus Nexus umbrella platform."""
    if request.user.is_authenticated:
        return redirect('dashboard')
    services = get_all_services()
    return render(request, 'landing.html', {
        'services': services,
    })


def service_catalogue(request):
    """Campus Nexus Service Directory accessible by all users."""
    services = get_all_services()
    return render(request, 'nexus/catalogue.html', {
        'services': services,
    })


def enforce_single_session_login(request, user: User):
    """
    Ensure each account can only have one active session at a time.
    Invalidates any previous session across other devices/browsers, and records current session key.
    """
    if user.current_session_key:
        try:
            Session.objects.filter(session_key=user.current_session_key).delete()
            log_audit_event(
                event_type='SESSION_TERMINATED_CONCURRENT',
                actor_enrollment=user.enrollment_number,
                description='Prior session invalidated on concurrent device/browser login',
            )
        except Exception:
            pass

    if not request.session.session_key:
        request.session.save()
    user.current_session_key = request.session.session_key
    user.save(update_fields=['current_session_key'])


def _safe_redirect_url(request, redirect_to, fallback='dashboard'):
    """Ensure redirection target belongs to the current host and scheme."""
    if redirect_to and url_has_allowed_host_and_scheme(
        url=redirect_to,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        return redirect_to
    return fallback


@rate_limit(key_prefix='login', limit=10, period_seconds=60)
def custom_login_view(request, extra_context=None):
    """Enrollment-based authentication with single concurrent session & 2FA intercept.
    Compatible with Django admin login redirection (admin.site.login = custom_login_view).
    """
    if request.user.is_authenticated:
        return redirect('dashboard')

    redirect_to = _safe_redirect_url(request, request.POST.get('next', request.GET.get('next', '')), fallback='')

    if request.method == 'POST':
        form = EnrollmentAuthenticationForm(request, data=request.POST)
        if form.is_valid():
            user = form.get_user()

            # Synthetic branch debug accounts (20XX...) bypass 2FA only when DEBUG=True or test runner
            if user.is_debug_account and (settings.DEBUG or 'test' in sys.argv):
                auth_login(request, user)
                enforce_single_session_login(request, user)
                log_audit_event(
                    event_type='LOGIN_SUCCESS',
                    actor_enrollment=user.enrollment_number,
                    description='Debug account signed in successfully (2FA bypassed)',
                )
                return redirect(redirect_to or 'dashboard')

            # Real student accounts with 2FA enabled require 2FA OTP verification
            if user.two_factor_enabled:
                request.session['pre_2fa_user_id'] = user.id
                request.session['pre_2fa_redirect'] = redirect_to
                request.session['pre_2fa_time'] = timezone.now().timestamp()
                otp, raw_code = create_phone_otp(user, purpose='2FA')
                return redirect('two_factor_verify')

            auth_login(request, user)
            enforce_single_session_login(request, user)
            log_audit_event(
                event_type='LOGIN_SUCCESS',
                actor_enrollment=user.enrollment_number,
                description='Student signed in successfully',
            )
            return redirect(redirect_to or 'dashboard')
        else:
            log_audit_event(
                event_type='LOGIN_FAILURE',
                actor_enrollment=request.POST.get('username', '')[:20],
                description='Failed login attempt',
            )
    else:
        form = EnrollmentAuthenticationForm(request)

    context = {
        'form': form,
        'next': redirect_to,
    }
    if extra_context:
        context.update(extra_context)

    return render(request, 'registration/login.html', context)


def two_factor_verify(request):
    """Handle 2FA Phone SMS verification and Passkey bypass options."""
    user_id = request.session.get('pre_2fa_user_id')
    pre_2fa_time = request.session.get('pre_2fa_time')
    now_ts = timezone.now().timestamp()

    # Expire pre-2FA session state after 5 minutes (300 seconds)
    if not user_id or not pre_2fa_time or (now_ts - pre_2fa_time) > 300:
        request.session.pop('pre_2fa_user_id', None)
        request.session.pop('pre_2fa_redirect', None)
        request.session.pop('pre_2fa_time', None)
        messages.error(request, "Authentication session expired. Please sign in again.")
        return redirect('login')

    user = get_object_or_404(User, id=user_id)
    redirect_to = _safe_redirect_url(request, request.session.get('pre_2fa_redirect', 'dashboard'))

    p = user.phone_number or ''
    masked_phone = f"{p[:3]} {'*' * max(0, len(p) - 6)} {p[-3:]}" if len(p) >= 6 else p
    e = user.email or ''
    masked_email = f"{e[:2]}***@{e.split('@')[1]}" if '@' in e else e

    registered_passkeys = list(
        PasskeyCredential.objects.filter(user=user)
        .values('credential_id', 'name')
    )

    if request.method == 'POST':
        action = request.POST.get('action')
        if action == 'resend':
            can_resend, wait_seconds = can_resend_otp(user, purpose='2FA')
            if can_resend:
                otp, raw_code = create_phone_otp(user, purpose='2FA')
                messages.info(request, "A new 6-digit verification code has been dispatched to your email and phone.")
            else:
                messages.warning(request, f"Please wait {wait_seconds} seconds before requesting a new code.")
            return redirect('two_factor_verify')

        elif action == 'verify':
            otp_code = request.POST.get('otp_code', '').strip()
            success, msg = verify_phone_otp(user, submitted_code=otp_code, purpose='2FA')
            if success:
                request.session.pop('pre_2fa_user_id', None)
                request.session.pop('pre_2fa_redirect', None)
                request.session.pop('pre_2fa_time', None)

                auth_login(request, user, backend='django.contrib.auth.backends.ModelBackend')
                enforce_single_session_login(request, user)
                # 10-minute grace window for modifying security details
                request.session['security_otp_verified_until'] = (timezone.now() + timedelta(minutes=10)).isoformat()
                log_audit_event(
                    event_type='LOGIN_SUCCESS',
                    actor_enrollment=user.enrollment_number,
                    description='2FA OTP successfully verified via email/SMS',
                )
                messages.success(request, f"Identity verified. Welcome back, {user.display_name}!")
                return redirect(redirect_to or 'dashboard')
            else:
                messages.error(request, msg)

    return render(request, 'registration/two_factor.html', {
        'masked_phone': masked_phone,
        'masked_email': masked_email,
        'user_obj': user,
        'registered_passkeys': registered_passkeys,
    })


def _get_webauthn_rp_id(request):
    """Return a valid domain string for WebAuthn rp.id or None if host is an IP address."""
    host = request.get_host().split(':')[0]
    try:
        import ipaddress
        ipaddress.ip_address(host)
        return None
    except ValueError:
        return host


def passkey_auth_challenge(request):
    """Generate WebAuthn challenge for bypassing 2FA with biometric / Windows Hello passkey."""
    user_id = request.session.get('pre_2fa_user_id') or (request.user.id if request.user.is_authenticated else None)
    if not user_id:
        return JsonResponse({'error': 'No authentication session in progress.'}, status=401)

    user = get_object_or_404(User, id=user_id)
    challenge = generate_webauthn_challenge()
    request.session['passkey_challenge'] = challenge

    credentials = list(
        PasskeyCredential.objects.filter(user=user)
        .values_list('credential_id', flat=True)
    )

    return JsonResponse({
        'challenge': challenge,
        'credential_ids': credentials,
        'rp_id': _get_webauthn_rp_id(request),
    })


@require_POST
def passkey_auth_verify(request):
    """Verify WebAuthn client assertion and bypass 2FA upon biometric / Windows Hello match."""
    user_id = request.session.get('pre_2fa_user_id')
    pre_2fa_time = request.session.get('pre_2fa_time')
    now_ts = timezone.now().timestamp()

    if not user_id or not pre_2fa_time or (now_ts - pre_2fa_time) > 300:
        return JsonResponse({'success': False, 'error': 'Session expired. Please sign in again.'}, status=401)

    user = get_object_or_404(User, id=user_id)
    redirect_to = _safe_redirect_url(request, request.session.get('pre_2fa_redirect', '/dashboard/'), fallback='/dashboard/')
    challenge = request.session.pop('passkey_challenge', '')
    if not challenge:
        return JsonResponse({'success': False, 'error': 'Challenge already consumed or missing. Please try again.'}, status=400)

    try:
        data = json.loads(request.body.decode('utf-8'))
        credential_id = data.get('credential_id', '')
        client_data_json = data.get('client_data_json', '')

        success, msg = verify_passkey_assertion(user, credential_id, client_data_json, challenge)
        if success:
            request.session.pop('pre_2fa_user_id', None)
            request.session.pop('pre_2fa_redirect', None)
            request.session.pop('pre_2fa_time', None)

            auth_login(request, user, backend='django.contrib.auth.backends.ModelBackend')
            enforce_single_session_login(request, user)
            request.session['security_otp_verified_until'] = (timezone.now() + timedelta(minutes=10)).isoformat()
            log_audit_event(
                event_type='LOGIN_SUCCESS',
                actor_enrollment=user.enrollment_number,
                description='2FA bypassed via Windows Hello / Biometric Passkey',
            )
            return JsonResponse({'success': True, 'redirect_url': redirect_to or '/dashboard/'})
        else:
            return JsonResponse({'success': False, 'error': msg}, status=400)
    except Exception as exc:
        return JsonResponse({'success': False, 'error': str(exc)}, status=400)


@login_required
def passkey_reg_challenge(request):
    """Generate registration challenge for saving a biometric / Windows Hello key."""
    challenge = generate_webauthn_challenge()
    request.session['passkey_reg_challenge'] = challenge
    return JsonResponse({
        'challenge': challenge,
        'user_id': str(request.user.id),
        'user_name': request.user.enrollment_number,
        'display_name': request.user.display_name,
        'rp_id': _get_webauthn_rp_id(request),
    })


@login_required
@require_POST
def passkey_reg_verify(request):
    """Register and store new PasskeyCredential for the authenticated student."""
    try:
        data = json.loads(request.body.decode('utf-8'))
        credential_id = data.get('credential_id', '').strip()
        public_key = data.get('public_key', '').strip()
        key_name = data.get('name', '').strip() or 'Windows Hello / Biometric Key'

        if not credential_id:
            return JsonResponse({'success': False, 'error': 'Credential ID is required.'}, status=400)

        PasskeyCredential.objects.update_or_create(
            user=request.user,
            credential_id=credential_id,
            defaults={
                'public_key': public_key,
                'name': key_name[:100],
            }
        )

        request.user.two_factor_enabled = True
        request.user.save(update_fields=['two_factor_enabled'])

        return JsonResponse({'success': True, 'message': 'Passkey registered successfully!'})
    except Exception as exc:
        return JsonResponse({'success': False, 'error': str(exc)}, status=400)



@rate_limit(key_prefix='send_signup_otp', limit=5, period_seconds=60)
@require_POST
def send_signup_otp(request):
    """Dispatch phone and email OTP for student registration verification."""
    phone = request.POST.get('phone_number', '').strip()
    email = request.POST.get('email', '').strip().lower()
    if not phone or not email:
        try:
            body = json.loads(request.body.decode('utf-8'))
            phone = phone or body.get('phone_number', '').strip()
            email = email or body.get('email', '').strip().lower()
        except Exception:
            pass

    if not phone or len(phone) < 10:
        return JsonResponse({'success': False, 'error': 'Please provide a valid phone number.'}, status=400)

    can_resend, wait_sec = can_resend_otp(phone_number=phone, email=email, purpose='SIGNUP')
    if not can_resend:
        return JsonResponse({'success': False, 'error': f'Please wait {wait_sec} seconds before requesting a new code.'}, status=429)

    otp, raw_code = create_phone_otp(phone_number=phone, email=email, purpose='SIGNUP')
    dest_parts = []
    if email:
        dest_parts.append(f"email ({email})")
    if phone:
        dest_parts.append(f"mobile ({phone[-4:]})")
    dest_str = " and ".join(dest_parts) or "your contacts"
    return JsonResponse({
        'success': True,
        'message': f'Verification code dispatched to {dest_str}. Check your email inbox or SMS.',
    })


@login_required
@require_POST
def send_security_otp(request):
    """Dispatch phone and email OTP to currently logged-in student to authorize security edits.
    Strictly dispatches to the stored contact details of request.user; client overrides are ignored.
    """
    user = request.user
    if user.is_debug_account:
        return JsonResponse({'success': True, 'message': 'Debug account: OTP bypassed.'})

    target_phone = user.phone_number
    target_email = user.email
    if not target_phone and not target_email:
        return JsonResponse({'success': False, 'error': 'No registered contact (phone or email) found on account.'}, status=400)

    can_resend, wait_sec = can_resend_otp(user=user, phone_number=target_phone, email=target_email, purpose='SECURITY_CHANGE')
    if not can_resend:
        return JsonResponse({'success': False, 'error': f'Please wait {wait_sec} seconds before requesting a new code.'}, status=429)

    otp, raw_code = create_phone_otp(user=user, phone_number=target_phone, email=target_email, purpose='SECURITY_CHANGE')
    dest_parts = []
    if target_email:
        dest_parts.append(f"email ({target_email})")
    if target_phone:
        dest_parts.append(f"mobile ({target_phone[-4:]})")
    dest_str = " and ".join(dest_parts)
    return JsonResponse({
        'success': True,
        'message': f'Verification code dispatched to {dest_str}. Check your email or SMS.',
    })


def forgot_password_view(request):
    """Forgotten password recovery: Phone SMS / Email OTP reset or Physical In-Person Desk request."""
    if request.user.is_authenticated:
        return redirect('dashboard')

    active_tab = 'otp'
    if request.method == 'POST':
        action = request.POST.get('action')

        if action == 'request_otp':
            enrollment = request.POST.get('enrollment_number', '').strip().upper()
            user = User.objects.filter(enrollment_number=enrollment, is_deleted=False).first()
            if not user:
                messages.error(request, "No active student account found with that enrollment number.")
            elif user.is_debug_account and getattr(settings, 'DEBUG', False):
                messages.info(request, "This is a debug account. Password is 'Debug@123'.")
                return redirect('login')
            else:
                otp, raw_code = create_phone_otp(user, purpose='PASSWORD_RESET')
                request.session['reset_user_id'] = user.id
                e = user.email or ''
                masked_email = f"{e[:2]}***@{e.split('@')[1]}" if '@' in e else e
                p = user.phone_number or ''
                masked_phone = f"***-***-{p[-4:]}" if len(p) >= 4 else p
                messages.success(request, f"A 6-digit reset code was dispatched to your registered email ({masked_email}) and mobile ({masked_phone}).")
                return render(request, 'registration/forgot_password.html', {
                    'step': 'verify_otp',
                    'enrollment_number': user.enrollment_number,
                    'masked_phone': masked_phone,
                    'masked_email': masked_email,
                })

        elif action == 'verify_reset':
            user_id = request.session.get('reset_user_id')
            user = get_object_or_404(User, id=user_id) if user_id else None
            if not user:
                messages.error(request, "Session expired. Please request a new reset code.")
                return redirect('forgot_password')

            otp_code = request.POST.get('otp_code', '').strip()
            new_password = request.POST.get('new_password', '').strip()
            confirm_password = request.POST.get('confirm_password', '').strip()

            if new_password != confirm_password:
                messages.error(request, "Passwords do not match.")
                return render(request, 'registration/forgot_password.html', {
                    'step': 'verify_otp',
                    'enrollment_number': user.enrollment_number,
                })

            try:
                validate_password(new_password, user)
            except ValidationError as e:
                for error in e.messages:
                    messages.error(request, error)
                return render(request, 'registration/forgot_password.html', {
                    'step': 'verify_otp',
                    'enrollment_number': user.enrollment_number,
                })

            ok, msg = verify_phone_otp(user, submitted_code=otp_code, purpose='PASSWORD_RESET')
            if ok:
                user.set_password(new_password)
                # Revoke all active sessions for this user across all devices/API
                for s in Session.objects.filter(expire_date__gt=timezone.now()):
                    try:
                        data = s.get_decoded()
                        if str(data.get('_auth_user_id')) == str(user.id):
                            s.delete()
                    except Exception:
                        pass
                user.current_session_key = ''
                user.save()
                del request.session['reset_user_id']
                log_audit_event(
                    event_type='SECURITY_SETTINGS_UPDATED',
                    actor_enrollment=user.enrollment_number,
                    description='Password reset successfully via Phone OTP; existing sessions revoked',
                )
                messages.success(request, "Your password has been reset successfully! Please sign in with your new password.")
                return redirect('login')
            else:
                messages.error(request, msg)
                return render(request, 'registration/forgot_password.html', {
                    'step': 'verify_otp',
                    'enrollment_number': user.enrollment_number,
                })

        elif action == 'physical_request':
            enrollment = request.POST.get('enrollment_number', '').strip().upper()
            contact_email = request.POST.get('contact_email', '').strip()
            contact_phone = request.POST.get('contact_phone', '').strip()
            student_notes = request.POST.get('student_notes', '').strip()

            user = User.objects.filter(enrollment_number=enrollment, is_deleted=False).first()
            if not user:
                messages.error(request, "No registered account found with that enrollment number.")
                active_tab = 'in_person'
            else:
                existing = PhysicalVerificationRequest.objects.filter(user=user, status='PENDING').first()
                if existing:
                    messages.warning(request, "You already have an active pending physical verification request. Please visit the Campus Operations Desk.")
                else:
                    PhysicalVerificationRequest.objects.create(
                        user=user,
                        contact_email=contact_email,
                        contact_phone=contact_phone,
                        student_notes=student_notes,
                        status='PENDING',
                    )
                    log_audit_event(
                        event_type='PHYSICAL_VERIFICATION_REQUESTED',
                        actor_enrollment=user.enrollment_number,
                        description='Physical In-Person Verification request submitted',
                    )
                    messages.success(request, "In-Person Verification Request submitted! Please visit the Campus Operations Desk with your official Institute ID card.")
                return redirect('login')

    return render(request, 'registration/forgot_password.html', {
        'step': 'request_otp',
        'active_tab': active_tab,
    })


@rate_limit(key_prefix='apply', limit=5, period_seconds=60)
def apply_account(request):
    """Student account application with mandatory phone OTP verification."""
    if request.user.is_authenticated:
        return redirect('dashboard')

    if request.method == 'POST':
        form = AccountApplicationForm(request.POST)
        enrollment = request.POST.get('enrollment_number', '').strip().upper()
        phone_otp = request.POST.get('phone_otp', '').strip()
        phone_num = request.POST.get('phone_number', '').strip()

        is_debug = enrollment.startswith('20XX')
        phone_verified = False

        if is_debug:
            phone_verified = True
        else:
            if not phone_otp:
                form.add_error(None, "Phone verification code is required. Please verify your phone number via OTP.")
            else:
                phone_verified, otp_err = verify_phone_otp(phone_number=phone_num, submitted_code=phone_otp, purpose='SIGNUP')
                if not phone_verified:
                    form.add_error(None, f"Phone verification failed: {otp_err}")

        if form.is_valid() and phone_verified:
            with transaction.atomic():
                application = form.save(commit=False)
                application.application_number = uuid.uuid4().hex[:8].upper()
                application.password = make_password(form.cleaned_data['password'])
                application.phone_verified = True
                application.save()
            return render(request, 'accounts/application_success.html', {
                'application': application,
            })
    else:
        form = AccountApplicationForm()

    designated_admins = User.objects.filter(is_superuser=True, is_active=True).order_by('enrollment_number')
    return render(request, 'accounts/apply.html', {
        'form': form,
        'designated_admins': designated_admins,
    })


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
        'services': get_all_services(),
    })


@login_required
def profile_view(request, enrollment_number):
    """View any verified user's profile with privacy safeguards, password change, and 10-minute grace window."""
    profile_user = get_object_or_404(
        User,
        enrollment_number=enrollment_number.strip().upper(),
    )

    is_self = profile_user == request.user
    is_moderator = request.user.is_staff or request.user.is_superuser

    # 10-minute session grace window for security changes
    grace_str = request.session.get('security_otp_verified_until')
    grace_active = False
    if grace_str:
        try:
            grace_dt = timezone.datetime.fromisoformat(grace_str)
            if timezone.now() < grace_dt:
                grace_active = True
        except Exception:
            pass

    if request.method == 'POST' and is_self:
        new_phone = request.POST.get('phone_number', '').strip()
        new_email = request.POST.get('email', '').strip().lower()
        new_password = request.POST.get('new_password', '').strip()
        confirm_password = request.POST.get('confirm_password', '').strip()
        new_2fa = (request.POST.get('two_factor_enabled') == 'on')

        phone_changed = bool(new_phone and new_phone != profile_user.phone_number)
        email_changed = bool(new_email and new_email != profile_user.email)
        password_changed = bool(new_password)
        two_factor_changed = (new_2fa != profile_user.two_factor_enabled)
        security_changed = phone_changed or email_changed or password_changed or two_factor_changed

        if email_changed:
            if User.objects.filter(email=new_email, is_deleted=False).exclude(id=profile_user.id).exists():
                messages.error(request, "This email address is already registered to another active account.")
                return redirect('profile', enrollment_number=profile_user.enrollment_number)

        if password_changed:
            current_password = request.POST.get('current_password', '').strip()
            if current_password:
                if not profile_user.check_password(current_password):
                    messages.error(request, "Current password is incorrect.")
                    return redirect('profile', enrollment_number=profile_user.enrollment_number)
            elif not grace_active:
                messages.error(request, "Current password is required and must be correct to set a new password.")
                return redirect('profile', enrollment_number=profile_user.enrollment_number)

            if new_password != confirm_password:
                messages.error(request, "New passwords do not match. Please re-enter.")
                return redirect('profile', enrollment_number=profile_user.enrollment_number)

            try:
                validate_password(new_password, profile_user)
            except ValidationError as e:
                for error in e.messages:
                    messages.error(request, error)
                return redirect('profile', enrollment_number=profile_user.enrollment_number)

        # Non-debug accounts require OTP if security details changed and grace period expired
        if security_changed and not profile_user.is_debug_account and not grace_active:
            sec_otp = request.POST.get('security_otp_code', '').strip()
            otp_valid, otp_msg = verify_phone_otp(profile_user, submitted_code=sec_otp, purpose='SECURITY_CHANGE')
            if not otp_valid:
                messages.error(request, f"Security verification required: {otp_msg}")
                return redirect('profile', enrollment_number=profile_user.enrollment_number)
            # Renew grace window
            request.session['security_otp_verified_until'] = (timezone.now() + timedelta(minutes=10)).isoformat()
            grace_active = True

        # Profile photo upload with strict validation
        if 'profile_photo' in request.FILES:
            photo = request.FILES['profile_photo']
            if photo.size > 5 * 1024 * 1024:
                messages.error(request, "Profile photo file size exceeds 5MB limit.")
                return redirect('profile', enrollment_number=profile_user.enrollment_number)

            ext = os.path.splitext(photo.name)[1].lower()
            if ext not in ('.jpg', '.jpeg', '.png', '.webp'):
                messages.error(request, "Only JPG, PNG, and WebP image formats are allowed.")
                return redirect('profile', enrollment_number=profile_user.enrollment_number)

            try:
                img = Image.open(photo)
                img.verify()
                photo.seek(0)
                img = Image.open(photo)
                if img.format.lower() not in ('jpeg', 'png', 'webp'):
                    messages.error(request, "Invalid or unsupported image format.")
                    return redirect('profile', enrollment_number=profile_user.enrollment_number)
            except Exception:
                messages.error(request, "Uploaded file is not a valid image.")
                return redirect('profile', enrollment_number=profile_user.enrollment_number)

            photo.name = f"{uuid.uuid4().hex}{ext}"
            profile_user.profile_photo = photo
        # Phone number update
        if new_phone:
            profile_user.phone_number = new_phone
        # Email update
        if new_email:
            profile_user.email = new_email
        # Password update
        if password_changed:
            profile_user.set_password(new_password)
        # Short Bio (up to 500 characters)
        if 'bio' in request.POST:
            profile_user.bio = request.POST.get('bio', '').strip()[:500]
        # Privacy & Security toggles
        profile_user.show_friends_publicly = (request.POST.get('show_friends_publicly') == 'on')
        profile_user.hide_online_status = (request.POST.get('hide_online_status') == 'on')
        profile_user.hide_from_search = (request.POST.get('hide_from_search') == 'on')
        profile_user.two_factor_enabled = new_2fa
        profile_user.save()

        if password_changed:
            update_session_auth_hash(request, profile_user)
            enforce_single_session_login(request, profile_user)

        if security_changed:
            request.session['security_otp_verified_until'] = (timezone.now() + timedelta(minutes=10)).isoformat()
            log_audit_event(
                event_type='SECURITY_SETTINGS_UPDATED',
                actor_enrollment=profile_user.enrollment_number,
                description='User updated security credentials/settings',
            )

        messages.success(request, 'Profile and security settings updated successfully.')
        return redirect('profile', enrollment_number=profile_user.enrollment_number)

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

    # Friends list visibility (public toggle check)
    can_see_friends = is_self or profile_user.show_friends_publicly or is_moderator
    friends = []
    if can_see_friends:
        friendships = Friendship.objects.filter(
            Q(user1=profile_user) | Q(user2=profile_user)
        ).select_related('user1', 'user2')
        friends = [f.user2 if f.user1 == profile_user else f.user1 for f in friendships]

    # Phone number privacy check
    can_see_phone = profile_user.can_view_phone_number(request.user)

    # Recent reviews: complaint text is only visible to authorized moderators
    recent_reviews = (
        profile_user.received_reviews
        .select_related('reviewer', 'ride')
        .order_by('-created_at')[:5]
    )

    return render(request, 'accounts/profile.html', {
        'profile_user': profile_user,
        'is_self': is_self,
        'is_friend': is_friend,
        'can_see_phone': can_see_phone,
        'can_see_friends': can_see_friends,
        'friends': friends,
        'is_moderator': is_moderator,
        'friend_request_sent': friend_request_sent,
        'incoming_request': incoming_request,
        'recent_reviews': recent_reviews,
        'grace_active': grace_active,
    })


@login_required
def user_search(request):
    """Search for students by enrollment number or name with privacy filtering."""
    query = request.GET.get('q', '').strip()

    # Base queryset: verified active students excluding oneself and soft-deleted accounts
    students_qs = User.objects.filter(verified=True, is_deleted=False, is_active=True).exclude(id=request.user.id)
    if not (request.user.is_staff or request.user.is_superuser):
        students_qs = students_qs.filter(hide_from_search=False)

    if query:
        students_qs = students_qs.filter(
            Q(enrollment_number__icontains=query) |
            Q(first_name__icontains=query) |
            Q(last_name__icontains=query) |
            Q(branch__icontains=query)
        )

    students_qs = students_qs.order_by('enrollment_number')[:60]

    # Map friendships and friend requests
    user_friends = set(
        Friendship.objects.filter(Q(user1=request.user) | Q(user2=request.user))
        .values_list('user1_id', 'user2_id')
    )
    friend_ids = {u2 if u1 == request.user.id else u1 for u1, u2 in user_friends}

    sent_request_ids = set(
        FriendRequest.objects.filter(sender=request.user).values_list('receiver_id', flat=True)
    )
    incoming_requests_map = {
        fr.sender_id: fr.id for fr in FriendRequest.objects.filter(receiver=request.user)
    }

    student_list = []
    for s in students_qs:
        student_list.append({
            'student': s,
            'is_friend': s.id in friend_ids,
            'request_sent': s.id in sent_request_ids,
            'incoming_request_id': incoming_requests_map.get(s.id),
        })

    return render(request, 'accounts/user_search.html', {
        'query': query,
        'student_list': student_list,
        'total_count': len(student_list),
    })


@login_required
@require_POST
def unfriend_user(request, enrollment_number):
    """Remove a connection between friends."""
    target_user = get_object_or_404(User, enrollment_number=enrollment_number.strip().upper())
    deleted, _ = Friendship.objects.filter(
        Q(user1=request.user, user2=target_user) |
        Q(user1=target_user, user2=request.user)
    ).delete()
    if deleted:
        messages.info(request, f'Removed {target_user.enrollment_number} from your friends.')
    return redirect('profile', enrollment_number=target_user.enrollment_number)


@login_required
def direct_chat_view(request, enrollment_number):
    """1-on-1 WebSocket chat room between confirmed friends."""
    friend = get_object_or_404(User, enrollment_number=enrollment_number.strip().upper())
    if friend == request.user:
        messages.warning(request, "You cannot chat with yourself.")
        return redirect('dashboard')

    is_friend = Friendship.objects.filter(
        Q(user1=request.user, user2=friend) | Q(user1=friend, user2=request.user)
    ).exists()

    if not is_friend:
        messages.error(request, "Direct messaging is reserved for confirmed friends.")
        return redirect('profile', enrollment_number=friend.enrollment_number)

    if request.method == 'POST':
        content = request.POST.get('content', '').strip()
        if content:
            DirectMessage.objects.create(
                sender=request.user,
                recipient=friend,
                content=content[:2000],
            )
            return redirect('direct_chat', enrollment_number=friend.enrollment_number)

    # Mark unread messages from this friend as read
    DirectMessage.objects.filter(
        sender=friend,
        recipient=request.user,
        is_read=False,
    ).update(is_read=True)

    # Load recent conversation history (last 100 messages)
    chat_messages = list(
        DirectMessage.objects
        .filter(
            (Q(sender=request.user, recipient=friend) | Q(sender=friend, recipient=request.user))
        )
        .order_by('created_at')[:100]
    )

    return render(request, 'accounts/friend_chat.html', {
        'friend': friend,
        'chat_messages': chat_messages,
    })


@login_required
def messages_inbox(request):
    """Overview of all friend conversations with latest snippet and unread badges."""
    friendships = Friendship.objects.filter(
        Q(user1=request.user) | Q(user2=request.user)
    ).select_related('user1', 'user2')
    friends = [f.user2 if f.user1 == request.user else f.user1 for f in friendships]

    conversations = []
    for friend in friends:
        latest = (
            DirectMessage.objects
            .filter(Q(sender=request.user, recipient=friend) | Q(sender=friend, recipient=request.user))
            .order_by('-created_at')
            .first()
        )
        unread = (
            DirectMessage.objects
            .filter(sender=friend, recipient=request.user, is_read=False)
            .count()
        )
        conversations.append({
            'friend': friend,
            'latest_message': latest,
            'unread_count': unread,
        })

    conversations.sort(
        key=lambda c: c['latest_message'].created_at if c['latest_message'] else timezone.now() - timezone.timedelta(days=3650),
        reverse=True
    )

    return render(request, 'accounts/messages_inbox.html', {
        'conversations': conversations,
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


@require_POST
@login_required
@user_passes_test(_is_superuser)
def approve_application(request, application_id):
    """
    POST only. Creates a verified User from the application, sends a
    notification email, and removes the application from the queue.
    """
    with transaction.atomic():
        application = get_object_or_404(AccountApplication, id=application_id, approved=False)

        # If a user with that enrollment already exists, just clean up.
        if User.objects.filter(enrollment_number=application.enrollment_number).exists():
            application.delete()
            messages.warning(request, 'A user with that enrollment number already exists.')
            if request.htmx:
                return HttpResponse('')
            return redirect('application_list')

        user = User.objects.create(
            enrollment_number=application.enrollment_number,
            username=application.enrollment_number,
            first_name=application.full_name.split()[0] if application.full_name else '',
            last_name=' '.join(application.full_name.split()[1:]) if application.full_name else '',
            email=application.email,
            phone_number=application.phone_number,
            gender=application.gender,
            password=application.password,   # already hashed
            verified=True,
        )
        application.approved = True
        application.save()
        application.delete()

    # Send approval email (fire-and-forget; console backend in dev, SMTP in prod)
    try:
        send_mail(
            subject='Campus Nexus — Your Account Has Been Approved',
            message=(
                f'Hi {user.first_name},\n\n'
                f'Your account for enrollment number {user.enrollment_number} '
                f'has been verified and approved by campus administrators.\n\n'
                f'You can now log in at https://campusnexus.nitsri.ac.in/login/\n\n'
                f'— The Campus Nexus Team, NIT Srinagar'
            ),
            from_email=None,   # uses DEFAULT_FROM_EMAIL
            recipient_list=[user.email] if user.email else [],
            fail_silently=True,
        )
    except Exception:
        pass

    if request.htmx:
        return HttpResponse('')

    messages.success(request, f'Account approved for {user.enrollment_number}.')
    return redirect('application_list')


@require_POST
@login_required
@user_passes_test(_is_superuser)
def reject_application(request, application_id):
    """
    POST only. Safely rejects and discards a pending student application,
    freeing the enrollment number for correction/resubmission.
    """
    with transaction.atomic():
        application = get_object_or_404(AccountApplication, id=application_id, approved=False)
        enrollment = application.enrollment_number
        application.delete()

    if request.htmx:
        return HttpResponse('')

    messages.info(request, f'Application for {enrollment} was rejected and removed.')
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

@require_POST
@login_required
def send_friend_request(request, enrollment_number):
    target = get_object_or_404(
        User,
        enrollment_number=enrollment_number.strip().upper(),
    )

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


@require_POST
@login_required
def accept_friend_request(request, request_id):
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


@require_POST
@login_required
def decline_friend_request(request, request_id):
    friend_request = get_object_or_404(
        FriendRequest,
        id=request_id,
        receiver=request.user,
    )
    sender = friend_request.sender
    friend_request.delete()
    messages.info(request, f'Friend request from {sender} was declined.')
    return redirect('profile', enrollment_number=request.user.enrollment_number)
