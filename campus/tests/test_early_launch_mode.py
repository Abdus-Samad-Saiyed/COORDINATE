"""Automated tests for Early Launch Mode & Temporary Database Isolation.

Validates:
1. EarlyLaunchDeclarationForm validation, untrusted self-declaration (verified=False), and pending application purge.
2. Self-declaration flow via apply_account view under EARLY_LAUNCH_MODE=True.
3. Fallback to standard physical verification application when EARLY_LAUNCH_MODE=False.
4. COORDINATE policy integration (is_verified_student waivers for untrusted active users).
5. Temporary database routing & isolation settings.
6. Management commands: runserver --early-launch and purge_early_launch.
"""

import os
from unittest.mock import patch
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management import call_command, load_command_class
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from accounts.forms import AccountApplicationForm, EarlyLaunchDeclarationForm
from accounts.models import AccountApplication, AuditEvent
from coordinate.policies import is_verified_student

User = get_user_model()


class EarlyLaunchFormTests(TestCase):
    """Test EarlyLaunchDeclarationForm validation, untrusted status, and persistence."""

    def test_valid_form_submission_creates_untrusted_user(self):
        # Create a pre-existing pending application to verify it gets cleaned up
        AccountApplication.objects.create(
            enrollment_number="2024BCSE901",
            full_name="Pending Student",
            gender="M",
            phone_number="+919876543210",
            email="pending901@nitsri.ac.in",
            approved=False,
        )
        self.assertEqual(AccountApplication.objects.filter(enrollment_number="2024BCSE901").count(), 1)

        form_data = {
            "enrollment_number": "2024BCSE901",
            "full_name": "Zaid Khan",
            "gender": "M",
            "phone_number": "+919876543210",
            "email": "zaid901@nitsri.ac.in",
            "password": "SecurePassword123!",
            "confirm_password": "SecurePassword123!",
        }
        form = EarlyLaunchDeclarationForm(data=form_data)
        self.assertTrue(form.is_valid(), form.errors)

        user = form.save()
        self.assertIsNotNone(user.pk)
        self.assertEqual(user.enrollment_number, "2024BCSE901")
        self.assertEqual(user.first_name, "Zaid")
        self.assertEqual(user.last_name, "Khan")
        self.assertEqual(user.phone_number, "+919876543210")
        self.assertEqual(user.email, "zaid901@nitsri.ac.in")
        # Early access accounts are untrusted
        self.assertFalse(user.verified)
        self.assertTrue(user.is_active)
        self.assertTrue(user.check_password("SecurePassword123!"))

        # Pending application must have been cleaned up
        self.assertEqual(AccountApplication.objects.filter(enrollment_number="2024BCSE901").count(), 0)

    def test_default_institute_email_generated_when_omitted(self):
        form_data = {
            "enrollment_number": "2024BCSE902",
            "full_name": "Sara Ali",
            "gender": "F",
            "phone_number": "9876543211",
            "email": "",
            "password": "SecurePassword123!",
            "confirm_password": "SecurePassword123!",
        }
        form = EarlyLaunchDeclarationForm(data=form_data)
        self.assertTrue(form.is_valid(), form.errors)
        user = form.save()
        self.assertEqual(user.email, "2024bcse902@nitsri.ac.in")
        self.assertEqual(user.gender, "F")
        self.assertFalse(user.verified)

    def test_invalid_enrollment_format_rejected(self):
        form_data = {
            "enrollment_number": "NOTANENROLL",
            "full_name": "Invalid Student",
            "gender": "M",
            "phone_number": "9876543210",
            "password": "SecurePassword123!",
            "confirm_password": "SecurePassword123!",
        }
        form = EarlyLaunchDeclarationForm(data=form_data)
        self.assertFalse(form.is_valid())
        self.assertIn("enrollment_number", form.errors)

    def test_duplicate_enrollment_rejected(self):
        User.objects.create_user(
            enrollment_number="2024BCSE903",
            username="2024BCSE903",
            password="ExistingPass123!",
        )
        form_data = {
            "enrollment_number": "2024BCSE903",
            "full_name": "Duplicate Student",
            "gender": "M",
            "phone_number": "9876543210",
            "password": "SecurePassword123!",
            "confirm_password": "SecurePassword123!",
        }
        form = EarlyLaunchDeclarationForm(data=form_data)
        self.assertFalse(form.is_valid())
        self.assertIn("enrollment_number", form.errors)

    def test_password_mismatch_rejected(self):
        form_data = {
            "enrollment_number": "2024BCSE904",
            "full_name": "Mismatch Student",
            "gender": "M",
            "phone_number": "9876543210",
            "password": "SecurePassword123!",
            "confirm_password": "DifferentPassword123!",
        }
        form = EarlyLaunchDeclarationForm(data=form_data)
        self.assertFalse(form.is_valid())
        self.assertIn("confirm_password", form.errors)


