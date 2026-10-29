"""Stage 8 verification tests:
- AuditEvent append-only immutability (instance and bulk queryset protection)
- Health probe minimal liveness without public information leakage
"""

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

from accounts.models import AuditEvent

User = get_user_model()


class Stage8AuditIntegrityAndHealthTests(TestCase):
    def setUp(self):
        self.client = Client()

        self.event = AuditEvent.objects.create(
            event_type="LOGIN_SUCCESS",
            actor_enrollment="2024BCSE901",
            description="User logged in securely.",
        )

        self.staff_user = User.objects.create_user(
            enrollment_number="2024BCSE999",
            username="2024BCSE999",
            password="SecurePassword123!",
            first_name="Staff",
            last_name="Member",
            gender="M",
            phone_number="+919876543999",
            email="staff999@nitsri.ac.in",
            verified=True,
            is_staff=True,
        )

    def test_audit_event_instance_immutability(self):
        """Individual AuditEvent instances cannot be modified or deleted."""
        with self.assertRaises(PermissionError):
            self.event.delete()

        with self.assertRaises(PermissionError):
            self.event.description = "Tampered description"
            self.event.save()

    def test_audit_event_bulk_queryset_immutability(self):
        """Bulk updates and deletes on AuditEvent querysets are strictly blocked."""
        with self.assertRaises(PermissionError):
            AuditEvent.objects.filter(id=self.event.id).update(description="Bulk tampered")

        with self.assertRaises(PermissionError):
            AuditEvent.objects.filter(id=self.event.id).delete()

        # Verify record remains unchanged in database
        self.event.refresh_from_db()
        self.assertEqual(self.event.description, "User logged in securely.")

    def test_health_check_minimal_liveness_probe(self):
        """Unauthenticated /health/ probe returns minimal liveness without internal telemetry."""
        resp = self.client.get(reverse("health_check"))
        self.assertEqual(resp.status_code, 200)
        data = resp.json()

        # Contains core liveness indicators
        self.assertEqual(data.get("status"), "healthy")
        self.assertIn("database", data)
        self.assertIn("cache", data)
        self.assertIn("timestamp", data)

        # Public probes do NOT leak version, telemetry, or internal stack traces
        self.assertNotIn("traffic_telemetry", data)
        self.assertNotIn("version", data)
        self.assertNotIn("error", data)

    def test_health_check_staff_telemetry(self):
        """Authenticated staff members can view operational telemetry on /health/."""
        self.client.force_login(self.staff_user)
        resp = self.client.get(reverse("health_check"))
        self.assertEqual(resp.status_code, 200)
        data = resp.json()

        self.assertIn("traffic_telemetry", data)
        self.assertIn("version", data)
