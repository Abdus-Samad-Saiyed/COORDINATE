from django.contrib.auth import authenticate
from django.test import TestCase
from django.urls import reverse

from .models import AccountApplication, FriendRequest, Friendship, User


class AccountWorkflowTests(TestCase):

    def setUp(self):

        self.admin = User.objects.create_superuser(
            username='Admin',
            enrollment_number='2024BCSE010',
            gender='M',
            phone_number='9999999900',
            password='password123'
        )

        self.user = User.objects.create_user(
            username='User',
            enrollment_number='2024BCSE011',
            gender='M',
            phone_number='9999999901',
            password='password123'
        )

        self.friend = User.objects.create_user(
            username='Friend',
            enrollment_number='2024BCSE012',
            gender='F',
            phone_number='9999999902',
            password='password123'
        )

    def test_valid_application_normalizes_and_hashes_password(self):

        response = self.client.post(
            reverse('apply_account'),
            {
                'enrollment_number': '2024bcse013',
                'full_name': 'Applicant',
                'phone_number': '9999999903',
                'gender': 'M',
                'password': 'password12345',
            }
        )

        self.assertEqual(response.status_code, 200)

        application = AccountApplication.objects.get()

        self.assertEqual(
            application.enrollment_number,
            '2024BCSE013'
        )
        self.assertNotEqual(
            application.password,
            'password12345'
        )

    def test_invalid_and_duplicate_applications_are_rejected(self):

        response = self.client.post(
            reverse('apply_account'),
            {
                'enrollment_number': 'bad',
                'full_name': 'Applicant',
                'phone_number': '9999999903',
                'gender': 'M',
                'password': 'password12345',
            }
        )

        self.assertContains(
            response,
            'Invalid enrollment number format'
        )

        AccountApplication.objects.create(
            enrollment_number='2024BCSE013',
            full_name='Applicant',
            phone_number='9999999903',
            gender='M',
            password='hashed',
            application_number='APP001'
        )

        response = self.client.post(
            reverse('apply_account'),
            {
                'enrollment_number': '2024BCSE013',
                'full_name': 'Applicant',
                'phone_number': '9999999903',
                'gender': 'M',
                'password': 'password12345',
            }
        )

        self.assertContains(
            response,
            'already pending'
        )

    def test_approval_requires_post_and_admin(self):

        application = AccountApplication.objects.create(
            enrollment_number='2024BCSE013',
            full_name='Applicant',
            phone_number='9999999903',
            gender='M',
            password='pbkdf2_sha256$1000000$example$hash',
            application_number='APP001'
        )

        self.client.force_login(self.user)

        self.assertEqual(
            self.client.post(
                reverse('approve_application', args=[application.id])
            ).status_code,
            302
        )

        self.assertTrue(
            AccountApplication.objects.filter(
                id=application.id
            ).exists()
        )

        self.client.force_login(self.admin)

        self.assertEqual(
            self.client.get(
                reverse('approve_application', args=[application.id])
            ).status_code,
            405
        )

        self.client.post(
            reverse('approve_application', args=[application.id])
        )

        self.assertTrue(
            User.objects.filter(
                enrollment_number='2024BCSE013'
            ).exists()
        )
        self.assertFalse(
            AccountApplication.objects.filter(
                id=application.id
            ).exists()
        )

    def test_enrollment_number_authentication(self):

        user = authenticate(
            enrollment_number='2024BCSE011',
            password='password123'
        )

        self.assertEqual(user, self.user)

    def test_friend_request_requires_post_and_accepts_once(self):

        self.client.force_login(self.user)

        self.assertEqual(
            self.client.get(
                reverse(
                    'send_friend_request',
                    args=[self.friend.enrollment_number]
                )
            ).status_code,
            405
        )

        self.client.post(
            reverse(
                'send_friend_request',
                args=[self.friend.enrollment_number]
            )
        )
        self.client.post(
            reverse(
                'send_friend_request',
                args=[self.friend.enrollment_number]
            )
        )

        self.assertEqual(FriendRequest.objects.count(), 1)

        friend_request = FriendRequest.objects.get()

        self.client.force_login(self.friend)
        self.client.post(
            reverse(
                'accept_friend_request',
                args=[friend_request.id]
            )
        )

        self.assertEqual(Friendship.objects.count(), 1)
        self.assertEqual(FriendRequest.objects.count(), 0)
