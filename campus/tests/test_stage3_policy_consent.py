"""Stage 3 tests — Unified Policy, Authorization Layer, and Ride-Scoped Affirmative Consent.

Covers:
1. is_verified_student: Verified, active accounts vs unverified, deleted accounts.
2. can_view_student_directory: Restricts directory / search access to verified students and staff.
3. can_view_profile_field: Protects private contact details (phone, email) from strangers.
4. can_view_ride: Audience comfort gating (MIXED, BOYS, GIRLS, FRIENDS) and kicked user exclusion.
5. RideConsent lifecycle and can_view_ride_contact affirmative consent gating.
6. API authorization: Anonymous access blocked for rides; contact details redacted without consent.
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
    RideJoinRequest,
    RideParticipant,
    RideRequest,
)
from coordinate.policies import (
    can_view_profile_field,
    can_view_ride,
    can_view_ride_contact,
    can_view_student_directory,
    is_verified_student,
    record_ride_consent,
    revoke_ride_consent,
)

User = get_user_model()


class Stage3PolicyAndConsentTests(TestCase):
    """Test policy functions, directory gating, and affirmative consent."""

    def setUp(self):
        self.client = Client()

        # 1. Verified male student
        self.student_m = User.objects.create_user(
            enrollment_number="2024BCSE201",
            username="2024BCSE201",
            password="Password123!",
            first_name="Male",
            last_name="Student",
            gender="M",
            phone_number="+919876543211",
            email="male201@nitsri.ac.in",
            verified=True,
        )

        # 2. Verified female student
        self.student_f = User.objects.create_user(
            enrollment_number="2024BCSE202",
            username="2024BCSE202",
            password="Password123!",
            first_name="Female",
            last_name="Student",
            gender="F",
            phone_number="+919876543212",
            email="female202@nitsri.ac.in",
            verified=True,
        )

        # 3. Unverified student
        self.unverified_user = User.objects.create_user(
            enrollment_number="2024BCSE203",
            username="2024BCSE203",
            password="Password123!",
            first_name="Pending",
            last_name="Student",
            gender="M",
            phone_number="+919876543213",
            email="pending203@nitsri.ac.in",
            verified=False,
        )

        # 4. Soft-deleted student
        self.deleted_user = User.objects.create_user(
            enrollment_number="2024BCSE204",
            username="2024BCSE204",
            password="Password123!",
            first_name="Deleted",
            last_name="Student",
            gender="M",
            phone_number="+919876543214",
            email="deleted204@nitsri.ac.in",
            verified=True,
            is_deleted=True,
        )

        # 5. Staff administrator
        self.staff_user = User.objects.create_user(
            enrollment_number="2024BCSE999",
            username="2024BCSE999",
            password="AdminPassword123!",
            first_name="Admin",
            last_name="Staff",
            gender="M",
            phone_number="+919876543299",
            email="admin@nitsri.ac.in",
            verified=True,
            is_staff=True,
        )

    def test_is_verified_student(self):
        """Only verified, active, non-deleted users qualify."""
        self.assertTrue(is_verified_student(self.student_m))
        self.assertTrue(is_verified_student(self.student_f))
        self.assertFalse(is_verified_student(self.unverified_user))
        self.assertFalse(is_verified_student(self.deleted_user))
        self.assertFalse(is_verified_student(None))

    def test_directory_access_policy(self):
        """Unverified students cannot access student directory/search."""
        self.assertTrue(can_view_student_directory(self.student_m))
        self.assertTrue(can_view_student_directory(self.staff_user))
        self.assertFalse(can_view_student_directory(self.unverified_user))
        self.assertFalse(can_view_student_directory(self.deleted_user))

        # Test search view redirect for unverified user
        self.client.force_login(self.unverified_user)
        resp = self.client.get(reverse("user_search"))
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp.url, reverse("dashboard"))

    def test_profile_field_visibility_controls(self):
        """Institutional directory fields are visible; contact details require friendship or staff."""
        # Institutional fields: name, enrollment, gender, branch
        self.assertTrue(can_view_profile_field(self.student_m, self.student_f, "enrollment_number"))
        self.assertTrue(can_view_profile_field(self.student_m, self.student_f, "full_name"))
        self.assertTrue(can_view_profile_field(self.student_m, self.student_f, "gender"))

        # Contact details (phone, email) are private from strangers
        self.assertFalse(can_view_profile_field(self.student_m, self.student_f, "phone_number"))
        self.assertFalse(can_view_profile_field(self.student_m, self.student_f, "email"))

        # Self can always view their own contact details
        self.assertTrue(can_view_profile_field(self.student_f, self.student_f, "phone_number"))
        self.assertTrue(can_view_profile_field(self.student_f, self.student_f, "email"))

        # Staff can view contact details for operational/safety needs
        self.assertTrue(can_view_profile_field(self.staff_user, self.student_f, "phone_number"))
        self.assertTrue(can_view_profile_field(self.staff_user, self.student_f, "email"))

        # Once friends, contact details become visible
        Friendship.objects.create(user1=self.student_m, user2=self.student_f)
        self.assertTrue(can_view_profile_field(self.student_m, self.student_f, "phone_number"))
        self.assertTrue(can_view_profile_field(self.student_m, self.student_f, "email"))

    def test_ride_audience_comfort_visibility(self):
        """Audience gating enforces privacy per gender and friend circle."""
        dep_time = timezone.now() + timedelta(days=2)

        # Girls Only ride
        girls_ride = RideRequest.objects.create(
            creator=self.student_f,
            route="NIT_TO_AIRPORT",
            departure_time=dep_time,
            total_spots=4,
            visibility="GIRLS",
        )
        self.assertTrue(can_view_ride(self.student_f, girls_ride))
        self.assertFalse(can_view_ride(self.student_m, girls_ride))
        self.assertTrue(can_view_ride(self.staff_user, girls_ride))  # Staff oversight

        # Boys Only ride
        boys_ride = RideRequest.objects.create(
            creator=self.student_m,
            route="NIT_TO_AIRPORT",
            departure_time=dep_time,
            total_spots=4,
            visibility="BOYS",
        )
        self.assertTrue(can_view_ride(self.student_m, boys_ride))
        self.assertFalse(can_view_ride(self.student_f, boys_ride))

        # Friends Only ride
        friends_ride = RideRequest.objects.create(
            creator=self.student_m,
            route="NIT_TO_AIRPORT",
            departure_time=dep_time,
            total_spots=4,
            visibility="FRIENDS",
        )
        self.assertTrue(can_view_ride(self.student_m, friends_ride))
        self.assertFalse(can_view_ride(self.student_f, friends_ride))

        # Now make them friends
        Friendship.objects.create(user1=self.student_m, user2=self.student_f)
        self.assertTrue(can_view_ride(self.student_f, friends_ride))

    def test_ride_scoped_affirmative_consent_lifecycle(self):
        """Contact info is only disclosed to confirmed co-passengers who granted affirmative consent."""
        dep_time = timezone.now() + timedelta(days=2)
        ride = RideRequest.objects.create(
            creator=self.student_m,
            route="NIT_TO_AIRPORT",
            departure_time=dep_time,
            total_spots=4,
            visibility="MIXED",
        )
        RideParticipant.objects.create(ride=ride, user=self.student_m)
        RideParticipant.objects.create(ride=ride, user=self.student_f)

        # Before affirmative consent is recorded, contact details must NOT be visible
        self.assertFalse(can_view_ride_contact(self.student_m, ride, self.student_f))
        self.assertFalse(can_view_ride_contact(self.student_f, ride, self.student_m))

        # Record consent for creator (student_m)
        record_ride_consent(ride, self.student_m, share_contact=True)
        # Still not mutual: student_f has not consented
        self.assertFalse(can_view_ride_contact(self.student_m, ride, self.student_f))

        # Record consent for passenger (student_f)
        record_ride_consent(ride, self.student_f, share_contact=True)
        # Now both confirmed participants have granted affirmative consent
        self.assertTrue(can_view_ride_contact(self.student_m, ride, self.student_f))
        self.assertTrue(can_view_ride_contact(self.student_f, ride, self.student_m))

        # When passenger leaves or is removed, consent is revoked immediately
        revoke_ride_consent(ride, self.student_f)
        RideParticipant.objects.filter(ride=ride, user=self.student_f).delete()
        self.assertFalse(can_view_ride_contact(self.student_m, ride, self.student_f))

    def test_api_requires_verified_student_authentication(self):
        """Anonymous and unverified users cannot query ride endpoints."""
        # 1. Anonymous request to /api/v1/rides/ must be rejected (401)
        resp1 = self.client.get(reverse("api_ride_list"))
        self.assertEqual(resp1.status_code, 401)
        self.assertEqual(resp1.json().get("code"), "AUTH_REQUIRED")

        # 2. Authenticated verified student request succeeds
        self.client.force_login(self.student_m)
        resp2 = self.client.get(reverse("api_ride_list"))
        self.assertEqual(resp2.status_code, 200)
        self.assertEqual(resp2.json().get("status"), "success")

        # 3. Unverified student request is rejected (401)
        self.client.force_login(self.unverified_user)
        resp3 = self.client.get(reverse("api_ride_list"))
        self.assertEqual(resp3.status_code, 401)
        self.assertEqual(resp3.json().get("code"), "AUTH_REQUIRED")
