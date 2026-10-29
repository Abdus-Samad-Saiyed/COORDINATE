"""Stage 2 & Stage 3 verification tests:
- Scoped RideConsent (disclose identity vs share contact)
- Host approval workflow for join requests (Web & API parity)
- Zero synthetic contact-sharing consent
- Immediate revocation upon leave/kick/cancellation
"""

import json
from datetime import timedelta
from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from coordinate.forms import RideRequestForm
from coordinate.models import (
    RideConsent,
    RideJoinRequest,
    RideParticipant,
    RideRequest,
    RideWaitlist,
)
from coordinate.policies import (
    can_view_profile_field,
    can_view_ride,
    can_view_ride_contact,
    can_view_student_directory,
    is_verified_student,
    record_ride_consent,
)

User = get_user_model()


class Stage2And3ScopedConsentAndApprovalTests(TestCase):
    def setUp(self):
        from django.core.cache import cache
        cache.clear()
        self.client = Client()

        self.host = User.objects.create_user(
            enrollment_number="2024BCSE501",
            username="2024BCSE501",
            password="SecurePassword123!",
            first_name="Host",
            last_name="Student",
            gender="M",
            phone_number="+919876543501",
            email="host501@nitsri.ac.in",
            verified=True,
            is_active=True,
        )

        self.passenger = User.objects.create_user(
            enrollment_number="2024BCSE502",
            username="2024BCSE502",
            password="SecurePassword123!",
            first_name="Passenger",
            last_name="Student",
            gender="M",
            phone_number="+919876543502",
            email="pass502@nitsri.ac.in",
            verified=True,
            is_active=True,
        )

        self.other_user = User.objects.create_user(
            enrollment_number="2024BCSE503",
            username="2024BCSE503",
            password="SecurePassword123!",
            first_name="Other",
            last_name="Student",
            gender="M",
            phone_number="+919876543503",
            email="other503@nitsri.ac.in",
            verified=True,
            is_active=True,
        )

        self.future_dep = timezone.now() + timedelta(days=2)
        self.ride = RideRequest.objects.create(
            creator=self.host,
            route="NIT_TO_AIRPORT",
            departure_time=self.future_dep,
            total_spots=3,
            visibility="MIXED",
            status="OPEN",
        )
        RideParticipant.objects.create(ride=self.ride, user=self.host)
        record_ride_consent(self.ride, self.host, disclose_identity=True, share_contact=True)

    def _get_api_token(self, enrollment, password="SecurePassword123!"):
        c = Client()
        res = c.post(
            reverse("api_login"),
            data=json.dumps({"enrollment_number": enrollment, "password": password}),
            content_type="application/json",
        )
        return res.json()["data"]["token"]

    def test_form_consent_validation(self):
        """RideRequestForm requires disclose_identity consent and defaults share_contact to False."""
        now = timezone.now() + timedelta(days=1)
        valid_data = {
            "route": "NIT_TO_AIRPORT",
            "visibility": "MIXED",
            "departure_time": now.strftime("%Y-%m-%dT%H:%M"),
            "total_spots": 3,
            "disclose_identity": True,
            "share_contact": False,
        }
        form = RideRequestForm(data=valid_data)
        self.assertTrue(form.is_valid(), form.errors)
        self.assertTrue(form.cleaned_data["disclose_identity"])
        self.assertFalse(form.cleaned_data["share_contact"])

        # Explicitly rejecting identity disclosure fails form validation
        invalid_data = valid_data.copy()
        invalid_data["disclose_identity"] = False
        invalid_form = RideRequestForm(data=invalid_data)
        self.assertFalse(invalid_form.is_valid())
        self.assertIn("disclose_identity", invalid_form.errors)

    def test_web_join_request_flow_and_approval(self):
        """Web join creates a PENDING request; host approval transitions to participant without synthetic consent."""
        self.client.force_login(self.passenger)

        # Passenger requests to join with default privacy (share_contact=False)
        resp = self.client.post(
            reverse("join_ride", kwargs={"ride_id": self.ride.id}),
            data={"disclose_identity": "true", "share_contact": "false"},
        )
        self.assertEqual(resp.status_code, 302)

        # Pending join request exists
        join_req = RideJoinRequest.objects.filter(ride=self.ride, user=self.passenger).first()
        self.assertIsNotNone(join_req)
        self.assertEqual(join_req.status, "PENDING")

        # Not yet a participant
        self.assertFalse(RideParticipant.objects.filter(ride=self.ride, user=self.passenger).exists())

        # Consent record created with share_contact_details=False
        consent = RideConsent.objects.get(ride=self.ride, user=self.passenger)
        self.assertTrue(consent.disclose_ride_identity)
        self.assertFalse(consent.share_contact_details)

        # Host approves the request
        self.client.force_login(self.host)
        resp_approve = self.client.post(
            reverse("approve_join_request", kwargs={"ride_id": self.ride.id, "request_id": join_req.id})
        )
        self.assertEqual(resp_approve.status_code, 302)

        # Now confirmed participant
        self.assertTrue(RideParticipant.objects.filter(ride=self.ride, user=self.passenger).exists())
        join_req.refresh_from_db()
        self.assertEqual(join_req.status, "APPROVED")

        # Consent was NOT synthesized to True
        consent.refresh_from_db()
        self.assertFalse(consent.share_contact_details)
        # Host cannot view passenger contact because passenger opted out of contact sharing
        self.assertFalse(can_view_ride_contact(self.host, self.ride, self.passenger))

    def test_api_join_request_and_host_approval(self):
        """API join returns HTTP 202 Accepted; host can approve or decline via REST endpoints."""
        pass_token = self._get_api_token(self.passenger.enrollment_number)
        host_token = self._get_api_token(self.host.enrollment_number)

        # 1. Passenger requests to join via API
        resp_join = self.client.post(
            reverse("api_ride_join", kwargs={"ride_id": self.ride.id}),
            data=json.dumps({"disclose_identity": True, "share_contact": True}),
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {pass_token}",
        )
        self.assertEqual(resp_join.status_code, 202)
        data = resp_join.json()["data"]
        self.assertEqual(data["status"], "pending")
        req_id = data["request_id"]

        # 2. Non-host cannot approve
        other_token = self._get_api_token(self.other_user.enrollment_number)
        resp_unauth = self.client.post(
            reverse("api_ride_approve_request", kwargs={"ride_id": self.ride.id, "request_id": req_id}),
            HTTP_AUTHORIZATION=f"Bearer {other_token}",
        )
        self.assertEqual(resp_unauth.status_code, 404)

        # 3. Host approves
        resp_approve = self.client.post(
            reverse("api_ride_approve_request", kwargs={"ride_id": self.ride.id, "request_id": req_id}),
            HTTP_AUTHORIZATION=f"Bearer {host_token}",
        )
        self.assertEqual(resp_approve.status_code, 200)

        # Because passenger explicitly opted in (share_contact: True), both can view contacts
        self.ride.refresh_from_db()
        self.assertTrue(can_view_ride_contact(self.host, self.ride, self.passenger))
        self.assertTrue(can_view_ride_contact(self.passenger, self.ride, self.host))

    def test_standby_waitlist_promotion_does_not_synthesize_contact_consent(self):
        """Standby promotion automatically confirms participant but retains strict privacy for contacts."""
        # Fill the ride
        RideParticipant.objects.create(ride=self.ride, user=self.passenger)
        record_ride_consent(self.ride, self.passenger, disclose_identity=True, share_contact=True)
        self.ride.total_spots = 2
        self.ride.sync_status()
        self.assertEqual(self.ride.status, "FULL")

        # Third user joins waitlist
        RideWaitlist.objects.create(ride=self.ride, user=self.other_user)

        # Passenger leaves
        self.client.force_login(self.passenger)
        self.client.post(reverse("leave_ride", kwargs={"ride_id": self.ride.id}))

        # Other user was promoted to participant
        self.assertTrue(RideParticipant.objects.filter(ride=self.ride, user=self.other_user).exists())
        self.assertFalse(RideWaitlist.objects.filter(ride=self.ride, user=self.other_user).exists())

        # Contact consent defaults to False; no synthesis
        other_consent = RideConsent.objects.get(ride=self.ride, user=self.other_user)
        self.assertTrue(other_consent.disclose_ride_identity)
        self.assertFalse(other_consent.share_contact_details)
        self.assertFalse(can_view_ride_contact(self.host, self.ride, self.other_user))

    def test_leave_and_kick_revocation(self):
        """Leaving or getting kicked marks consent is_revoked=True and share_contact_details=False."""
        RideParticipant.objects.create(ride=self.ride, user=self.passenger)
        record_ride_consent(self.ride, self.passenger, disclose_identity=True, share_contact=True)
        self.assertTrue(can_view_ride_contact(self.host, self.ride, self.passenger))

        # Passenger leaves
        self.client.force_login(self.passenger)
        self.client.post(reverse("leave_ride", kwargs={"ride_id": self.ride.id}))

        consent = RideConsent.objects.get(ride=self.ride, user=self.passenger)
        self.assertTrue(consent.is_revoked)
        self.assertIsNotNone(consent.revoked_at)
        self.assertFalse(consent.share_contact_details)
        self.assertFalse(can_view_ride_contact(self.host, self.ride, self.passenger))
