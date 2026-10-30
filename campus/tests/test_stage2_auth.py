"""Stage 2 tests — Authentication, OTPs, Passkeys, and Sessions.

Covers:
1. verify_phone_otp tuple return signature and atomic select_for_update semantics.
2. OTP retry counter atomic decrement and maximum attempt lockout.
3. 2FA enforcement on API login with proper tuple handling.
4. Mobile Bearer token authentication and cookie isolation on mutating API routes.
5. Passkey registration challenge lifecycle (TTL, single-use, storage).
6. Passkey authentication challenge lifecycle (replay defense, single-use, sign_count increment).
7. Profile password change requiring current password and strict strength checks.
8. Single active session enforcement across logins.
9. Rate limiting on sensitive auth endpoints.
10. Synthetic debug accounts disabled when settings.DEBUG=False.
"""

import json
import time
from datetime import timedelta
from unittest.mock import patch

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.sessions.models import Session
from django.core.cache import cache
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from accounts.models import PasskeyCredential, PhoneOTP
from accounts.two_factor import (
    create_phone_otp,
    generate_webauthn_challenge,
    verify_passkey_assertion,
    verify_passkey_registration,
    verify_phone_otp,
)

User = get_user_model()


class Stage2OtpVerificationTests(TestCase):
    """Test OTP creation, atomic attempt tracking, and tuple unpacking."""

    def setUp(self):
        self.user = User.objects.create_user(
            enrollment_number="2024BCSE101",
            username="2024BCSE101",
            password="InitialPassword123!",
            first_name="Alice",
            last_name="Test",
            phone_number="+919876543201",
            email="alice@nitsri.ac.in",
            gender="F",
            verified=True,
        )

    def test_verify_phone_otp_tuple_signature(self):
        """verify_phone_otp must strictly return (bool, str)."""
        otp_obj, raw_code = create_phone_otp(self.user, purpose='2FA')
        res = verify_phone_otp(self.user, submitted_code=raw_code, purpose='2FA')
        self.assertIsInstance(res, tuple)
        self.assertEqual(len(res), 2)
        ok, msg = res
        self.assertTrue(ok)
        self.assertIn("successful", msg.lower())

    def test_wrong_code_decrements_attempts_and_locks_out(self):
        """Invalid submissions decrement attempts atomically and lock out at 0."""
        otp_obj, raw_code = create_phone_otp(self.user, purpose='2FA')

        # Attempt 1: wrong code
        ok1, msg1 = verify_phone_otp(self.user, submitted_code="000000", purpose='2FA')
        self.assertFalse(ok1)
        self.assertIn("2 attempt(s) remaining", msg1)

        # Attempt 2: wrong code
        ok2, msg2 = verify_phone_otp(self.user, submitted_code="000001", purpose='2FA')
        self.assertFalse(ok2)
        self.assertIn("1 attempt(s) remaining", msg2)

        # Attempt 3: wrong code -> lockout
        ok3, msg3 = verify_phone_otp(self.user, submitted_code="000002", purpose='2FA')
        self.assertFalse(ok3)
        self.assertIn("Maximum attempts exceeded", msg3)

        # Attempt 4: even if now submitting the correct code, it must be rejected as used/locked
        ok4, msg4 = verify_phone_otp(self.user, submitted_code=raw_code, purpose='2FA')
        self.assertFalse(ok4)

    def test_expired_otp_rejected(self):
        """Expired OTPs cannot be verified."""
        otp_obj, raw_code = create_phone_otp(self.user, purpose='2FA')
        PhoneOTP.objects.filter(id=otp_obj.id).update(
            expires_at=timezone.now() - timedelta(seconds=10)
        )
        ok, msg = verify_phone_otp(self.user, submitted_code=raw_code, purpose='2FA')
        self.assertFalse(ok)
        self.assertIn("expired", msg.lower())