class EarlyLaunchViewTests(TestCase):
    """Test HTTP views and templates under Early Launch Mode."""

    def setUp(self):
        self.client = Client()

    @override_settings(EARLY_LAUNCH_MODE=True)
    def test_apply_view_get_in_early_launch_mode(self):
        response = self.client.get(reverse("apply_account"))
        self.assertEqual(response.status_code, 200)
        self.assertIsInstance(response.context["form"], EarlyLaunchDeclarationForm)
        self.assertTrue(response.context.get("early_launch_mode"))
        self.assertContains(response, "TEMPORARY EARLY ACCESS (UNTRUSTED)")
        self.assertContains(response, "Temporary Student Registration")
        self.assertNotContains(response, "Designated Application Approvers")

    @override_settings(EARLY_LAUNCH_MODE=True)
    def test_apply_view_post_creates_and_logs_in_user(self):
        post_data = {
            "enrollment_number": "2024BCSE905",
            "full_name": "Tariq Ahmad",
            "gender": "M",
            "phone_number": "+919876543210",
            "email": "tariq905@nitsri.ac.in",
            "password": "SecurePassword123!",
            "confirm_password": "SecurePassword123!",
        }
        response = self.client.post(reverse("apply_account"), data=post_data, follow=True)
        self.assertRedirects(response, reverse("dashboard"))

        # Verify user was created with active, untrusted status (verified=False)
        user = User.objects.get(enrollment_number="2024BCSE905")
        self.assertFalse(user.verified)
        self.assertTrue(user.is_active)

        # Verify audit log was recorded
        audit = AuditEvent.objects.filter(
            event_type="EARLY_LAUNCH_SELF_DECLARATION",
            actor_enrollment="2024BCSE905",
        ).first()
        self.assertIsNotNone(audit)
        self.assertIn("2024BCSE905", audit.description)

        # Verify client is actively authenticated
        self.assertEqual(int(self.client.session["_auth_user_id"]), user.pk)

    @override_settings(EARLY_LAUNCH_MODE=False)
    def test_apply_view_get_in_standard_mode(self):
        response = self.client.get(reverse("apply_account"))
        self.assertEqual(response.status_code, 200)
        self.assertIsInstance(response.context["form"], AccountApplicationForm)
        self.assertFalse(response.context.get("early_launch_mode", False))
        self.assertContains(response, "STUDENT REGISTRATION")
        self.assertContains(response, "Apply for Verification")
        self.assertNotContains(response, "TEMPORARY EARLY ACCESS")

    @override_settings(EARLY_LAUNCH_MODE=True)
    def test_landing_page_renders_early_launch_banners_and_cta(self):
        response = self.client.get(reverse("landing"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Early Launch Mode Active")
        self.assertContains(response, "Instant Student Access")
        self.assertContains(response, "End-of-Term Temporary Launch")

    @override_settings(EARLY_LAUNCH_MODE=False)
    def test_landing_page_renders_standard_banners_and_cta(self):
        response = self.client.get(reverse("landing"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Apply for Verification")
        self.assertNotContains(response, "Instant Student Access")

    @override_settings(EARLY_LAUNCH_MODE=True)
    def test_dashboard_displays_untrusted_badge_for_early_access_user(self):
        user = User.objects.create_user(
            enrollment_number="2024BCSE906",
            username="2024BCSE906",
            password="SecurePassword123!",
            verified=False,
            is_active=True,
        )
        self.client.force_login(user)
        response = self.client.get(reverse("dashboard"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Untrusted &bull; Early Access")
        self.assertContains(response, "Temporary Account:")

    @override_settings(EARLY_LAUNCH_MODE=True)
    def test_profile_displays_untrusted_badge(self):
        user = User.objects.create_user(
            enrollment_number="2024BCSE907",
            username="2024BCSE907",
            password="SecurePassword123!",
            verified=False,
            is_active=True,
        )
        self.client.force_login(user)
        response = self.client.get(reverse("profile", kwargs={"enrollment_number": "2024BCSE907"}))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Untrusted &bull; Early Access")


class EarlyLaunchPolicyTests(TestCase):
    """Test COORDINATE verification policies under early launch."""

    def setUp(self):
        self.unverified_user = User.objects.create_user(
            enrollment_number="2024BCSE910",
            username="2024BCSE910",
            password="SecurePassword123!",
            verified=False,
            is_active=True,
        )
        self.verified_user = User.objects.create_user(
            enrollment_number="2024BCSE911",
            username="2024BCSE911",
            password="SecurePassword123!",
            verified=True,
            is_active=True,
        )
        self.inactive_user = User.objects.create_user(
            enrollment_number="2024BCSE912",
            username="2024BCSE912",
            password="SecurePassword123!",
            verified=True,
            is_active=False,
        )

    def test_is_verified_student_under_standard_mode(self):
        with override_settings(EARLY_LAUNCH_MODE=False):
            self.assertFalse(is_verified_student(self.unverified_user))
            self.assertTrue(is_verified_student(self.verified_user))
            self.assertFalse(is_verified_student(self.inactive_user))

    def test_is_verified_student_under_early_launch_mode(self):
        with override_settings(EARLY_LAUNCH_MODE=True):
            # Untrusted active student is granted temporary coordination privileges
            self.assertTrue(is_verified_student(self.unverified_user))
            self.assertTrue(is_verified_student(self.verified_user))
            # Inactive student is still barred
            self.assertFalse(is_verified_student(self.inactive_user))


class EarlyLaunchManagementCommandTests(TestCase):
    """Test manage.py runserver and purge_early_launch commands."""

    def test_runserver_command_argument_parsing(self):
        cmd = load_command_class("accounts", "runserver")
        parser = cmd.create_parser("manage.py", "runserver")
        parsed = parser.parse_args(["--early-launch", "0.0.0.0:8000"])
        self.assertTrue(parsed.early_launch)
        self.assertEqual(parsed.addrport, "0.0.0.0:8000")

    def test_purge_early_launch_command(self):
        # Create a mock temporary db file
        mock_path = settings.BASE_DIR / "test_temp_early_access.sqlite3"
        with open(mock_path, "w") as f:
            f.write("mock db content")
        self.assertTrue(os.path.exists(mock_path))

        with override_settings(EARLY_LAUNCH_DB_PATH=mock_path):
            call_command("purge_early_launch", force=True)
            self.assertFalse(os.path.exists(mock_path))
