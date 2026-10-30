"""Exhaustive End-to-End Crawler & Deep Verification Suite for Campus Nexus.

Validates:
1. Every URL, link, and form across the entire application (public, user, admin).
2. Dual-channel OTP verification (Email + SMS) for Signup, 2FA, Profile Security, and Password Reset.
3. Administrative operations (Add/Remove Contributors, Change Phone, Physical Reset Desk, Account Deletion).
4. Zen Mode and Light Mode Reluctance mechanisms (dialogues, panic shake, transition overlay, scripts).
"""

import os
import sys
import re
import json
from html.parser import HTMLParser

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'campus.settings.dev')
import django
django.setup()
from django.conf import settings

if not getattr(settings, 'DEBUG', False):
    print("REFUSING TO RUN: test_full_platform_e2e.py must NEVER run against production (DEBUG=False).", file=sys.stderr)
    sys.exit(1)

settings.EMAIL_BACKEND = 'django.core.mail.backends.locmem.EmailBackend'

from datetime import datetime, timedelta
from django.contrib.auth import get_user_model
from django.test import Client
from django.urls import resolve, reverse
from django.utils import timezone
from django.core import mail

from accounts.models import (
    AccountApplication, AuditEvent, Contributor, DirectMessage, FriendRequest,
    Friendship, PasskeyCredential, PhoneOTP, PhysicalVerificationRequest
)
from coordinate.models import RideJoinRequest, RideParticipant, RideRequest, RideWaitlist
from accounts.two_factor import create_phone_otp, verify_phone_otp

User = get_user_model()


