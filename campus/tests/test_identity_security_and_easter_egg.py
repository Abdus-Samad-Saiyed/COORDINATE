"""
Automated regression tests for:
1. Namespace segregation: 20XX synthetic debug accounts bypass 2FA & phone verification
2. Single concurrent session enforcement (superseded session termination)
3. 10-minute session grace window for security setting modifications
4. Profile password change directly from profile interface
5. Phone OTP verification on registration application
6. Forgotten password flow: Phone SMS OTP vs In-Person Physical Verification Desk
7. Admin Identity Desk: phone update, physical verification resolution, soft deletion preserving trip history
"""

from datetime import timedelta
from django.contrib.auth import authenticate
from django.contrib.sessions.models import Session
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import (
    AccountApplication,
    AuditEvent,
    PhoneOTP,
    PhysicalVerificationRequest,
    User,
)
from accounts.two_factor import create_phone_otp, verify_phone_otp
from coordinate.models import RideRequest, RideParticipant


class IdentitySecurityArchitectureTests(TestCase):
    def setUp(self):
        self.client = Client()

        # Superaccount (User's personal enrollment)
        self.superaccount = User.objects.create_superuser(
            enrollment_number="2024BCSE065",
            username="2024BCSE065",
            password="AbSm72000@123",
            first_name="Abdur",
            last_name="Samad",
            phone_number="+917355463857",
            gender="M",
            verified=True,
            two_factor_enabled=True,
        )

        # 20XX Synthetic Debug account
        self.debug_user = User.objects.create_user(
            enrollment_number="20XXBCSE001",
            username="20XXBCSE001",
            password="Debug@123",
            first_name="Debug",
            last_name="CSE",
            phone_number="+919876543210",
            gender="M",
            verified=True,
            two_factor_enabled=False,
        )

        # Standard real student
        self.student = User.objects.create_user(
            enrollment_number="2024BCSE099",
            username="2024BCSE099",
            password="StudentPass@123",
            first_name="Real",
            last_name="Student",
            phone_number="+919999988888",
            gender="M",
            verified=True,
            two_factor_enabled=True,
        )

    def test_debug_account_bypasses_2fa_on_login(self):
        """Synthetic 20XX accounts must bypass 2FA intercept directly into authenticated state."""
        self.assertTrue(self.debug_user.is_debug_account)
        res = self.client.post(reverse("login"), {
            "username": "20XXBCSE001",
            "password": "Debug@123",
        }, follow=True)

        self.assertRedirects(res, reverse("dashboard"))
        self.assertEqual(int(self.client.session["_auth_user_id"]), self.debug_user.id)

    def test_real_student_with_2fa_intercepted(self):
        """Real student accounts with 2FA enabled must receive OTP and redirect to 2FA verification."""
        self.assertFalse(self.student.is_debug_account)
        res = self.client.post(reverse("login"), {
            "username": "2024BCSE099",
            "password": "StudentPass@123",
        })

        self.assertRedirects(res, reverse("two_factor_verify"))
        self.assertEqual(self.client.session.get("pre_2fa_user_id"), self.student.id)

        # OTP record created
        otp = PhoneOTP.objects.filter(user=self.student, is_used=False, purpose="2FA").first()
        self.assertIsNotNone(otp)

    def test_single_active_session_enforcement(self):
        """Logging in from a new device/browser terminates any prior active session."""
        browser_1 = Client()
        browser_2 = Client()

        # Login on Device 1
        browser_1.post(reverse("login"), {
            "username": "20XXBCSE001",
            "password": "Debug@123",
        })
        key_1 = browser_1.session.session_key
        self.debug_user.refresh_from_db()
        self.assertEqual(self.debug_user.current_session_key, key_1)

        # Login on Device 2
        browser_2.post(reverse("login"), {
            "username": "20XXBCSE001",
            "password": "Debug@123",
        })
        key_2 = browser_2.session.session_key
        self.debug_user.refresh_from_db()
        self.assertEqual(self.debug_user.current_session_key, key_2)
        self.assertNotEqual(key_1, key_2)

        # Device 1 subsequent request must be terminated by SingleSessionMiddleware
        res_device_1 = browser_1.get(reverse("dashboard"))
        self.assertRedirects(res_device_1, reverse("login") + "?next=" + reverse("dashboard"))
        self.assertFalse(browser_1.session.get("_auth_user_id"))

    def test_ten_minute_security_grace_window(self):
        """Security settings modifications within 10 minutes proceed without OTP challenge."""
        self.client.force_login(self.student)
        # Establish active 10-minute grace window in session
        session = self.client.session
        session["security_otp_verified_until"] = (timezone.now() + timedelta(minutes=10)).isoformat()
        session.save()

        # Update password and phone within grace window
        res = self.client.post(reverse("profile", args=[self.student.enrollment_number]), {
            "phone_number": "+918888877777",
            "new_password": "NewSecretPass@123",
            "confirm_password": "NewSecretPass@123",
        }, follow=True)

        self.assertContains(res, "Profile and security settings updated successfully.")
        self.student.refresh_from_db()
        self.assertEqual(self.student.phone_number, "+918888877777")
        self.assertTrue(self.student.check_password("NewSecretPass@123"))

    def test_security_change_requires_otp_when_grace_expired(self):
        """Security settings change with expired grace window must be blocked without valid OTP."""
        self.client.force_login(self.student)
        # Expired grace window
        session = self.client.session
        session["security_otp_verified_until"] = (timezone.now() - timedelta(minutes=5)).isoformat()
        session.save()

        # Attempt to change phone number without OTP
        res = self.client.post(reverse("profile", args=[self.student.enrollment_number]), {
            "phone_number": "+911111122222",
        }, follow=True)

        self.assertContains(res, "Security verification required")
        self.student.refresh_from_db()
        self.assertNotEqual(self.student.phone_number, "+911111122222")

    def test_forgot_password_via_phone_otp(self):
        """Student can reset password self-service via Phone SMS OTP."""
        # Step 1: Request OTP
        res1 = self.client.post(reverse("forgot_password"), {
            "action": "request_otp",
            "enrollment_number": "2024BCSE099",
        })
        self.assertEqual(res1.status_code, 200)
        self.assertEqual(self.client.session.get("reset_user_id"), self.student.id)

        # Generate OTP
        otp, code = create_phone_otp(self.student, purpose="PASSWORD_RESET")

        # Step 2: Submit OTP & new password
        res2 = self.client.post(reverse("forgot_password"), {
            "action": "verify_reset",
            "otp_code": code,
            "new_password": "CompletelyNewPassword123!",
            "confirm_password": "CompletelyNewPassword123!",
        }, follow=True)

        self.assertRedirects(res2, reverse("login"))
        self.student.refresh_from_db()
        self.assertTrue(self.student.check_password("CompletelyNewPassword123!"))

    def test_physical_verification_request_filing_and_admin_resolution(self):
        """Student with lost phone files in-person request; Admin verifies ID card and sets password."""
        # Filing
        res_file = self.client.post(reverse("forgot_password"), {
            "action": "physical_request",
            "enrollment_number": "2024BCSE099",
            "contact_phone": "+917777766666",
            "contact_email": "lostsim@example.com",
            "student_notes": "SIM card lost during transit, presenting ID card at desk",
        }, follow=True)

        self.assertRedirects(res_file, reverse("login"))
        pvr = PhysicalVerificationRequest.objects.get(user=self.student)
        self.assertEqual(pvr.status, "PENDING")

        # Admin Resolution at Operations Desk
        self.client.force_login(self.superaccount)
        res_resolve = self.client.post(reverse("admin_resolve_physical_verification", args=[pvr.id]), {
            "action": "verify_reset_password",
            "new_password": "TempDeskPassword@999",
            "notes": "Student presented official NIT ID card in person",
        }, follow=True)

        self.assertRedirects(res_resolve, reverse("operational_dashboard"))
        pvr.refresh_from_db()
        self.assertEqual(pvr.status, "VERIFIED")
        self.assertEqual(pvr.verified_by, self.superaccount)
        self.student.refresh_from_db()
        self.assertTrue(self.student.check_password("TempDeskPassword@999"))

    def test_soft_delete_account_preserves_trip_history(self):
        """Admin soft-deleting an account closes login but preserves trip log records and reviews."""
        # Create a ride with student participation
        ride = RideRequest.objects.create(
            creator=self.student,
            route="NIT_TO_AIRPORT",
            visibility="MIXED",
            departure_time=timezone.now() + timedelta(days=1),
            total_spots=4,
            status="OPEN",
        )
        participant = RideParticipant.objects.create(
            ride=ride,
            user=self.student,
        )

        self.client.force_login(self.superaccount)
        res_delete = self.client.post(reverse("admin_delete_account", args=[self.student.id]), follow=True)

        self.assertRedirects(res_delete, reverse("operational_dashboard"))
        self.student.refresh_from_db()
        self.assertTrue(self.student.is_deleted)
        self.assertFalse(self.student.is_active)
        self.assertIn("(Closed Account)", self.student.display_name)

        # Ride history is intact and not cascade-deleted
        self.assertTrue(RideRequest.objects.filter(id=ride.id).exists())
        self.assertTrue(RideParticipant.objects.filter(id=participant.id).exists())
