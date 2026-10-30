from datetime import timedelta

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import Contributor, Friendship, User

from .models import (
    RideJoinRequest,
    RideMessage,
    RideParticipant,
    RideRequest,
    RideReview,
)


class RideWorkflowTests(TestCase):

    def setUp(self):

        self.creator = User.objects.create_user(
            username='Creator',
            enrollment_number='2024BCSE001',
            gender='M',
            phone_number='9999999999',
            password='password123',
            verified=True,
        )

        self.other = User.objects.create_user(
            username='Other',
            enrollment_number='2024BCSE002',
            gender='M',
            phone_number='9999999998',
            password='password123',
            verified=True,
        )

        self.girl = User.objects.create_user(
            username='Girl',
            enrollment_number='2024BCSE003',
            gender='F',
            phone_number='9999999997',
            password='password123',
            verified=True,
        )

    def future_time(self, days=1):

        return timezone.now() + timedelta(days=days)

    def create_ride(self, total_spots=2, visibility='MIXED', route='NIT_TO_AIRPORT'):

        ride = RideRequest.objects.create(
            creator=self.creator,
            route=route,
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

        # Duplicate join requests create only 1 pending request
        self.client.post(reverse('join_ride', args=[ride.id]))
        self.client.post(reverse('join_ride', args=[ride.id]))

        self.assertEqual(
            RideJoinRequest.objects.filter(
                ride=ride,
                user=self.other,
                status='PENDING'
            ).count(),
            1
        )

        # Host approves the join request
        join_req = RideJoinRequest.objects.get(ride=ride, user=self.other)
        self.client.force_login(self.creator)
        self.client.post(reverse('approve_join_request', args=[ride.id, join_req.id]))

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

        # Student with active ride cannot request second ride
        self.client.force_login(self.other)
        self.client.post(reverse('join_ride', args=[second_ride.id]))

        self.assertFalse(
            RideParticipant.objects.filter(
                ride=second_ride,
                user=self.other
            ).exists()
        )
        self.assertFalse(
            RideJoinRequest.objects.filter(
                ride=second_ride,
                user=self.other
            ).exists()
        )

    def test_empty_ride_deleted_after_last_participant_leaves(self):

        ride = self.create_ride(total_spots=1)

        self.client.force_login(self.creator)
        self.client.post(reverse('leave_ride', args=[ride.id]))

        ride.refresh_from_db()
        self.assertEqual(ride.status, 'CANCELLED')

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

        # Host approves the join request
        join_req = RideJoinRequest.objects.get(ride=ride, user=self.other)
        self.assertEqual(join_req.status, 'PENDING')
        self.client.force_login(self.creator)
        self.client.post(reverse('approve_join_request', args=[ride.id, join_req.id]))

        self.assertTrue(
            RideParticipant.objects.filter(
                ride=ride,
                user=self.other
            ).exists()
        )

    def test_ride_join_request_approval_and_decline_workflow(self):
        ride = self.create_ride(total_spots=3)

        # Student requests to join
        self.client.force_login(self.other)
        resp = self.client.post(reverse('join_ride', args=[ride.id]))
        self.assertRedirects(resp, reverse('ride_list'))

        join_req = RideJoinRequest.objects.get(ride=ride, user=self.other)
        self.assertEqual(join_req.status, 'PENDING')
        self.assertFalse(RideParticipant.objects.filter(ride=ride, user=self.other).exists())

        # Non-creator cannot decline or approve
        outsider = User.objects.create_user(
            username='OutsiderJoin',
            enrollment_number='2024BCSE099',
            gender='M',
            phone_number='9999999988',
            password='password123',
            verified=True,
        )
        self.client.force_login(outsider)
        self.assertIn(
            self.client.post(reverse('approve_join_request', args=[ride.id, join_req.id])).status_code,
            [403, 404]
        )

        # Host declines the request
        self.client.force_login(self.creator)
        self.client.post(reverse('decline_join_request', args=[ride.id, join_req.id]))
        join_req.refresh_from_db()
        self.assertEqual(join_req.status, 'DECLINED')
        self.assertFalse(RideParticipant.objects.filter(ride=ride, user=self.other).exists())

        # Student cancels a new request
        self.client.force_login(self.other)
        self.client.post(reverse('join_ride', args=[ride.id]))
        self.assertTrue(RideJoinRequest.objects.filter(ride=ride, user=self.other, status='PENDING').exists())
        self.client.post(reverse('cancel_join_request', args=[ride.id]))
        self.assertFalse(RideJoinRequest.objects.filter(ride=ride, user=self.other, status='PENDING').exists())

        # Host approves a final request
        self.client.post(reverse('join_ride', args=[ride.id]))
        final_req = RideJoinRequest.objects.get(ride=ride, user=self.other, status='PENDING')
        self.client.force_login(self.creator)
        self.client.post(reverse('approve_join_request', args=[ride.id, final_req.id]))
        final_req.refresh_from_db()
        self.assertEqual(final_req.status, 'APPROVED')
        self.assertTrue(RideParticipant.objects.filter(ride=ride, user=self.other).exists())

    def test_immediate_grievance_review_for_kicked_and_left_passengers(self):
        ride = self.create_ride(total_spots=3)
        RideParticipant.objects.create(ride=ride, user=self.other)

        # Host kicks participant while ride is OPEN
        self.client.force_login(self.creator)
        other_part = RideParticipant.objects.get(ride=ride, user=self.other)
        self.client.post(reverse('kick_participant', args=[ride.id, other_part.id]))
        ride.refresh_from_db()
        self.assertIn(self.other, ride.kicked_users.all())

        # Host can review immediately with grievance without waiting for ride COMPLETED
        self.assertEqual(ride.status, 'OPEN')
        rev_resp = self.client.post(
            reverse('review_user', args=[ride.id, self.other.id]),
            {
                'rating': '2',
                'punctuality_rating': '1',
                'communication_rating': '2',
                'reliability_rating': '1',
                'grievance': 'LATE',
                'complaint': 'Arrived 25 minutes late without heads-up.',
            }
        )
        self.assertRedirects(rev_resp, reverse('ride_detail', args=[ride.id]))
        self.assertTrue(RideReview.objects.filter(ride=ride, reviewed_user=self.other, grievance='LATE').exists())

        # Second student leaves voluntarily
        voluntary_user = User.objects.create_user(
            username='VoluntaryLeaver',
            enrollment_number='2024BCSE088',
            gender='M',
            phone_number='9999999987',
            password='password123'
        )
        RideParticipant.objects.create(ride=ride, user=voluntary_user)
        self.client.force_login(voluntary_user)
        self.client.post(reverse('leave_ride', args=[ride.id]))
        ride.refresh_from_db()
        self.assertIn(voluntary_user, ride.left_users.all())

        # Host reviews departed user immediately with NO_SHOW grievance
        self.client.force_login(self.creator)
        self.client.post(
            reverse('review_user', args=[ride.id, voluntary_user.id]),
            {
                'rating': '1',
                'punctuality_rating': '1',
                'communication_rating': '1',
                'reliability_rating': '1',
                'grievance': 'NO_SHOW',
                'complaint': 'Left ride 5 minutes before departure.',
            }
        )
        self.assertTrue(RideReview.objects.filter(ride=ride, reviewed_user=voluntary_user, grievance='NO_SHOW').exists())

    def test_ride_density_telemetry_and_ordering(self):
        self.client.force_login(self.creator)

        # Create multiple rides across different dates
        r1 = self.create_ride(total_spots=2, route='NIT_TO_AIRPORT')
        r2 = RideRequest.objects.create(
            creator=self.creator,
            route='LAL_CHOWK_TO_NIT',
            visibility='MIXED',
            departure_time=timezone.now() + timedelta(days=2),
            total_spots=4
        )
        RideParticipant.objects.create(ride=r2, user=self.creator)

        # Check ride list defaults to all upcoming rides (un-filtered)
        resp = self.client.get(reverse('ride_list'))
        self.assertEqual(resp.status_code, 200)
        self.assertIn('density_data', resp.context)
        self.assertEqual(len(resp.context['density_data']), 14)

        # Check order_by parameters
        for order_param in ['time_asc', 'time_desc', 'spots_desc', 'created_desc']:
            order_resp = self.client.get(reverse('ride_list') + f'?order_by={order_param}')
            self.assertEqual(order_resp.status_code, 200)

        # Check queue_only filter
        q_resp = self.client.get(reverse('ride_list') + '?queue_only=1')
        self.assertEqual(q_resp.status_code, 200)

        # Check date filter application and verify reset button URL is clean (no bare ampersand 404)
        today_str = timezone.now().strftime('%Y-%m-%d')
        date_filtered_resp = self.client.get(reverse('ride_list') + f'?date_from={today_str}&date_to={today_str}')
        self.assertEqual(date_filtered_resp.status_code, 200)
        self.assertTrue(date_filtered_resp.context['has_date_filter'])
        self.assertContains(date_filtered_resp, 'View All Dates (Reset Date Filter)')
        self.assertNotContains(date_filtered_resp, '/coordinate/&order_by')
        self.assertContains(date_filtered_resp, '/coordinate/?order_by')

    def test_contributor_nomination_peer_workflow(self):
        # Ordinary non-admin user cannot nominate or add
        self.client.force_login(self.other)
        nom_resp = self.client.post(
            reverse('nominate_contributor'),
            {
                'name': 'Other Nominee',
                'enrollment_number': self.creator.enrollment_number,
                'role': 'Core Maintainer',
                'bio': 'Built routing algorithm.',
            }
        )
        self.assertRedirects(nom_resp, reverse('contributors'))
        self.assertFalse(Contributor.objects.filter(name='Other Nominee').exists())

        # Admin can add contributor
        self.creator.is_staff = True
        self.creator.save()
        self.client.force_login(self.creator)
        success_nom = self.client.post(
            reverse('nominate_contributor'),
            {
                'name': 'Test Other Contributor',
                'enrollment_number': self.other.enrollment_number,
                'role': 'Full-stack Contributor',
                'bio': 'Implemented real-time chat telemetry.',
                'github_url': 'https://github.com/other',
            }
        )
        self.assertRedirects(success_nom, reverse('contributors'))
        contrib = Contributor.objects.filter(user=self.other, nominated_by=self.creator).first()
        self.assertIsNotNone(contrib)

        # Admin can remove contributor
        remove_resp = self.client.post(reverse('remove_contributor', args=[contrib.id]))
        self.assertRedirects(remove_resp, reverse('contributors'))
        self.assertFalse(Contributor.objects.filter(id=contrib.id).exists())

    def test_unverified_student_cannot_create_ride(self):
        """Unverified student cannot create a ride."""
        unverified_user = User.objects.create_user(
            username='2024BCSE077',
            enrollment_number='2024BCSE077',
            gender='M',
            phone_number='9999999977',
            password='password123',
            verified=False,
            is_active=True,
        )
        self.client.force_login(unverified_user)
        dep_time = (timezone.now() + timedelta(days=1)).strftime('%Y-%m-%dT%H:%M')
        resp = self.client.post(reverse('create_ride'), {
            'route': 'NIT_TO_AIRPORT',
            'visibility': 'MIXED',
            'departure_time': dep_time,
            'total_spots': 3,
            'disclose_identity': 'on',
        })
        self.assertRedirects(resp, reverse('ride_list'))
        self.assertFalse(RideRequest.objects.filter(creator=unverified_user).exists())

    def test_reschedule_concluded_ride_fails(self):
        """Rescheduling a ride whose departure + 2 hours buffer has elapsed is blocked."""
        past_ride = RideRequest.objects.create(
            creator=self.creator,
            route='NIT_TO_AIRPORT',
            visibility='MIXED',
            departure_time=timezone.now() - timedelta(hours=3),
            total_spots=3,
            status='OPEN',
        )
        RideParticipant.objects.create(ride=past_ride, user=self.creator)
        self.client.force_login(self.creator)
        new_dep_time = (timezone.now() + timedelta(days=2)).strftime('%Y-%m-%dT%H:%M')
        resp = self.client.post(reverse('reschedule_ride', args=[past_ride.id]), {
            'departure_time': new_dep_time,
        })
        self.assertRedirects(resp, reverse('ride_detail', args=[past_ride.id]))
        past_ride.refresh_from_db()
        self.assertNotEqual(past_ride.departure_time.strftime('%Y-%m-%d'), (timezone.now() + timedelta(days=2)).strftime('%Y-%m-%d'))
