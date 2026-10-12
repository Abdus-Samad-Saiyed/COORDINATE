from datetime import timedelta

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import Friendship, User

from .models import (
    RideMessage,
    RideParticipant,
    RideRequest,
    RideReview
)


class RideWorkflowTests(TestCase):

    def setUp(self):

        self.creator = User.objects.create_user(
            username='Creator',
            enrollment_number='2024BCSE001',
            gender='M',
            phone_number='9999999999',
            password='password123'
        )

        self.other = User.objects.create_user(
            username='Other',
            enrollment_number='2024BCSE002',
            gender='M',
            phone_number='9999999998',
            password='password123'
        )

        self.girl = User.objects.create_user(
            username='Girl',
            enrollment_number='2024BCSE003',
            gender='F',
            phone_number='9999999997',
            password='password123'
        )

    def future_time(self, days=1):

        return timezone.now() + timedelta(days=days)

    def create_ride(self, total_spots=2, visibility='MIXED'):

        ride = RideRequest.objects.create(
            creator=self.creator,
            route='NIT_TO_AIRPORT',
            visibility=visibility,
            departure_time=self.future_time(),
            total_spots=total_spots
        )

        RideParticipant.objects.create(
            ride=ride,
            user=self.creator
        )

        ride.sync_status()

        return ride

    def test_create_ride_adds_creator_and_capacity_one_is_full(self):

        self.client.force_login(self.creator)

        response = self.client.post(
            reverse('create_ride'),
            {
                'route': 'NIT_TO_AIRPORT',
                'visibility': 'MIXED',
                'departure_time': self.future_time().strftime(
                    '%Y-%m-%dT%H:%M'
                ),
                'total_spots': '1',
            }
        )

        self.assertRedirects(response, reverse('ride_list'))

        ride = RideRequest.objects.get()

        self.assertEqual(ride.status, 'FULL')
        self.assertEqual(ride.participant_count(), 1)
        self.assertTrue(
            RideParticipant.objects.filter(
                ride=ride,
                user=self.creator
            ).exists()
        )

    def test_full_ride_reopens_when_participant_leaves(self):

        ride = self.create_ride(total_spots=2)

        RideParticipant.objects.create(
            ride=ride,
            user=self.other
        )

        ride.sync_status()
        ride.refresh_from_db()

        self.assertEqual(ride.status, 'FULL')

        self.client.force_login(self.other)

        self.client.post(
            reverse('leave_ride', args=[ride.id])
        )

        ride.refresh_from_db()

        self.assertEqual(ride.status, 'OPEN')
        self.assertEqual(ride.participant_count(), 1)

    def test_join_rejects_full_completed_restricted_and_get_requests(self):

        full_ride = self.create_ride(total_spots=1)

        self.client.force_login(self.other)

        self.assertEqual(
            self.client.get(
                reverse('join_ride', args=[full_ride.id])
            ).status_code,
            405
        )

        self.client.post(
            reverse('join_ride', args=[full_ride.id])
        )

        self.assertFalse(
            RideParticipant.objects.filter(
                ride=full_ride,
                user=self.other
            ).exists()
        )

        completed = self.create_ride(total_spots=3)
        completed.status = 'COMPLETED'
        completed.save(update_fields=['status'])

        self.client.post(
            reverse('join_ride', args=[completed.id])
        )

        self.assertFalse(
            RideParticipant.objects.filter(
                ride=completed,
                user=self.other
            ).exists()
        )

        girls_only = self.create_ride(
            total_spots=3,
            visibility='GIRLS'
        )

        self.client.post(
            reverse('join_ride', args=[girls_only.id])
        )

        self.assertFalse(
            RideParticipant.objects.filter(
                ride=girls_only,
                user=self.other
            ).exists()
        )

    def test_duplicate_and_multiple_active_ride_join_are_prevented(self):

        ride = self.create_ride(total_spots=3)

        self.client.force_login(self.other)

        self.client.post(reverse('join_ride', args=[ride.id]))
        self.client.post(reverse('join_ride', args=[ride.id]))

        self.assertEqual(
            RideParticipant.objects.filter(
                ride=ride,
                user=self.other
            ).count(),
            1
        )

        second_ride = RideRequest.objects.create(
            creator=self.girl,
            route='AIRPORT_TO_NIT',
            visibility='MIXED',
            departure_time=self.future_time(),
            total_spots=3
        )

        RideParticipant.objects.create(
            ride=second_ride,
            user=self.girl
        )

        self.client.post(reverse('join_ride', args=[second_ride.id]))

        self.assertFalse(
            RideParticipant.objects.filter(
                ride=second_ride,
                user=self.other
            ).exists()
        )

    def test_empty_ride_deleted_after_last_participant_leaves(self):

        ride = self.create_ride(total_spots=1)

        self.client.force_login(self.creator)
        self.client.post(reverse('leave_ride', args=[ride.id]))

        self.assertFalse(
            RideRequest.objects.filter(id=ride.id).exists()
        )

    def test_creator_can_kick_participant_and_cannot_kick_self(self):

        ride = self.create_ride(total_spots=2)

        other_participant = RideParticipant.objects.create(
            ride=ride,
            user=self.other
        )

        creator_participant = RideParticipant.objects.get(
            ride=ride,
            user=self.creator
        )

        self.client.force_login(self.creator)
        self.client.post(
            reverse(
                'kick_participant',
                args=[ride.id, other_participant.id]
            )
        )

        self.assertFalse(
            RideParticipant.objects.filter(
                id=other_participant.id
            ).exists()
        )

        self.client.post(
            reverse(
                'kick_participant',
                args=[ride.id, creator_participant.id]
            )
        )

        self.assertTrue(
            RideParticipant.objects.filter(
                id=creator_participant.id
            ).exists()
        )

    def test_completed_ride_stays_completed_on_save(self):

        ride = self.create_ride(total_spots=2)
        ride.status = 'COMPLETED'
        ride.save()
        ride.save()
        ride.refresh_from_db()

        self.assertEqual(ride.status, 'COMPLETED')

    def test_ride_detail_private_and_chat_participant_only(self):

        ride = self.create_ride(total_spots=2)
        outsider = User.objects.create_user(
            username='Outsider',
            enrollment_number='2024BCSE004',
            gender='M',
            phone_number='9999999996',
            password='password123'
        )

        self.client.force_login(outsider)

        self.assertEqual(
            self.client.get(
                reverse('ride_detail', args=[ride.id])
            ).status_code,
            404
        )

        self.assertEqual(
            self.client.post(
                reverse('send_message', args=[ride.id]),
                {'content': 'hello'}
            ).status_code,
            403
        )

        self.client.force_login(self.creator)
        self.client.post(
            reverse('send_message', args=[ride.id]),
            {'content': 'Meet at gate 1'}
        )

        self.assertEqual(RideMessage.objects.count(), 1)
        self.assertContains(
            self.client.get(
                reverse('ride_detail', args=[ride.id])
            ),
            'Meet at gate 1'
        )

    def test_review_requires_completed_participated_ride(self):

        ride = self.create_ride(total_spots=2)

        RideParticipant.objects.create(
            ride=ride,
            user=self.other
        )

        self.client.force_login(self.creator)

        self.assertEqual(
            self.client.get(
                reverse(
                    'review_user',
                    args=[ride.id, self.other.id]
                )
            ).status_code,
            403
        )

        ride.status = 'COMPLETED'
        ride.save(update_fields=['status'])

        response = self.client.post(
            reverse('review_user', args=[ride.id, self.other.id]),
            {
                'rating': '5',
                'complaint': 'Helpful'
            }
        )

        self.assertRedirects(
            response,
            reverse('ride_detail', args=[ride.id])
        )
        self.assertEqual(RideReview.objects.count(), 1)

        self.client.post(
            reverse('review_user', args=[ride.id, self.other.id]),
            {
                'rating': '4',
                'complaint': ''
            }
        )

        self.assertEqual(RideReview.objects.count(), 1)

    def test_friends_only_ride_allows_friend(self):

        Friendship.objects.create(
            user1=self.creator,
            user2=self.other
        )

        ride = self.create_ride(
            total_spots=2,
            visibility='FRIENDS'
        )

        self.client.force_login(self.other)
        self.client.post(reverse('join_ride', args=[ride.id]))

        self.assertTrue(
            RideParticipant.objects.filter(
                ride=ride,
                user=self.other
            ).exists()
        )
