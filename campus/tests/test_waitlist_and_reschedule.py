"""Tests for Ride Waitlist (Standby Queue), Automatic Promotion, Rescheduling, and Gender Invariants."""

import datetime
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import User
from coordinate.models import (
    RideMessage,
    RideParticipant,
    RideRequest,
    RideWaitlist,
)


class RideWaitlistAndPromotionTests(TestCase):

    def setUp(self):
        self.host = User.objects.create_user(
            username='2024BCSE201',
            enrollment_number='2024BCSE201',
            gender='M',
            phone_number='9876543201',
            password='Password123',
            verified=True,
        )
        self.passenger1 = User.objects.create_user(
            username='2024BCSE202',
            enrollment_number='2024BCSE202',
            gender='M',
            phone_number='9876543202',
            password='Password123',
            verified=True,
        )
        self.passenger2 = User.objects.create_user(
            username='2024BCSE203',
            enrollment_number='2024BCSE203',
            gender='M',
            phone_number='9876543203',
            password='Password123',
            verified=True,
        )
        self.standby_user = User.objects.create_user(
            username='2024BCSE204',
            enrollment_number='2024BCSE204',
            gender='M',
            phone_number='9876543204',
            password='Password123',
            verified=True,
        )
        self.female_user = User.objects.create_user(
            username='2024BCSE205',
            enrollment_number='2024BCSE205',
            gender='F',
            phone_number='9876543205',
            password='Password123',
            verified=True,
        )

        # Ride with capacity of 2 spots (Host + 1 passenger)
        self.ride = RideRequest.objects.create(
            creator=self.host,
            route='NIT_TO_AIRPORT',
            visibility='MIXED',
            departure_time=timezone.now() + datetime.timedelta(days=2),
            total_spots=2,
            status='OPEN',
        )
        RideParticipant.objects.create(ride=self.ride, user=self.host)
        RideParticipant.objects.create(ride=self.ride, user=self.passenger1)
        self.ride.sync_status()
        self.assertEqual(self.ride.status, 'FULL')

    def test_join_and_leave_waitlist(self):
        """Student can join standby waitlist for full ride and leave it."""
        self.client.force_login(self.standby_user)

        # Join waitlist
        response = self.client.post(reverse('join_waitlist', args=[self.ride.id]))
        self.assertEqual(response.status_code, 302)
        self.assertTrue(RideWaitlist.objects.filter(ride=self.ride, user=self.standby_user).exists())

        # Duplicate join attempt is handled gracefully
        response2 = self.client.post(reverse('join_waitlist', args=[self.ride.id]))
        self.assertEqual(RideWaitlist.objects.filter(ride=self.ride, user=self.standby_user).count(), 1)

        # Leave waitlist
        response3 = self.client.post(reverse('leave_waitlist', args=[self.ride.id]))
        self.assertEqual(response3.status_code, 302)
        self.assertFalse(RideWaitlist.objects.filter(ride=self.ride, user=self.standby_user).exists())

    def test_automatic_promotion_when_passenger_leaves(self):
        """When a confirmed passenger leaves a full ride, standby student is automatically promoted."""
        # Standby user joins waitlist
        RideWaitlist.objects.create(ride=self.ride, user=self.standby_user)
        self.assertEqual(RideWaitlist.objects.filter(ride=self.ride).count(), 1)

        # Passenger 1 leaves the ride
        self.client.force_login(self.passenger1)
        response = self.client.post(reverse('leave_ride', args=[self.ride.id]))
        self.assertEqual(response.status_code, 302)

        # Passenger 1 is no longer in ride
        self.assertFalse(RideParticipant.objects.filter(ride=self.ride, user=self.passenger1).exists())

        # Standby user is promoted to participant!
        self.assertTrue(RideParticipant.objects.filter(ride=self.ride, user=self.standby_user).exists())
        # Standby user removed from waitlist
        self.assertFalse(RideWaitlist.objects.filter(ride=self.ride, user=self.standby_user).exists())

        # Ride remains full
        self.ride.refresh_from_db()
        self.assertEqual(self.ride.status, 'FULL')
        self.assertEqual(self.ride.participant_count(), 2)

        # System chat announcement exists
        self.assertTrue(
            RideMessage.objects.filter(
                ride=self.ride,
                content__icontains='Standby Promotion'
            ).exists()
        )

    def test_automatic_promotion_when_passenger_kicked(self):
        """When a host kicks a passenger, the standby user is automatically promoted."""
        RideWaitlist.objects.create(ride=self.ride, user=self.standby_user)
        p1_entry = RideParticipant.objects.get(ride=self.ride, user=self.passenger1)

        self.client.force_login(self.host)
        self.client.post(reverse('kick_participant', args=[self.ride.id, p1_entry.id]))

        self.assertFalse(RideParticipant.objects.filter(ride=self.ride, user=self.passenger1).exists())
        self.assertTrue(RideParticipant.objects.filter(ride=self.ride, user=self.standby_user).exists())
        self.assertFalse(RideWaitlist.objects.filter(ride=self.ride, user=self.standby_user).exists())


