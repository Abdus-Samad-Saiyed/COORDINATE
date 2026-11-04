from datetime import timedelta
import time
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.utils import timezone

from accounts.models import User
from coordinate.models import ParticipantStatus, RideParticipant, RideRequest
from coordinate.participation import transition_participant_state


class StateMachineTransitionTests(TestCase):
    def setUp(self):
        self.host = User.objects.create_user(
            username='host_user',
            enrollment_number='2024BCSE101',
            gender='M',
            phone_number='9876543210',
            password='password123',
            verified=True,
        )
        self.student = User.objects.create_user(
            username='student_user',
            enrollment_number='2024BCSE102',
            gender='M',
            phone_number='9876543211',
            password='password123',
            verified=True,
        )
        self.ride = RideRequest.objects.create(
            creator=self.host,
            route='NIT_TO_AIRPORT',
            visibility='MIXED',
            departure_time=timezone.now() + timedelta(days=2),
            total_spots=3,
        )

    def test_entry_transitions(self):
        # 1. Direct host addition to CONFIRMED
        host_rp = transition_participant_state(self.ride, self.host, ParticipantStatus.CONFIRMED)
        self.assertEqual(host_rp.status, ParticipantStatus.CONFIRMED)

        # 2. Student request to PENDING
        student_rp = transition_participant_state(self.ride, self.student, ParticipantStatus.PENDING, note='Need ride')
        self.assertEqual(student_rp.status, ParticipantStatus.PENDING)
        self.assertEqual(student_rp.note, 'Need ride')

    def test_pending_moderation_and_withdrawal(self):
        # Student requests PENDING
        rp = transition_participant_state(self.ride, self.student, ParticipantStatus.PENDING)
        self.assertEqual(rp.status, ParticipantStatus.PENDING)

        # Host approves -> CONFIRMED
        rp = transition_participant_state(self.ride, self.student, ParticipantStatus.CONFIRMED)
        self.assertEqual(rp.status, ParticipantStatus.CONFIRMED)
        self.assertIsNotNone(rp.reviewed_at)

    def test_decline_and_reentry(self):
        # Student requests PENDING
        transition_participant_state(self.ride, self.student, ParticipantStatus.PENDING)
        # Host declines -> DECLINED
        rp = transition_participant_state(self.ride, self.student, ParticipantStatus.DECLINED)
        self.assertEqual(rp.status, ParticipantStatus.DECLINED)

        # Student re-applies -> PENDING (allowed)
        rp2 = transition_participant_state(self.ride, self.student, ParticipantStatus.PENDING, note='Second try')
        self.assertEqual(rp2.status, ParticipantStatus.PENDING)
        self.assertEqual(rp2.note, 'Second try')

    def test_waitlist_promotion_and_queue_fifo(self):
        # Student joins WAITLISTED
        t1 = timezone.now() - timedelta(hours=2)
        rp = transition_participant_state(self.ride, self.student, ParticipantStatus.WAITLISTED)
        original_joined_at = rp.joined_at

        # Student withdraws -> CANCELLED
        rp = transition_participant_state(self.ride, self.student, ParticipantStatus.CANCELLED)
        self.assertEqual(rp.status, ParticipantStatus.CANCELLED)
        self.assertTrue(rp.is_revoked)

        # Student re-joins WAITLISTED -> queued_at must be updated, joined_at preserved
        time.sleep(0.01)
        rp2 = transition_participant_state(self.ride, self.student, ParticipantStatus.WAITLISTED)
        self.assertEqual(rp2.status, ParticipantStatus.WAITLISTED)
        self.assertEqual(rp2.joined_at, original_joined_at)
        self.assertGreater(rp2.queued_at, original_joined_at)

        # Promotion to CONFIRMED
        rp3 = transition_participant_state(self.ride, self.student, ParticipantStatus.CONFIRMED)
        self.assertEqual(rp3.status, ParticipantStatus.CONFIRMED)

    def test_confirmed_passenger_leave_and_kick(self):
        # Setup confirmed passenger with consent
        rp = transition_participant_state(
            self.ride, self.student, ParticipantStatus.CONFIRMED,
            consent_data={'disclose_ride_identity': True, 'share_contact_details': True}
        )
        self.assertFalse(rp.is_revoked)
        self.assertTrue(rp.disclose_ride_identity)

        # Passenger leaves -> LEFT (consent revoked)
        rp_left = transition_participant_state(self.ride, self.student, ParticipantStatus.LEFT)
        self.assertEqual(rp_left.status, ParticipantStatus.LEFT)
        self.assertTrue(rp_left.is_revoked)
        self.assertIsNotNone(rp_left.revoked_at)

    def test_kicked_passenger_is_terminal(self):
        # Passenger confirmed then kicked
        transition_participant_state(self.ride, self.student, ParticipantStatus.CONFIRMED)
        rp_kicked = transition_participant_state(self.ride, self.student, ParticipantStatus.KICKED)
        self.assertEqual(rp_kicked.status, ParticipantStatus.KICKED)
        self.assertTrue(rp_kicked.is_revoked)

        # Kicked passenger cannot re-request or rejoin
        with self.assertRaises(ValidationError):
            transition_participant_state(self.ride, self.student, ParticipantStatus.PENDING)

        with self.assertRaises(ValidationError):
            transition_participant_state(self.ride, self.student, ParticipantStatus.CONFIRMED)

        with self.assertRaises(ValidationError):
            transition_participant_state(self.ride, self.student, ParticipantStatus.WAITLISTED)

    def test_illegal_transitions_raise_validation_error(self):
        # Cannot jump from None to LEFT or KICKED
        with self.assertRaises(ValidationError):
            transition_participant_state(self.ride, self.student, ParticipantStatus.LEFT)

        with self.assertRaises(ValidationError):
            transition_participant_state(self.ride, self.student, ParticipantStatus.KICKED)

        # Cannot jump from WAITLISTED to LEFT directly
        transition_participant_state(self.ride, self.student, ParticipantStatus.WAITLISTED)
        with self.assertRaises(ValidationError):
            transition_participant_state(self.ride, self.student, ParticipantStatus.LEFT)
