from datetime import timedelta
from django.test import TestCase
from django.utils import timezone

from accounts.models import User
from coordinate.models import ParticipantStatus, RideParticipant, RideRequest
from coordinate.policies import can_view_ride_contact, can_view_ride_identity
from coordinate.services import user_has_active_ride
from coordinate.participation import transition_participant_state
from campus.api.serializers import serialize_ride_detail, serialize_ride


class AuthorizationRegressionTests(TestCase):
    def setUp(self):
        self.host = User.objects.create_user(
            username='host_auth',
            enrollment_number='2024BCSE201',
            gender='M',
            phone_number='9876543220',
            password='password123',
            verified=True,
        )
        self.student = User.objects.create_user(
            username='student_auth',
            enrollment_number='2024BCSE202',
            gender='M',
            phone_number='9876543221',
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
        transition_participant_state(self.ride, self.host, ParticipantStatus.CONFIRMED)

    def test_non_confirmed_statuses_isolated_from_authorization_and_capacity(self):
        non_confirmed_statuses = [
            ParticipantStatus.PENDING,
            ParticipantStatus.WAITLISTED,
            ParticipantStatus.LEFT,
            ParticipantStatus.KICKED,
            ParticipantStatus.DECLINED,
            ParticipantStatus.CANCELLED,
        ]

        for status in non_confirmed_statuses:
            with self.subTest(status=status):
                # Setup participant in target non-confirmed status
                rp, _ = RideParticipant.all_rows.update_or_create(
                    ride=self.ride,
                    user=self.student,
                    defaults={
                        'status': status,
                        'disclose_ride_identity': True,
                        'share_contact_details': True,
                    }
                )

                # 1. ConfirmedManager isolation: RideParticipant.objects.filter(...) misses them
                self.assertFalse(
                    RideParticipant.objects.filter(ride=self.ride, user=self.student).exists(),
                    f"Status {status} leaked into default RideParticipant.objects queryset!"
                )

                # 2. Capacity isolation: spots_remaining and is_full only count confirmed
                self.assertEqual(self.ride.participant_count(), 1, f"Status {status} incremented participant count!")
                self.assertEqual(self.ride.spots_remaining(), 2)
                self.assertFalse(self.ride.is_full())

                # 3. Active ride isolation: user_has_active_ride evaluates to False
                self.assertFalse(
                    user_has_active_ride(self.student),
                    f"Status {status} wrongly blocked student from creating/joining other rides!"
                )

                # 4. API serialization isolation: serialize_ride_detail excludes them
                detail = serialize_ride_detail(self.ride, request_user=self.host)
                passenger_enrollments = [p['enrollment_number'] for p in detail['participants'] if not p.get('is_creator')]
                self.assertNotIn(
                    self.student.enrollment_number,
                    passenger_enrollments,
                    f"Status {status} student leaked into serialized passenger roster!"
                )

                # 5. Contact privacy isolation: non-confirmed passengers never reveal contacts
                self.assertFalse(
                    can_view_ride_contact(self.host, self.ride, self.student),
                    f"Host was able to view private contact details of student with status {status}!"
                )