class RideRescheduleTests(TestCase):

    def setUp(self):
        self.host = User.objects.create_user(
            username='2024BCSE210',
            enrollment_number='2024BCSE210',
            gender='M',
            phone_number='9876543210',
            password='Password123',
            verified=True,
        )
        self.ride = RideRequest.objects.create(
            creator=self.host,
            route='NIT_TO_AIRPORT',
            visibility='MIXED',
            departure_time=timezone.now() + datetime.timedelta(days=1),
            total_spots=3,
            status='OPEN',
        )
        RideParticipant.objects.create(ride=self.ride, user=self.host)

    def test_host_can_reschedule_ride(self):
        """Host can update departure time of an active ride."""
        self.client.force_login(self.host)
        new_time = timezone.localtime(timezone.now()) + datetime.timedelta(days=3)
        response = self.client.post(reverse('reschedule_ride', args=[self.ride.id]), {
            'departure_time': new_time.strftime('%Y-%m-%dT%H:%M'),
        })
        self.assertRedirects(response, reverse('ride_detail', args=[self.ride.id]))

        self.ride.refresh_from_db()
        self.assertEqual(timezone.localtime(self.ride.departure_time).date(), new_time.date())
        self.assertTrue(
            RideMessage.objects.filter(ride=self.ride, content__icontains='Ride Rescheduled').exists()
        )

    def test_reschedule_rejects_past_time(self):
        """Rescheduling to a past time is rejected with error."""
        self.client.force_login(self.host)
        past_time = timezone.now() - datetime.timedelta(hours=2)
        response = self.client.post(reverse('reschedule_ride', args=[self.ride.id]), {
            'departure_time': past_time.strftime('%Y-%m-%dT%H:%M'),
        })
        self.assertRedirects(response, reverse('ride_detail', args=[self.ride.id]))
        # Departure time unchanged
        self.ride.refresh_from_db()
        self.assertGreater(self.ride.departure_time, timezone.now())


class GenderConstraintInvariantTests(TestCase):

    def setUp(self):
        self.male_user = User.objects.create_user(
            username='2024BCSE220',
            enrollment_number='2024BCSE220',
            gender='M',
            phone_number='9876543220',
            password='Password123',
            verified=True,
        )
        self.female_user = User.objects.create_user(
            username='2024BCSE221',
            enrollment_number='2024BCSE221',
            gender='F',
            phone_number='9876543221',
            password='Password123',
            verified=True,
        )

    def test_model_level_gender_validation_on_create(self):
        """Male student cannot save Girls-Only ride directly at model level."""
        ride = RideRequest(
            creator=self.male_user,
            route='NIT_TO_AIRPORT',
            visibility='GIRLS',
            departure_time=timezone.now() + datetime.timedelta(days=1),
            total_spots=3,
        )
        with self.assertRaises(ValidationError):
            ride.clean()

    def test_model_level_gender_validation_on_join(self):
        """Male student cannot join Girls-Only ride at model level."""
        ride = RideRequest.objects.create(
            creator=self.female_user,
            route='NIT_TO_AIRPORT',
            visibility='GIRLS',
            departure_time=timezone.now() + datetime.timedelta(days=1),
            total_spots=3,
        )
        rp = RideParticipant(ride=ride, user=self.male_user)
        with self.assertRaises(ValidationError):
            rp.clean()