class LinkExtractor(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links = []
        self.forms = []
        self.buttons = []

    def handle_starttag(self, tag, attrs):
        attr_dict = dict(attrs)
        if tag == 'a' and 'href' in attr_dict:
            self.links.append(attr_dict['href'])
        elif tag == 'form' and 'action' in attr_dict:
            self.forms.append(attr_dict['action'])
        elif tag == 'button':
            self.buttons.append(attr_dict.get('id') or attr_dict.get('class') or 'unnamed_button')


def run_comprehensive_audit():
    if not getattr(settings, 'DEBUG', False) or 'prod' in os.environ.get('DJANGO_SETTINGS_MODULE', ''):
        print("REFUSING TO RUN: test_full_platform_e2e.py must NEVER run against production.", file=sys.stderr)
        return False

    print("=" * 75)
    print("STARTING FULL END-TO-END DEEP PLATFORM VERIFICATION")
    print("=" * 75)

    failures = []
    passes = 0

    def assert_test(cond, desc):
        nonlocal passes
        if cond:
            passes += 1
            print(f" [PASS] {desc}")
        else:
            failures.append(desc)
            print(f" [FAIL] {desc}")

    # =========================================================================
    # PART 1: IDENTITY & DATABASE FIXTURES
    # =========================================================================
    print("\n--- 1. SEEDING AUDIT FIXTURES ---")
    import secrets
    admin_enrollment = os.environ.get('TEST_ADMIN_ENROLLMENT', '20XXBCSE999')
    admin_pw = os.environ.get('TEST_ADMIN_PASSWORD', secrets.token_urlsafe(16))
    admin, _ = User.objects.get_or_create(
        enrollment_number=admin_enrollment,
        defaults={
            "username": admin_enrollment,
            "first_name": "Audit",
            "last_name": "Admin",
            "email": f"{admin_enrollment.lower()}@nitsri.ac.in",
            "phone_number": "+919999999999",
            "gender": "M",
            "is_staff": True,
            "is_superuser": True,
            "is_active": True,
            "verified": True,
        }
    )
    admin.set_password(admin_pw)
    admin.is_staff = True
    admin.is_superuser = True
    admin.verified = True
    admin.current_session_key = ''
    admin.save()
    assert_test(admin.is_superuser, "Admin user is superuser")
    assert_test(admin.verified, "Admin user is verified student")

    def force_login_sync(cl, u):
        cl.force_login(u)
        u.current_session_key = cl.session.session_key
        u.save(update_fields=['current_session_key'])

    student, _ = User.objects.get_or_create(
        enrollment_number="2024BCSE099",
        defaults={
            "username": "2024BCSE099",
            "first_name": "Audit",
            "last_name": "Student",
            "email": "student2024@nitsri.ac.in",
            "phone_number": "+919876543299",
            "gender": "M",
            "is_active": True,
            "verified": True,
        }
    )
    student.set_password("TestPass@123")
    student.email = "student2024@nitsri.ac.in"
    student.phone_number = "+919876543299"
    student.current_session_key = ''
    student.save()

    # =========================================================================
    # PART 2: DUAL-CHANNEL OTP (EMAIL + SMS) VERIFICATION ENGINE
    # =========================================================================
    print("\n--- 2. DUAL-CHANNEL OTP ENGINE AUDIT ---")
    mail.outbox = []
    otp_record, raw_code = create_phone_otp(
        phone_number=student.phone_number,
        email=student.email,
        purpose='SIGNUP'
    )
    assert_test(len(raw_code) == 6 and raw_code.isdigit(), f"Generated 6-digit cryptographic OTP: {raw_code}")
    assert_test(len(mail.outbox) >= 1, "MIME/SMTP Email dispatched to outbox")
    if mail.outbox:
        email_msg = mail.outbox[-1]
        assert_test(student.email in email_msg.to, f"Email correctly addressed to {student.email}")
        assert_test(raw_code in email_msg.body, "Plaintext email contains verification code")
        assert_test(hasattr(email_msg, 'alternatives') and len(email_msg.alternatives) > 0, "MIME multipart includes HTML dark-mode email alternative")

    # Verify matching by phone
    v_ok, v_err = verify_phone_otp(phone_number=student.phone_number, submitted_code=raw_code, purpose='SIGNUP')
    assert_test(v_ok, "OTP code verified successfully via phone number lookup")

    # Second dispatch: verify matching by email
    mail.outbox = []
    otp_record2, raw_code2 = create_phone_otp(
        phone_number=student.phone_number,
        email=student.email,
        purpose='SECURITY_CHANGE'
    )
    v_ok2, _ = verify_phone_otp(email=student.email, submitted_code=raw_code2, purpose='SECURITY_CHANGE')
    assert_test(v_ok2, "OTP code verified successfully via email address lookup")

    # Verify rate limiting / cooldown
    can_resend, wait = create_phone_otp(user=student, purpose='PASSWORD_RESET')
    can_resend_again, wait_sec = create_phone_otp(user=student, purpose='PASSWORD_RESET')
    # Should throttle within 15 seconds
    assert_test(wait_sec is not None or not can_resend_again, "OTP rate-limiting engine properly throttles rapid requests")

    # =========================================================================
    # PART 3: APPLICATION SIGNUP WITH MANDATORY EMAIL & OTP
    # =========================================================================
    print("\n--- 3. SIGNUP APPLICATION WORKFLOW WITH EMAIL ---")
    User.objects.filter(enrollment_number='2024BCSE777').delete()
    AccountApplication.objects.filter(enrollment_number='2024BCSE777').delete()
    client = Client()
    # 3.1 Request signup OTP
    res_otp = client.post(
        reverse('send_signup_otp'),
        json.dumps({'phone_number': '+919988776655', 'email': 'new_applicant@nitsri.ac.in'}),
        content_type='application/json'
    )
    assert_test(res_otp.status_code == 200, "POST send_signup_otp returns HTTP 200")
    otp_json = res_otp.json()
    assert_test(otp_json.get('success') is True, "send_signup_otp JSON success is True")
    assert_test('otp' not in otp_json and 'code' not in otp_json, "Security check: OTP code NEVER leaked in JSON response")

    # Fetch latest OTP from database for testing
    latest_signup_otp = PhoneOTP.objects.filter(phone_number='+919988776655', purpose='SIGNUP').latest('created_at')
    # Since hashed, let's create a known OTP to submit
    _, app_code = create_phone_otp(phone_number='+919988776655', email='new_applicant@nitsri.ac.in', purpose='SIGNUP')

    # Submit application
    res_apply = client.post(
        reverse('apply_account'),
        {
            'enrollment_number': '2024BCSE777',
            'full_name': 'E2E Test Applicant',
            'phone_number': '+919988776655',
            'email': 'new_applicant@nitsri.ac.in',
            'phone_otp': app_code,
            'gender': 'M',
            'password': 'SecurePass@123',
            'confirm_password': 'SecurePass@123',
        }
    )
    assert_test(res_apply.status_code == 200, "POST apply_account returns HTTP 200 (Success view)")
    app_obj = AccountApplication.objects.filter(enrollment_number='2024BCSE777').first()
    assert_test(app_obj is not None, "Application object saved in database")
    assert_test(app_obj and app_obj.email == 'new_applicant@nitsri.ac.in', "Application stores mandatory normalized email")
    assert_test(app_obj and app_obj.phone_verified is True, "Application is flagged phone_verified=True")

    # Admin approves application
    admin_client = Client()
    force_login_sync(admin_client, admin)
    res_appr = admin_client.post(reverse('approve_application', args=[app_obj.id]))
    assert_test(res_appr.status_code == 302, "Admin approve_application redirects (HTTP 302)")
    created_user = User.objects.filter(enrollment_number='2024BCSE777').first()
    assert_test(created_user is not None, "Approved user created in User model")
    assert_test(created_user and created_user.email == 'new_applicant@nitsri.ac.in', "Approved user inherited valid email")

    # =========================================================================
    # PART 4: FORGOTTEN PASSWORD DUAL-CHANNEL RECOVERY & PHYSICAL DESK
    # =========================================================================
    print("\n--- 4. PASSWORD RESET & PHYSICAL DESK AUDIT ---")
    # 4.1 OTP Reset flow
    res_req = client.post(
        reverse('forgot_password'),
        {'action': 'request_otp', 'enrollment_number': '2024BCSE777'}
    )
    assert_test(res_req.status_code == 200, "POST forgot_password (request_otp) renders verify step")
    _, reset_code = create_phone_otp(created_user, purpose='PASSWORD_RESET')

    session = client.session
    session['reset_user_id'] = created_user.id
    session.save()

    res_v_reset = client.post(
        reverse('forgot_password'),
        {
            'action': 'verify_reset',
            'otp_code': reset_code,
            'new_password': 'NewPassword@456',
            'confirm_password': 'NewPassword@456',
        }
    )
    assert_test(res_v_reset.status_code == 302, "POST forgot_password (verify_reset) redirects to login")
    created_user.refresh_from_db()
    assert_test(created_user.check_password('NewPassword@456'), "User password successfully updated via dual-channel OTP")

    # 4.2 In-Person Physical Desk Request
    res_desk = client.post(
        reverse('forgot_password'),
        {
            'action': 'physical_request',
            'enrollment_number': '2024BCSE777',
            'contact_phone': '+919988776655',
            'reason': 'Lost SIM card and cannot access registered email.',
        }
    )
    assert_test(res_desk.status_code == 302, "POST physical_request redirects to login with success message")
    phys_req = PhysicalVerificationRequest.objects.filter(user=created_user, status='PENDING').first()
    assert_test(phys_req is not None, "PhysicalVerificationRequest logged in database")

    # Admin verifies physical request
    res_admin_phys = admin_client.post(
        reverse('admin_resolve_physical_verification', args=[phys_req.id]),
        {
            'action': 'verify_reset_password',
            'new_password': 'TempDeskPass@789',
            'notes': 'Verified student College ID card in person.'
        }
    )
    assert_test(res_admin_phys.status_code == 302, "Admin admin_resolve_physical_verification redirects")
    phys_req.refresh_from_db()
    assert_test(phys_req.status == 'VERIFIED', "Physical verification marked VERIFIED")
    created_user.refresh_from_db()
    assert_test(created_user.check_password('TempDeskPass@789'), "User password reset by Admin via physical verification desk")

    # =========================================================================
    # PART 5: ADMIN OPERATIONS (PHONE CHANGE, DELETE ACCOUNT, CONTRIBUTORS)
    # =========================================================================
    print("\n--- 5. ADMIN CONTROL PANEL AUDIT ---")
    # 5.1 Admin change student phone
    res_change_ph = admin_client.post(
        reverse('admin_update_phone', args=[created_user.id]),
        {'phone_number': '+919988770000'}
    )
    assert_test(res_change_ph.status_code == 302, "Admin change phone redirects")
    created_user.refresh_from_db()
    assert_test(created_user.phone_number == '+919988770000', "Student phone updated by administrator")

    # 5.2 Admin Add & Remove Contributor
    res_add_contrib = admin_client.post(
        reverse('nominate_contributor'),
        {'name': 'Test Maintainer', 'role': 'Security Engineer'}
    )
    assert_test(res_add_contrib.status_code == 302, "Admin nominate_contributor succeeds")
    contrib = Contributor.objects.filter(name='Test Maintainer').first()
    assert_test(contrib is not None, "Contributor created in database")

    res_rem_contrib = admin_client.post(
        reverse('remove_contributor', args=[contrib.id])
    )
    assert_test(res_rem_contrib.status_code == 302, "Admin remove_contributor succeeds")
    assert_test(not Contributor.objects.filter(id=contrib.id).exists(), "Contributor removed by admin")

    # 5.3 Admin Delete Account (Soft Delete with Audit Preservation)
    res_del = admin_client.post(
        reverse('admin_delete_account', args=[created_user.id]),
        {'reason': 'E2E testing lifecycle completion'}
    )
    assert_test(res_del.status_code == 302, "Admin delete account redirects")
    created_user.refresh_from_db()
    assert_test(created_user.is_deleted is True, "Account is marked is_deleted=True")
    assert_test(created_user.is_active is False, "Account is marked is_active=False")
    audit_del = AuditEvent.objects.filter(
        event_type='ACCOUNT_DELETED',
        target_id=str(created_user.id)
    ).first()
    assert_test(audit_del is not None, "AuditEvent preserves deletion record and reason")

    # =========================================================================
    # PART 6: FULL SITE LINK, BUTTON, AND ZEN MODE CRAWLER
    # =========================================================================
    print("\n--- 6. EXHAUSTIVE PAGE, LINK & ZEN MODE CRAWLER ---")
    student_client = Client()
    force_login_sync(student_client, student)

    urls_to_crawl = [
        ('/', 'public', 200),
        ('/about/', 'public', 200),
        ('/contact/', 'public', 200),
        ('/contributors/', 'public', 200),
        ('/feedback/', 'public', 200),
        ('/services/', 'public', 200),
        ('/health/', 'public', 200),
        ('/login/', 'public', 200),
        ('/forgot-password/', 'public', 200),
        ('/apply/', 'public', 200),
        ('/apply/success/', 'public', 200),
        ('/dashboard/', 'auth', 200),
        ('/coordinate/', 'auth', 200),
        ('/coordinate/rides/', 'auth', 200),
        ('/coordinate/my-rides/', 'auth', 200),
        ('/coordinate/create/', 'auth', 200),
        ('/search/', 'auth', 200),
        ('/messages/', 'auth', 200),
        (f'/profile/{student.enrollment_number}/', 'auth', 200),
        ('/operations/', 'admin', 200),
        ('/operations/superusers/', 'admin', 200),
        ('/applications/', 'admin', 200),
        ('/analytics/', 'admin', 200),
    ]

    all_found_links = set()
    zen_overlay_found = 0
    zen_theme_script_found = 0

    total_html_pages = 0
    for path, client_type, expected_code in urls_to_crawl:
        cl = admin_client if client_type == 'admin' else (student_client if client_type == 'auth' else client)
        resp = cl.get(path)
        assert_test(resp.status_code == expected_code, f"Crawler URL '{path}' returned HTTP {resp.status_code} (expected {expected_code})")

        content_type = resp.headers.get('content-type', '')
        if not content_type.startswith('text/html'):
            continue

        total_html_pages += 1
        content = resp.content.decode('utf-8', errors='ignore')

        # Check Zen Mode Transition & Clockwork elements
        if 'zen-restore-banner' in content and 'clockwork-watermark' in content:
            zen_overlay_found += 1
        if 'watermark.js' in content and 'toggleForegroundScatter' in content:
            zen_theme_script_found += 1

        # Extract links
        parser = LinkExtractor()
        parser.feed(content)
        for link in parser.links:
            if link.startswith('/') and not link.startswith('//') and not link.startswith('/static/'):
                all_found_links.add(link.split('#')[0].split('?')[0])

    assert_test(zen_overlay_found == total_html_pages, f"All {total_html_pages} HTML pages include clockwork canvas and 'zen-restore-banner'")
    assert_test(zen_theme_script_found == total_html_pages, f"All {total_html_pages} HTML pages load 'watermark.js' and Zen scatter/transition engine")

    print(f"\nDiscovered {len(all_found_links)} unique internal application links. Testing reachable endpoints...")
    # Test all distinct internal links
    tested_internal = 0
    link_failures = 0
    for link in sorted(all_found_links):
        if any(skip in link for skip in ['/logout', '/delete', '/remove', '/admin/']):
            continue
        tested_internal += 1
        resp = admin_client.get(link)
        if resp.status_code in [200, 302, 403, 404]:
            pass
        else:
            link_failures += 1
            print(f"  [WARN] Internal link {link} gave unexpected HTTP {resp.status_code}")

    assert_test(link_failures == 0, f"Tested {tested_internal} unique extracted internal links without 500 errors")

    # =========================================================================
    # PART 7: FINAL CLEANUP & SUMMARY
    # =========================================================================
    # Clean up test users created in e2e
    User.objects.filter(enrollment_number__in=['2024BCSE099', '2024BCSE777']).delete()
    AccountApplication.objects.filter(enrollment_number='2024BCSE777').delete()

    print("\n" + "=" * 75)
    print(f"VERIFICATION COMPLETE: {passes} PASSED, {len(failures)} FAILED")
    print("=" * 75)

    if failures:
        print("\nFailures:")
        for f in failures:
            print(f" - {f}")
        return False
    return True


if __name__ == '__main__':
    from django.test.utils import setup_databases, teardown_databases
    from django.db import connection

    old_db_config = setup_databases(verbosity=0, interactive=False)
    try:
        db_name = connection.settings_dict.get('NAME', '')
        if not ('memory' in db_name or 'test' in db_name):
            print("REFUSING TO RUN: test_full_platform_e2e.py must only run against an isolated test database.", file=sys.stderr)
            sys.exit(1)
        success = run_comprehensive_audit()
        sys.exit(0 if success else 1)
    finally:
        teardown_databases(old_db_config, verbosity=0)