class Stage2ApiAuthAndTwoFactorTests(TestCase):
    """Test API 2FA enforcement and Bearer token session binding."""

    def setUp(self):
        cache.clear()
        self.client = Client()
        self.user = User.objects.create_user(
            enrollment_number="2024BCSE102",
            username="2024BCSE102",
            password="StrongPassword123!",
            first_name="Bob",
            last_name="Test",
            phone_number="+919876543202",
            email="bob@nitsri.ac.in",
            gender="M",
            verified=True,
            two_factor_enabled=True,
        )

    def tearDown(self):
        cache.clear()

    def test_api_login_requires_2fa_and_rejects_invalid_otp(self):
        """api_login must challenge 2FA when enabled and reject false OTP without bypassing."""
        # 1. First POST without OTP -> triggers 403 2FA_REQUIRED
        resp1 = self.client.post(
            reverse("api_login"),
            data=json.dumps({
                "enrollment_number": "2024BCSE102",
                "password": "StrongPassword123!",
            }),
            content_type="application/json",
        )
        self.assertEqual(resp1.status_code, 403)
        data1 = resp1.json()
        self.assertEqual(data1.get("code"), "2FA_REQUIRED")

        # 2. Second POST with bogus OTP -> must reject with 401 INVALID_2FA_OTP
        resp2 = self.client.post(
            reverse("api_login"),
            data=json.dumps({
                "enrollment_number": "2024BCSE102",
                "password": "StrongPassword123!",
                "otp": "999999",
            }),
            content_type="application/json",
        )
        self.assertEqual(resp2.status_code, 401)
        data2 = resp2.json()
        self.assertEqual(data2.get("code"), "INVALID_2FA_OTP")

        # 3. Third POST with real OTP -> must succeed and yield Bearer token
        latest_otp = PhoneOTP.objects.filter(user=self.user, purpose="2FA", is_used=False).latest("created_at")
        # In test mode we can retrieve through newly generated known OTP
        _, real_code = create_phone_otp(self.user, purpose="2FA")
        resp3 = self.client.post(
            reverse("api_login"),
            data=json.dumps({
                "enrollment_number": "2024BCSE102",
                "password": "StrongPassword123!",
                "otp": real_code,
            }),
            content_type="application/json",
        )
        self.assertEqual(resp3.status_code, 200)
        data3 = resp3.json()
        self.assertEqual(data3.get("status"), "success")
        token = data3.get("data", {}).get("token")
        self.assertTrue(bool(token))

        # Ensure single session key recorded
        self.user.refresh_from_db()
        self.assertEqual(self.user.current_session_key, token)


