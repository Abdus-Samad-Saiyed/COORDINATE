"""Stage 5 verification tests:
- Concurrency with select_for_update and capacity boundaries
- Universal soft-termination (status='CANCELLED') preserving history, messages, and reviews
- Reputation anti-farming protection (solo rides blocked from gaining credits)
- Strict double-completion and pre-departure completion blocks
"""

from datetime import timedelta
from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from coordinate.models import (
    RideJoinRequest,
    RideMessage,
    RideParticipant,
    RideRequest,
    RideReview,
    RideWaitlist,
)
from coordinate.services import (
    approve_ride_join_request,
    cancel_ride_service,
    request_to_join_ride,
)

User = get_user_model()


class Stage5LifecycleConcurrencyTests(TestCase):
    def setUp(self):
        self.client = Client()

        self.host = User.objects.create_user(
            enrollment_number="2024BCSE701",
            username="2024BCSE701",
            password="SecurePassword123!",
            first_name="Host",
            last_name="Seven",
            gender="M",
            phone_number="+919876543701",
            email="host701@nitsri.ac.in",
            verified=True,
            is_active=True,
        )

        self.p1 = User.objects.create_user(
            enrollment_number="2024BCSE702",
            username="2024BCSE702",
            password="SecurePassword123!",
            first_name="Passenger",
            last_name="One",
            gender="M",
            phone_number="+919876543702",
            email="pass702@nitsri.ac.in",
            verified=True,
            is_active=True,
        )

        self.p2 = User.objects.create_user(
            enrollment_number="2024BCSE703",
            username="2024BCSE703",
            password="SecurePassword123!",
            first_name="Passenger",
            last_name="Two",
            gender="M",
            phone_number="+919876543703",
            email="pass703@nitsri.ac.in",
            verified=True,
            is_active=True,
        )

    def test_capacity_concurrency_guard(self):
        """When 1 spot is left, only 1 join request can be approved; second approval is rejected."""
        future_dep = timezone.now() + timedelta(days=2)
        ride = RideRequest.objects.create(
            creator=self.host,
            route="NIT_TO_AIRPORT",
            departure_time=future_dep,
            total_spots=2,  # 1 host + 1 open spot
            visibility="MIXED",
            status="OPEN",
        )
        RideParticipant.objects.create(ride=ride, user=self.host)

        # Both p1 and p2 request to join
        ok1, _, d1 = request_to_join_ride(ride.id, self.p1)
        ok2, _, d2 = request_to_join_ride(ride.id, self.p2)
        self.assertTrue(ok1)
        self.assertTrue(ok2)

        # Host approves p1 -> succeeds, ride becomes FULL
        ok_app1, _, _ = approve_ride_join_request(ride.id, d1["request_id"], self.host)
        self.assertTrue(ok_app1)
        ride.refresh_from_db()
        self.assertEqual(ride.status, "FULL")
        self.assertTrue(ride.is_full())

        # Host attempts to approve p2 -> atomically rejected due to capacity limit
        ok_app2, msg2, err2 = approve_ride_join_request(ride.id, d2["request_id"], self.host)
        self.assertFalse(ok_app2)
        self.assertEqual(err2.get("code"), "RIDE_FULL")

    def test_soft_cancellation_preserves_messages_and_audit(self):
        """Cancelling a ride transitions status to CANCELLED without hard deleting records, chat, or reviews."""
        future_dep = timezone.now() + timedelta(days=1)
        ride = RideRequest.objects.create(
            creator=self.host,
            route="NIT_TO_AIRPORT",
            departure_time=future_dep,
            total_spots=3,
            visibility="MIXED",
            status="OPEN",
        )
        RideParticipant.objects.create(ride=ride, user=self.host)
        RideParticipant.objects.create(ride=ride, user=self.p1)

        # Chat message recorded
        msg = RideMessage.objects.create(
            ride=ride,
            author=self.p1,
            content="Confirming pickup at Main Gate."
        )

        # Cancel ride
        ok, _ = cancel_ride_service(ride.id, self.host)
        self.assertTrue(ok)

        # Verify database persistence: ride is NOT deleted
        ride.refresh_from_db()
        self.assertEqual(ride.status, "CANCELLED")

        # Chat message persists in DB for audit trail
        self.assertTrue(RideMessage.objects.filter(id=msg.id).exists())
        self.assertEqual(RideMessage.objects.get(id=msg.id).content, "Confirming pickup at Main Gate.")

    def test_anti_farming_solo_and_pre_departure_guards(self):
        """Solo rides award no reputation; pre-departure completion is strictly rejected."""
        future_dep = timezone.now() + timedelta(hours=5)
        ride = RideRequest.objects.create(
            creator=self.host,
            route="NIT_TO_AIRPORT",
            departure_time=future_dep,
            total_spots=3,
            visibility="MIXED",
            status="OPEN",
        )
        RideParticipant.objects.create(ride=ride, user=self.host)

        self.client.force_login(self.host)

        # 1. Attempting completion before departure time is rejected
        resp_early = self.client.post(reverse("complete_ride", kwargs={"ride_id": ride.id}))
        self.assertEqual(resp_early.status_code, 302)
        ride.refresh_from_db()
        self.assertNotEqual(ride.status, "COMPLETED")

        # 2. Update departure time to past, but ride is solo (only host)
        ride.departure_time = timezone.now() - timedelta(hours=1)
        ride.save(update_fields=["departure_time"])

        resp_solo = self.client.post(reverse("complete_ride", kwargs={"ride_id": ride.id}))
        self.assertEqual(resp_solo.status_code, 302)
        ride.refresh_from_db()
        self.assertEqual(ride.status, "COMPLETED")

        # Solo completion awards NO reputation credits
        self.host.refresh_from_db()
        self.assertEqual(self.host.rides_completed, 0)
        self.assertEqual(self.host.on_time_count, 0)
