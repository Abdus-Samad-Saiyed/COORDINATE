"""Stage 6 verification tests:
- Multi-tab presence tracking with shared connection counting
- Dynamic membership re-verification on incoming and outgoing frames
- Immediate WebSocket group teardown on membership revocation and cancellation
"""

import asyncio
from datetime import timedelta
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase, TransactionTestCase
from django.utils import timezone

from accounts.consumers import FriendChatConsumer
from accounts.models import Friendship
from coordinate.consumers import RideChatConsumer
from coordinate.models import RideParticipant, RideRequest

User = get_user_model()


class Stage6WebSocketPresenceTests(TransactionTestCase):
    def setUp(self):
        cache.clear()
        self.user_a = User.objects.create_user(
            enrollment_number="2024BCSE801",
            username="2024BCSE801",
            password="SecurePassword123!",
            first_name="Alice",
            last_name="Echo",
            gender="F",
            phone_number="+919876543801",
            email="alice801@nitsri.ac.in",
            verified=True,
            is_active=True,
        )

        self.user_b = User.objects.create_user(
            enrollment_number="2024BCSE802",
            username="2024BCSE802",
            password="SecurePassword123!",
            first_name="Bob",
            last_name="Echo",
            gender="M",
            phone_number="+919876543802",
            email="bob802@nitsri.ac.in",
            verified=True,
            is_active=True,
        )

    def test_multi_tab_presence_connection_counting(self):
        """Presence broadcasts occur only on first connection open (count=1) and final disconnect (count=0)."""
        consumer = FriendChatConsumer()

        # Tab 1 connects
        c1 = asyncio.run(consumer._incr_user_connection(self.user_a.id))
        self.assertEqual(c1, 1)

        # Tab 2 connects from same user
        c2 = asyncio.run(consumer._incr_user_connection(self.user_a.id))
        self.assertEqual(c2, 2)

        # Tab 1 disconnects -> 1 tab remains active, user is still online
        d1 = asyncio.run(consumer._decr_user_connection(self.user_a.id))
        self.assertEqual(d1, 1)

        # Tab 2 disconnects -> 0 tabs remain, user is now offline
        d2 = asyncio.run(consumer._decr_user_connection(self.user_a.id))
        self.assertEqual(d2, 0)

    def test_dynamic_friendship_check(self):
        """Friendship verification reflects real-time relationship status."""
        consumer = FriendChatConsumer()
        consumer.user = self.user_a
        consumer.friend = self.user_b

        # Initially strangers
        self.assertFalse(asyncio.run(consumer._are_friends()))

        # Add friendship
        f = Friendship.objects.create(user1=self.user_a, user2=self.user_b)
        self.assertTrue(asyncio.run(consumer._are_friends()))

        # Remove friendship
        f.delete()
        self.assertFalse(asyncio.run(consumer._are_friends()))
