"""Stage 4 verification tests:
- Field-level visibility allowlists (Directory vs Profile vs Contacts)
- Ride-specific contact coordination window (departure + 2 hours max)
- Instant contact closure on completion or cancellation
- Mutual affirmative consent requirement for ride contact disclosure
"""

import json
from datetime import timedelta
from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import Friendship
from coordinate.models import (
    RideConsent,
    RideParticipant,
    RideRequest,
)
from coordinate.policies import (
    can_view_profile_field,
    can_view_ride_contact,
    can_view_student_directory,
    record_ride_consent,
)
from campus.api.serializers import serialize_ride_detail

User = get_user_model()


class Stage4FieldVisibilityAndLifetimeTests(TestCase):
    def setUp(self):
        self.client = Client()

        self.student_a = User.objects.create_user(
            enrollment_number="2024BCSE601",
            username="2024BCSE601",
            password="SecurePassword123!",
            first_name="Alice",
            last_name="Alpha",
            gender="F",
            phone_number="+919876543601",
            email="alice601@nitsri.ac.in",
            verified=True,
            is_active=True,
        )

        self.student_b = User.objects.create_user(
            enrollment_number="2024BCSE602",
            username="2024BCSE602",
            password="SecurePassword123!",
            first_name="Bob",
            last_name="Beta",
            gender="M",
            phone_number="+919876543602",
            email="bob602@nitsri.ac.in",
            verified=True,
            is_active=True,
        )

        self.student_c = User.objects.create_user(
            enrollment_number="2024BCSE603",
            username="2024BCSE603",
            password="SecurePassword123!",
            first_name="Charlie",
            last_name="Gamma",
            gender="M",
            phone_number="+919876543603",
            email="charlie603@nitsri.ac.in",
            verified=True,
            is_active=True,
        )

        self.unverified_user = User.objects.create_user(
            enrollment_number="2024BCSE604",
            username="2024BCSE604",
            password="SecurePassword123!",
            first_name="David",
            last_name="Delta",
            gender="M",
            phone_number="+919876543604",
            email="david604@nitsri.ac.in",
            verified=False,
            is_active=True,
        )

        self.staff_user = User.objects.create_user(
            enrollment_number="2024BCSE999",
            username="2024BCSE999",
            password="SecurePassword123!",
            first_name="Staff",
            last_name="Admin",
            gender="M",
            phone_number="+919876543999",
            email="staff999@nitsri.ac.in",
            verified=True,
            is_staff=True,
        )

    def test_directory_access_gating_and_field_allowlist(self):
        """Student directory is accessible only to verified students and staff; hides sensitive fields from strangers."""
        self.assertTrue(can_view_student_directory(self.student_a))
        self.assertTrue(can_view_student_directory(self.staff_user))
        self.assertFalse(can_view_student_directory(self.unverified_user))
        self.assertFalse(can_view_student_directory(None))

        # Public institutional profile fields are visible
        for f in ("full_name", "enrollment_number", "gender", "branch", "degree"):
            self.assertTrue(can_view_profile_field(self.student_a, self.student_b, f))

        # Contact fields are strictly hidden between non-friends
        self.assertFalse(can_view_profile_field(self.student_a, self.student_b, "phone_number"))
        self.assertFalse(can_view_profile_field(self.student_a, self.student_b, "email"))

        # Once friends, contact fields become visible
        Friendship.objects.create(user1=self.student_a, user2=self.student_b)
        self.assertTrue(can_view_profile_field(self.student_a, self.student_b, "phone_number"))
        self.assertTrue(can_view_profile_field(self.student_a, self.student_b, "email"))

        # Staff can view regardless of friendship
        self.assertTrue(can_view_profile_field(self.staff_user, self.student_b, "phone_number"))

    def test_ride_contact_coordination_window_and_lifetime(self):
        """Contact details are visible to confirmed participants with mutual consent during trip + 2h coordination window only."""
        now = timezone.now()
        ride = RideRequest.objects.create(
            creator=self.student_a,
            route="NIT_TO_AIRPORT",
            departure_time=now + timedelta(hours=3),
            total_spots=3,
            visibility="MIXED",
            status="OPEN",
        )
        RideParticipant.objects.create(ride=ride, user=self.student_a)
        RideParticipant.objects.create(ride=ride, user=self.student_b)

        # Before mutual consent is granted, neither can view
        record_ride_consent(ride, self.student_a, disclose_identity=True, share_contact=True)
        record_ride_consent(ride, self.student_b, disclose_identity=True, share_contact=False)
        self.assertFalse(can_view_ride_contact(self.student_a, ride, self.student_b))
        self.assertFalse(can_view_ride_contact(self.student_b, ride, self.student_a))

        # Both grant consent
        record_ride_consent(ride, self.student_b, disclose_identity=True, share_contact=True)
        self.assertTrue(can_view_ride_contact(self.student_a, ride, self.student_b))
        self.assertTrue(can_view_ride_contact(self.student_b, ride, self.student_a))

        # Serializer includes phone number when authorized
        serialized = serialize_ride_detail(ride, request_user=self.student_a)
        b_serialized = next(p for p in serialized["participants"] if p["enrollment_number"] == self.student_b.enrollment_number)
        self.assertEqual(b_serialized.get("phone_number"), self.student_b.phone_number)

        # 1 hour after departure (within 2-hour post-departure window): contacts still accessible
        ride.departure_time = now - timedelta(hours=1)
        ride.save(update_fields=["departure_time"])
        self.assertTrue(can_view_ride_contact(self.student_a, ride, self.student_b))

        # 2 hours + 5 minutes after departure: coordination window closed
        ride.departure_time = now - timedelta(hours=2, minutes=5)
        ride.save(update_fields=["departure_time"])
        self.assertFalse(can_view_ride_contact(self.student_a, ride, self.student_b))

        # Serializer redacts contact details once window expired
        serialized_expired = serialize_ride_detail(ride, request_user=self.student_a)
        b_expired = next(p for p in serialized_expired["participants"] if p["enrollment_number"] == self.student_b.enrollment_number)
        self.assertNotIn("phone_number", b_expired)
        self.assertNotIn("email", b_expired)

    def test_instant_contact_closure_on_complete_and_cancel(self):
        """When ride transitions to COMPLETED or CANCELLED, contacts are immediately hidden regardless of timestamp."""
        now = timezone.now()
        ride = RideRequest.objects.create(
            creator=self.student_a,
            route="NIT_TO_AIRPORT",
            departure_time=now + timedelta(hours=2),
            total_spots=2,
            visibility="MIXED",
            status="OPEN",
        )
        RideParticipant.objects.create(ride=ride, user=self.student_a)
        RideParticipant.objects.create(ride=ride, user=self.student_b)
        record_ride_consent(ride, self.student_a, disclose_identity=True, share_contact=True)
        record_ride_consent(ride, self.student_b, disclose_identity=True, share_contact=True)

        self.assertTrue(can_view_ride_contact(self.student_a, ride, self.student_b))

        # 1. Complete ride -> contacts immediately inaccessible
        ride.status = "COMPLETED"
        ride.save(update_fields=["status"])
        self.assertFalse(can_view_ride_contact(self.student_a, ride, self.student_b))

        # 2. Cancel ride -> contacts immediately inaccessible
        ride.status = "CANCELLED"
        ride.save(update_fields=["status"])
        self.assertFalse(can_view_ride_contact(self.student_a, ride, self.student_b))

    def test_non_participant_never_receives_contacts(self):
        """A user who is not a confirmed participant in the ride cannot see contact details even if participants opted in."""
        now = timezone.now()
        ride = RideRequest.objects.create(
            creator=self.student_a,
            route="NIT_TO_AIRPORT",
            departure_time=now + timedelta(hours=2),
            total_spots=3,
            visibility="MIXED",
            status="OPEN",
        )
        RideParticipant.objects.create(ride=ride, user=self.student_a)
        record_ride_consent(ride, self.student_a, disclose_identity=True, share_contact=True)

        # Student C is not in the ride
        self.assertFalse(can_view_ride_contact(self.student_c, ride, self.student_a))
        detail = serialize_ride_detail(ride, request_user=self.student_c)
        host_entry = next(p for p in detail["participants"] if p["enrollment_number"] == self.student_a.enrollment_number)
        self.assertNotIn("phone_number", host_entry)
        self.assertNotIn("email", host_entry)
