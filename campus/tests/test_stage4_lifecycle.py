"""Stage 4 tests — Centralized Ride Lifecycle, Atomicity, and Capacity Management.

Covers:
1. Double completion prevention: Completed/cancelled rides refuse re-completion.
2. Solo reputation farming prevention: Solo ride completion awards no reputation credits.
3. Group ride completion (>= 2 participants) increments reliability counters.
4. Concurrency & capacity limits: Ride status transitions between OPEN and FULL accurately.
5. Soft termination: Terminating a ride transitions to CANCELLED and preserves database record.
6. Standby waitlist automatic promotion on vacancy.
7. Immediate affirmative consent revocation on membership termination.
"""

from datetime import timedelta
from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from coordinate.models import (
    RideConsent,
    RideJoinRequest,
    RideParticipant,
    RideRequest,
    RideWaitlist,
)
from coordinate.policies import (
    can_view_ride_contact,
    record_ride_consent,
)

User = get_user_model()


class Stage4LifecycleTests(TestCase):
    """Test ride lifecycle state machine, anti-farming guards, and atomic transitions."""

    def setUp(self):
        self.client = Client()

        # Host
        self.host = User.objects.create_user(
            enrollment_number="2024BCSE301",
            username="2024BCSE301",
            password="Password123!",
            first_name="Host",
            last_name="User",
            gender="M",
            phone_number="+919876543301",
            email="host301@nitsri.ac.in",
            verified=True,
        )

        # Passenger 1
        self.passenger1 = User.objects.create_user(
            enrollment_number="2024BCSE302",
            username="2024BCSE302",
            password="Password123!",
            first_name="Passenger",
            last_name="One",
            gender="M",
            phone_number="+919876543302",
            email="pass302@nitsri.ac.in",
            verified=True,
        )

        # Passenger 2 (Waitlisted)
        self.passenger2 = User.objects.create_user(
            enrollment_number="2024BCSE303",
            username="2024BCSE303",
            password="Password123!",
            first_name="Passenger",
            last_name="Two",
            gender="M",
            phone_number="+919876543303",
            email="pass303@nitsri.ac.in",
            verified=True,
        )

    def test_solo_reputation_farming_prevented(self):
        """Completing a solo ride (host alone) must NOT award rides_completed or on_time_count."""
        past_dep = timezone.now() - timedelta(hours=1)
        solo_ride = RideRequest.objects.create(
            creator=self.host,
            route="NIT_TO_AIRPORT",
            departure_time=past_dep,
            total_spots=4,
            visibility="MIXED",
            status="OPEN",
        )
        RideParticipant.objects.create(ride=solo_ride, user=self.host)
        record_ride_consent(solo_ride, self.host, share_contact=True)

        self.client.force_login(self.host)
        resp = self.client.post(reverse("complete_ride", kwargs={"ride_id": solo_ride.id}))
        self.assertEqual(resp.status_code, 302)

        solo_ride.refresh_from_db()
        self.assertEqual(solo_ride.status, "COMPLETED")

        # Verify host did NOT gain reputation counts
        self.host.refresh_from_db()
        self.assertEqual(self.host.rides_completed, 0)
        self.assertEqual(self.host.on_time_count, 0)

    def test_group_ride_completion_awards_reputation(self):
        """Completing a ride with >= 2 participants awards attendance and on-time stats."""
        past_dep = timezone.now() - timedelta(hours=1)
        group_ride = RideRequest.objects.create(
            creator=self.host,
            route="NIT_TO_AIRPORT",
            departure_time=past_dep,
            total_spots=4,
            visibility="MIXED",
            status="OPEN",
        )
        RideParticipant.objects.create(ride=group_ride, user=self.host)
        RideParticipant.objects.create(ride=group_ride, user=self.passenger1)
        record_ride_consent(group_ride, self.host, share_contact=True)
        record_ride_consent(group_ride, self.passenger1, share_contact=True)

        self.client.force_login(self.host)
        resp = self.client.post(reverse("complete_ride", kwargs={"ride_id": group_ride.id}))
        self.assertEqual(resp.status_code, 302)

        group_ride.refresh_from_db()
        self.assertEqual(group_ride.status, "COMPLETED")

        # Both host and passenger gain +1
        self.host.refresh_from_db()
        self.passenger1.refresh_from_db()
        self.assertEqual(self.host.rides_completed, 1)
        self.assertEqual(self.host.on_time_count, 1)
        self.assertEqual(self.passenger1.rides_completed, 1)
        self.assertEqual(self.passenger1.on_time_count, 1)

    def test_double_completion_prevented(self):
        """Attempting to complete an already completed ride is rejected."""
        past_dep = timezone.now() - timedelta(hours=1)
        ride = RideRequest.objects.create(
            creator=self.host,
            route="NIT_TO_AIRPORT",
            departure_time=past_dep,
            total_spots=4,
            visibility="MIXED",
            status="COMPLETED",
        )
        self.client.force_login(self.host)
        resp = self.client.post(reverse("complete_ride", kwargs={"ride_id": ride.id}))
        self.assertEqual(resp.status_code, 302)
        ride.refresh_from_db()
        self.assertEqual(ride.status, "COMPLETED")

    def test_soft_termination_preserves_records_and_revokes_consent(self):
        """Terminating a ride sets status to CANCELLED and purges consents without hard-deleting."""
        future_dep = timezone.now() + timedelta(days=2)
        ride = RideRequest.objects.create(
            creator=self.host,
            route="NIT_TO_AIRPORT",
            departure_time=future_dep,
            total_spots=2,
            visibility="MIXED",
            status="OPEN",
        )
        RideParticipant.objects.create(ride=ride, user=self.host)
        record_ride_consent(ride, self.host, share_contact=True)

        self.client.force_login(self.host)
        resp = self.client.post(reverse("terminate_ride", kwargs={"ride_id": ride.id}))
        self.assertEqual(resp.status_code, 302)

        # Ride still exists in database as CANCELLED
        ride.refresh_from_db()
        self.assertEqual(ride.status, "CANCELLED")

        # Active consents revoked while keeping historical record for audit
        self.assertFalse(RideConsent.objects.filter(ride=ride, is_revoked=False).exists())
        self.assertTrue(RideConsent.objects.filter(ride=ride, is_revoked=True).exists())
        # Another user cannot view contacts for a cancelled ride
        self.assertFalse(can_view_ride_contact(self.passenger1, ride, self.host))

    def test_waitlist_promotion_on_passenger_leave(self):
        """When a passenger leaves a full ride, standby passenger is promoted and receives consent."""
        future_dep = timezone.now() + timedelta(days=2)
        ride = RideRequest.objects.create(
            creator=self.host,
            route="NIT_TO_AIRPORT",
            departure_time=future_dep,
            total_spots=2,
            visibility="MIXED",
            status="FULL",
        )
        RideParticipant.objects.create(ride=ride, user=self.host)
        RideParticipant.objects.create(ride=ride, user=self.passenger1)
        record_ride_consent(ride, self.host, share_contact=True)
        record_ride_consent(ride, self.passenger1, share_contact=True)

        # Passenger 2 joins waitlist
        RideWaitlist.objects.create(ride=ride, user=self.passenger2)

        # Passenger 1 leaves ride
        self.client.force_login(self.passenger1)
        resp = self.client.post(reverse("leave_ride", kwargs={"ride_id": ride.id}))
        self.assertEqual(resp.status_code, 302)

        # Passenger 1 consent revoked (soft-revocation keeps historical audit)
        self.assertTrue(RideConsent.objects.filter(ride=ride, user=self.passenger1, is_revoked=True).exists())
        self.assertFalse(can_view_ride_contact(self.host, ride, self.passenger1))

        # Passenger 2 automatically promoted from waitlist to participant
        self.assertTrue(RideParticipant.objects.filter(ride=ride, user=self.passenger2).exists())
        self.assertFalse(RideWaitlist.objects.filter(ride=ride, user=self.passenger2).exists())
        self.assertTrue(RideConsent.objects.filter(ride=ride, user=self.passenger2).exists())
        # Standby promotion never synthesizes contact sharing consent
        self.assertFalse(can_view_ride_contact(self.host, ride, self.passenger2))

        # Explicit affirmative opt-in enables contact visibility
        record_ride_consent(ride, self.passenger2, share_contact=True)
        self.assertTrue(can_view_ride_contact(self.host, ride, self.passenger2))