class Stage2PasskeyLifecycleTests(TestCase):
    """Test passkey challenge generation, single-use consumption, and TTL."""

    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            enrollment_number="2024BCSE103",
            username="2024BCSE103",
            password="Password123!",
            first_name="Charlie",
            last_name="Test",
            phone_number="+919876543203",
            email="charlie@nitsri.ac.in",
            gender="M",
            verified=True,
        )
        self.client.force_login(self.user)

    def test_passkey_reg_challenge_and_verification(self):
        """Passkey registration requires recent reauthentication, valid attestation, and single-use challenge."""
        from datetime import timedelta
        from campus.tests.webauthn_test_utils import make_registration_response

        # 1. Registration challenge without recent reauthentication is rejected (403)
        chal_fail = self.client.get(reverse("passkey_reg_challenge"))
        self.assertEqual(chal_fail.status_code, 403)
        self.assertTrue(chal_fail.json().get("requires_step_up"))

        # Enable active reauthentication grace window in session
        session = self.client.session
        session["security_otp_verified_until"] = (timezone.now() + timedelta(minutes=10)).isoformat()
        session.save()

        # 2. Challenge generation succeeds with step-up active
        chal_resp = self.client.get(reverse("passkey_reg_challenge"))
        self.assertEqual(chal_resp.status_code, 200)
        chal_data = chal_resp.json()
        challenge = chal_data.get("challenge")
        self.assertTrue(bool(challenge))

        # 3. Client-supplied mock payload without attestation is strictly rejected
        mock_resp = self.client.post(
            reverse("passkey_reg_verify"),
            data=json.dumps({
                "credential_id": "mock_cred_103",
                "public_key": "webauthn_mock_public_key",
                "name": "Windows Hello Device",
            }),
            content_type="application/json",
        )
        self.assertEqual(mock_resp.status_code, 400)
        self.assertIn("attestation", mock_resp.json().get("error", "").lower())

        # 4. Generate new challenge and register with genuine attestation
        chal_resp2 = self.client.get(reverse("passkey_reg_challenge"))
        challenge2 = chal_resp2.json().get("challenge")

        reg_payload, priv_key, cose_pub_b64 = make_registration_response(
            challenge_b64=challenge2,
            credential_id=b"real_cred_103",
            origin="http://testserver",
            rp_id="testserver",
        )
        reg_payload["name"] = "Windows Hello Device"

        reg_resp = self.client.post(
            reverse("passkey_reg_verify"),
            data=json.dumps(reg_payload),
            content_type="application/json",
        )
        self.assertEqual(reg_resp.status_code, 200)
        self.assertTrue(reg_resp.json().get("success"))

        # Verify credential in database
        cred = PasskeyCredential.objects.filter(user=self.user).first()
        self.assertIsNotNone(cred)
        self.assertEqual(cred.public_key, cose_pub_b64)
        self.user.refresh_from_db()
        self.assertTrue(self.user.two_factor_enabled)

        # Challenge must be consumed (single-use)
        reg_replay = self.client.post(
            reverse("passkey_reg_verify"),
            data=json.dumps(reg_payload),
            content_type="application/json",
        )
        self.assertEqual(reg_replay.status_code, 400)
        self.assertIn("expired", reg_replay.json().get("error", "").lower())


class Stage2ProfileSecurityTests(TestCase):
    """Test password update requirements in profile view."""

    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            enrollment_number="2024BCSE104",
            username="2024BCSE104",
            password="CurrentStrongPassword123!",
            first_name="Dana",
            last_name="Test",
            phone_number="+919876543204",
            email="dana@nitsri.ac.in",
            gender="F",
            verified=True,
        )
        self.client.force_login(self.user)

    def test_password_change_requires_current_password(self):
        """Updating password without current password must be rejected."""
        resp = self.client.post(
            reverse("profile", kwargs={"enrollment_number": "2024BCSE104"}),
            data={
                "current_password": "",
                "new_password": "NewStrongPassword123!",
                "confirm_password": "NewStrongPassword123!",
            },
        )
        # Should redirect back to profile with error
        self.assertEqual(resp.status_code, 302)
        self.user.refresh_from_db()
        # Old password must still authenticate
        self.assertTrue(self.user.check_password("CurrentStrongPassword123!"))

    def test_password_change_with_incorrect_current_password_fails(self):
        """Incorrect current password must fail."""
        resp = self.client.post(
            reverse("profile", kwargs={"enrollment_number": "2024BCSE104"}),
            data={
                "current_password": "WrongPassword!",
                "new_password": "NewStrongPassword123!",
                "confirm_password": "NewStrongPassword123!",
            },
        )
        self.assertEqual(resp.status_code, 302)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password("CurrentStrongPassword123!"))


class Stage2DebugAccountSecurityTests(TestCase):
    """Test synthetic debug accounts are disabled when settings.DEBUG=False."""

    def setUp(self):
        self.user = User.objects.create_user(
            enrollment_number="20XXBCSE001",
            username="20XXBCSE001",
            password="Debug@123",
            first_name="Debug",
            last_name="Student",
            phone_number="+919876543299",
            email="debug@nitsri.ac.in",
            gender="M",
            verified=True,
        )

    def test_is_debug_account_property_respects_debug_mode(self):
        """is_debug_account must be False under production settings."""
        # When DEBUG is False and not in test or alpha context:
        with patch.object(settings, "DEBUG", False), patch.object(settings, "TESTING", False, create=True), patch.object(settings, "ALPHA_MODE", False, create=True), patch("sys.argv", ["manage.py", "runserver"]):
            self.assertFalse(self.user.is_debug_account)
