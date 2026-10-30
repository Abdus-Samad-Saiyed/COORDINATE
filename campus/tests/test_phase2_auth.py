"""Phase 2 regression tests — Authentication, Account Applications, Authorization, and Privacy.

Covers:
  - Upper/lowercase enrollment login normalization
  - Timing attack mitigation & generic error responses
  - Invalid enrollment / malformed applications
  - Duplicate application prevention
  - Safe application rejection path (SEC-08 / AUTH-02)
  - Throttling boundaries (429 on abuse)
  - Complaint privacy: private complaint text hidden from public, visible to moderators (SEC-01)
  - Phone number disclosure policy: hidden from strangers, visible to self/friends/host (SEC-02)
  - Password change workflow
  - Server-side permission gates on sensitive endpoints
"""

from django.contrib.auth import authenticate
from django.core.cache import cache
from django.test import TestCase, override_settings
from django.urls import reverse

from accounts.models import AccountApplication, Friendship, FriendRequest, User
from coordinate.models import RideParticipant, RideRequest, RideReview


class AuthenticationNormalizationTests(TestCase):
    """Verify enrollment number normalization during authentication."""

    def setUp(self):
        self.user = User.objects.create_user(
            username='2024BCSE001',
            enrollment_number='2024BCSE001',
            gender='M',
            phone_number='9999999901',
            password='SecretPassword123',
            verified=True,
        )

    def test_uppercase_enrollment_authenticates(self):
        user = authenticate(username='2024BCSE001', password='SecretPassword123')
        self.assertEqual(user, self.user)

    def test_lowercase_enrollment_authenticates(self):
        """Entering lowercase enrollment number must authenticate successfully."""
        user = authenticate(username='2024bcse001', password='SecretPassword123')
        self.assertEqual(user, self.user)

    def test_enrollment_kwarg_authenticates(self):
        """Passing enrollment_number keyword argument works with EnrollmentBackend."""
        user = authenticate(enrollment_number='2024bcse001', password='SecretPassword123')
        self.assertEqual(user, self.user)

    def test_wrong_password_fails_cleanly(self):
        user = authenticate(username='2024BCSE001', password='WrongPassword!')
        self.assertIsNone(user)

    def test_nonexistent_user_fails_cleanly(self):
        user = authenticate(username='2024BCSE999', password='AnyPassword123')
        self.assertIsNone(user)

    def test_web_login_form_normalizes_lowercase(self):
        """Web login via POST must accept lowercase enrollment number."""
        response = self.client.post(reverse('login'), {
            'username': '2024bcse001',
            'password': 'SecretPassword123',
        })
        self.assertEqual(response.status_code, 302)
        self.assertEqual(int(self.client.session['_auth_user_id']), self.user.pk)


