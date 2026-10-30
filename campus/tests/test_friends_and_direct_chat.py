"""Tests for Friend Direct Messaging (1-on-1 Chat), Profile Photo, and Friends List Privacy."""

from django.test import TestCase
from django.urls import reverse

from accounts.models import DirectMessage, Friendship, User


class FriendDirectChatAndPrivacyTests(TestCase):

    def setUp(self):
        self.user1 = User.objects.create_user(
            username='2024BCSE301',
            enrollment_number='2024BCSE301',
            gender='M',
            phone_number='9876543301',
            password='Password123',
            verified=True,
            show_friends_publicly=True,
        )
        self.user2 = User.objects.create_user(
            username='2024BCSE302',
            enrollment_number='2024BCSE302',
            gender='F',
            phone_number='9876543302',
            password='Password123',
            verified=True,
            show_friends_publicly=False,  # Private friends list
        )
        self.stranger = User.objects.create_user(
            username='2024BCSE303',
            enrollment_number='2024BCSE303',
            gender='M',
            phone_number='9876543303',
            password='Password123',
            verified=True,
        )

        # Make user1 and user2 friends
        Friendship.objects.create(user1=self.user1, user2=self.user2)

    def test_direct_messaging_between_friends(self):
        """Friends can exchange direct messages and view conversation history."""
        self.client.force_login(self.user1)

        # Send direct message via HTTP fallback / form
        response = self.client.post(
            reverse('direct_chat', args=[self.user2.enrollment_number]),
            {'content': 'Hello, are you taking the morning cab?'}
        )
        self.assertRedirects(response, reverse('direct_chat', args=[self.user2.enrollment_number]))

        # Verify message created
        msg = DirectMessage.objects.filter(sender=self.user1, recipient=self.user2).first()
        self.assertIsNotNone(msg)
        self.assertEqual(msg.content, 'Hello, are you taking the morning cab?')
        self.assertFalse(msg.is_read)

        # Recipient opens chat room: message is marked read
        self.client.force_login(self.user2)
        resp2 = self.client.get(reverse('direct_chat', args=[self.user1.enrollment_number]))
        self.assertEqual(resp2.status_code, 200)
        self.assertContains(resp2, 'Hello, are you taking the morning cab?')

        msg.refresh_from_db()
        self.assertTrue(msg.is_read)

    def test_strangers_cannot_access_direct_chat(self):
        """Non-friends are barred from direct chatting."""
        self.client.force_login(self.stranger)
        response = self.client.get(reverse('direct_chat', args=[self.user1.enrollment_number]))
        self.assertRedirects(response, reverse('profile', args=[self.user1.enrollment_number]))

    def test_messages_inbox_lists_conversations(self):
        """Messages inbox lists friends and displays unread count."""
        DirectMessage.objects.create(
            sender=self.user1,
            recipient=self.user2,
            content='Test unread message',
            is_read=False,
        )

        self.client.force_login(self.user2)
        response = self.client.get(reverse('messages_inbox'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.user1.enrollment_number)
        self.assertContains(response, 'Test unread message')

    def test_friend_list_privacy_toggle(self):
        """Public friend list is visible, but private friend list is hidden to non-moderator strangers."""
        self.client.force_login(self.stranger)

        # user1 has show_friends_publicly = True
        resp1 = self.client.get(reverse('profile', args=[self.user1.enrollment_number]))
        self.assertContains(resp1, self.user2.enrollment_number)

        # user2 has show_friends_publicly = False
        resp2 = self.client.get(reverse('profile', args=[self.user2.enrollment_number]))
        self.assertContains(resp2, 'Friend list is private')
        self.assertNotContains(resp2, self.user1.enrollment_number)

    def test_unfriend_user(self):
        """Users can terminate friendship."""
        self.client.force_login(self.user1)
        response = self.client.post(reverse('unfriend_user', args=[self.user2.enrollment_number]))
        self.assertRedirects(response, reverse('profile', args=[self.user2.enrollment_number]))
        self.assertFalse(Friendship.objects.filter(user1=self.user1, user2=self.user2).exists())
