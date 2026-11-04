from datetime import timedelta
import threading
import unittest
from django.db import connection, transaction
from django.test import TransactionTestCase
from django.utils import timezone

from accounts.models import User
from coordinate.models import ParticipantStatus, RideParticipant, RideRequest
from coordinate.participation import transition_participant_state


class ConcurrencyLockingTests(TransactionTestCase):
    """
    Validates atomic row-locking under concurrent threads during seat claims.
    Multi-threaded row locking is designed for PostgreSQL row-level locks and
    is skipped on SQLite which employs file/table-level locks.
    """
    def setUp(self):
        self.host = User.objects.create_user(
            username='c_host', enrollment_number='2024BCSE401', gender='M', phone_number='9876543401', password='pass'
        )
        self.student1 = User.objects.create_user(
            username='c_s1', enrollment_number='2024BCSE402', gender='M', phone_number='9876543402', password='pass'
        )
        self.student2 = User.objects.create_user(
            username='c_s2', enrollment_number='2024BCSE403', gender='M', phone_number='9876543403', password='pass'
        )
        self.ride = RideRequest.objects.create(
            creator=self.host,
            route='NIT_TO_AIRPORT',
            visibility='MIXED',
            departure_time=timezone.now() + timedelta(days=2),
            total_spots=2,  # 1 host spot + 1 remaining passenger spot
        )
        transition_participant_state(self.ride, self.host, ParticipantStatus.CONFIRMED)

    @unittest.skipIf(connection.vendor == 'sqlite', "Multi-threaded row concurrency tests require PostgreSQL (skipped on SQLite)")
    def test_concurrent_claim_final_spot(self):
        """
        Two simultaneous approvals/transitions for the last remaining seat.
        Under row locking, exactly one becomes CONFIRMED, and total confirmed count never exceeds total_spots.
        """
        results = []

        def claim_seat(user):
            connection.close()
            try:
                with transaction.atomic():
                    r = RideRequest.objects.select_for_update().get(id=self.ride.id)
                    if r.spots_remaining() > 0:
                        transition_participant_state(r, user, ParticipantStatus.CONFIRMED)
                        results.append((user.enrollment_number, True))
                    else:
                        results.append((user.enrollment_number, False))
            except Exception as e:
                results.append((user.enrollment_number, False, str(e)))
            finally:
                connection.close()

        t1 = threading.Thread(target=claim_seat, args=(self.student1,))
        t2 = threading.Thread(target=claim_seat, args=(self.student2,))

        t1.start()
        t2.start()
        t1.join()
        t2.join()

        success_count = sum(1 for r in results if r[1] is True)
        self.assertEqual(success_count, 1, f"Expected exactly 1 seat claim to succeed, got results: {results}")

        confirmed_count = RideParticipant.objects.filter(ride=self.ride, status=ParticipantStatus.CONFIRMED).count()
        self.assertEqual(confirmed_count, 2)  # Host (1) + 1 winner = 2 (total_spots)