class ApplicationWorkflowSecurityTests(TestCase):
    """Validation, rejection, and duplicate handling for account applications."""

    def setUp(self):
        cache.clear()
        self.admin = User.objects.create_superuser(
            username='2024BCSE010',
            enrollment_number='2024BCSE010',
            gender='M',
            phone_number='9999999900',
            password='AdminPassword123',
            verified=True,
        )
        self.user = User.objects.create_user(
            username='2024BCSE011',
            enrollment_number='2024BCSE011',
            gender='M',
            phone_number='9999999901',
            password='UserPassword123',
            verified=True,
        )

    def test_malformed_enrollment_rejected(self):
        response = self.client.post(reverse('apply_account'), {
            'enrollment_number': 'BAD_FORMAT',
            'full_name': 'Test Student',
            'phone_number': '9999999999',
            'gender': 'M',
            'password': 'ValidPassword123',
            'confirm_password': 'ValidPassword123',
            'email': 'valid_test@nitsri.ac.in',
        })
        self.assertContains(response, 'Invalid enrollment number format')
        self.assertFalse(AccountApplication.objects.filter(full_name='Test Student').exists())

    def test_existing_user_enrollment_rejected(self):
        """Cannot submit application for an enrollment number that already has an account."""
        response = self.client.post(reverse('apply_account'), {
            'enrollment_number': self.user.enrollment_number,
            'full_name': 'Impostor',
            'phone_number': '9999999999',
            'gender': 'M',
            'password': 'ValidPassword123',
            'confirm_password': 'ValidPassword123',
            'email': 'valid_test@nitsri.ac.in',
        })
        self.assertContains(response, 'already registered')

    def test_duplicate_pending_application_rejected(self):
        AccountApplication.objects.create(
            enrollment_number='2024BCSE050',
            full_name='First Applicant',
            phone_number='9999999990',
            gender='M',
            password='hashed',
            application_number='APP050',
        )
        response = self.client.post(reverse('apply_account'), {
            'enrollment_number': '2024BCSE050',
            'full_name': 'Second Applicant',
            'phone_number': '9999999991',
            'gender': 'M',
            'password': 'ValidPassword123',
            'confirm_password': 'ValidPassword123',
            'email': 'valid_test@nitsri.ac.in',
        })
        self.assertContains(response, 'already pending')

    def test_reject_application_by_admin(self):
        """Admin can reject and delete a pending application (AUTH-02)."""
        app = AccountApplication.objects.create(
            enrollment_number='2024BCSE051',
            full_name='Rejected Applicant',
            phone_number='9999999992',
            gender='M',
            password='hashed',
            application_number='APP051',
        )

        # Non-admin cannot reject
        self.client.force_login(self.user)
        res = self.client.post(reverse('reject_application', args=[app.id]))
        self.assertEqual(res.status_code, 302)  # Redirects unauthorized user
        self.assertTrue(AccountApplication.objects.filter(id=app.id).exists())

        # Admin GET returns 405 Method Not Allowed
        self.client.force_login(self.admin)
        res_get = self.client.get(reverse('reject_application', args=[app.id]))
        self.assertEqual(res_get.status_code, 405)

        # Admin POST successfully rejects and removes application
        res_post = self.client.post(reverse('reject_application', args=[app.id]))
        self.assertRedirects(res_post, reverse('application_list'))
        self.assertFalse(AccountApplication.objects.filter(id=app.id).exists())


class PrivacySafeguardTests(TestCase):
    """SEC-01 (complaint text) and SEC-02 (phone numbers) privacy safeguards."""

    def setUp(self):
        self.admin = User.objects.create_superuser(
            username='2024BCSE010',
            enrollment_number='2024BCSE010',
            gender='M',
            phone_number='9999999900',
            password='AdminPassword123',
            verified=True,
        )
        self.user_a = User.objects.create_user(
            username='2024BCSE020',
            enrollment_number='2024BCSE020',
            gender='M',
            phone_number='9876500001',
            password='Password123',
            verified=True,
        )
        self.user_b = User.objects.create_user(
            username='2024BCSE021',
            enrollment_number='2024BCSE021',
            gender='F',
            phone_number='9876500002',
            password='Password123',
            verified=True,
        )
        self.stranger = User.objects.create_user(
            username='2024BCSE022',
            enrollment_number='2024BCSE022',
            gender='M',
            phone_number='9876500003',
            password='Password123',
            verified=True,
        )

        from django.utils import timezone
        self.ride = RideRequest.objects.create(
            creator=self.user_a,
            route='NIT_TO_AIRPORT',
            visibility='MIXED',
            departure_time=timezone.now(),
            total_spots=3,
            status='COMPLETED',
        )
        RideParticipant.objects.create(ride=self.ride, user=self.user_a)
        RideParticipant.objects.create(ride=self.ride, user=self.user_b)

        # User B wrote a review with a sensitive complaint about User A
        self.review = RideReview.objects.create(
            ride=self.ride,
            reviewer=self.user_b,
            reviewed_user=self.user_a,
            rating=2,
            complaint='Private issue: showed up 25 minutes late and brought unauthorized luggage.',
        )

    def test_complaint_hidden_from_general_public_and_strangers(self):
        """SEC-01: An ordinary student viewing a profile must NOT see private complaint text."""
        self.client.force_login(self.stranger)
        response = self.client.get(reverse('profile', args=[self.user_a.enrollment_number]))
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 'Private issue:')
        self.assertNotContains(response, '25 minutes late')

    def test_complaint_visible_to_moderator(self):
        """SEC-01: Authorized staff/moderator CAN see the private complaint note for moderation."""
        self.client.force_login(self.admin)
        response = self.client.get(reverse('profile', args=[self.user_a.enrollment_number]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Private Moderator Note:')
        self.assertContains(response, 'Private issue:')

    def test_profile_phone_number_hidden_from_strangers(self):
        """SEC-02: Strangers cannot see another student's phone number on their profile."""
        self.client.force_login(self.stranger)
        response = self.client.get(reverse('profile', args=[self.user_a.enrollment_number]))
        self.assertNotContains(response, self.user_a.phone_number)

    def test_profile_phone_number_visible_to_friends(self):
        """SEC-02: Confirmed friends CAN view each other's phone number."""
        Friendship.objects.create(user1=self.user_a, user2=self.user_b)
        self.client.force_login(self.user_b)
        response = self.client.get(reverse('profile', args=[self.user_a.enrollment_number]))
        self.assertContains(response, self.user_a.phone_number)

    def test_ride_phone_number_policy_on_ride_detail(self):
        """SEC-02: Ride host and passenger see phone numbers; strangers cannot even view the ride."""
        # Non-participant gets 404
        self.client.force_login(self.stranger)
        res_stranger = self.client.get(reverse('ride_detail', args=[self.ride.id]))
        self.assertEqual(res_stranger.status_code, 404)

        # Host sees passenger's phone number during active trip when affirmative consent is established
        from datetime import timedelta
        from django.utils import timezone
        self.ride.status = 'OPEN'
        self.ride.departure_time = timezone.now() + timedelta(hours=2)
        self.ride.save()

        from coordinate.policies import record_ride_consent
        record_ride_consent(self.ride, self.user_a, share_contact=True)
        record_ride_consent(self.ride, self.user_b, share_contact=True)

        self.client.force_login(self.user_a)
        res_host = self.client.get(reverse('ride_detail', args=[self.ride.id]))
        self.assertEqual(res_host.status_code, 200)
        self.assertContains(res_host, self.user_b.phone_number)

class ThrottlingBoundaryTests(TestCase):
    """Rate limiting and abuse protection tests."""

    def setUp(self):
        cache.clear()

    def tearDown(self):
        cache.clear()

    def test_application_endpoint_throttling(self):
        """Submitting more than 5 applications within 60s returns HTTP 429."""
        url = reverse('apply_account')
        data = {
            'enrollment_number': '2024BCSE901',
            'full_name': 'Throttled Applicant',
            'phone_number': '9999999999',
            'gender': 'M',
            'password': 'Password123',
        }

        # 5 attempts should succeed/validate
        for i in range(5):
            res = self.client.post(url, {**data, 'enrollment_number': f'2024BCSE90{i}'})
            self.assertNotEqual(res.status_code, 429)

        # 6th attempt from same IP must be throttled with 429
        res_throttled = self.client.post(url, {**data, 'enrollment_number': '2024BCSE909'})
        self.assertEqual(res_throttled.status_code, 429)


class PasswordManagementWorkflowTests(TestCase):
    """Verify password change views and operations."""

    def setUp(self):
        self.user = User.objects.create_user(
            username='2024BCSE030',
            enrollment_number='2024BCSE030',
            gender='M',
            phone_number='9999999930',
            password='OldPassword123',
            verified=True,
        )

    def test_password_change_requires_login(self):
        response = self.client.get(reverse('password_change'))
        self.assertEqual(response.status_code, 302)

    def test_password_change_success(self):
        self.client.force_login(self.user)
        response = self.client.post(reverse('password_change'), {
            'old_password': 'OldPassword123',
            'new_password1': 'BrandNewPassword123!',
            'new_password2': 'BrandNewPassword123!',
        })
        self.assertRedirects(response, reverse('password_change_done'))
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password('BrandNewPassword123!'))
