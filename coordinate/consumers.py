"""
WebSocket consumer for ride chat.

Each ride has its own channel group: 'ride_<ride_id>'
Messages are saved to the DB and broadcast to all connected participants.
"""

import json

from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncWebsocketConsumer
from django.utils import timezone


class RideChatConsumer(AsyncWebsocketConsumer):

    async def connect(self):
        self.ride_id = self.scope['url_route']['kwargs']['ride_id']
        self.group_name = f'ride_{self.ride_id}'
        self.user = self.scope['user']

        if not self.user.is_authenticated:
            await self.close()
            return

        if not await self._is_participant():
            await self.close()
            return

        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()

    async def disconnect(self, close_code):
        await self.channel_layer.group_discard(self.group_name, self.channel_name)

    async def receive(self, text_data):
        try:
            data = json.loads(text_data)
        except json.JSONDecodeError:
            return

        content = (data.get('content') or '').strip()
        if not content or len(content) > 1000:
            return

        if not await self._can_send():
            return

        message = await self._save_message(content)

        await self.channel_layer.group_send(
            self.group_name,
            {
                'type': 'chat.message',
                'author': self.user.enrollment_number,
                'content': message.content,
                'timestamp': message.created_at.strftime('%b %d, %H:%M'),
            },
        )

    async def chat_message(self, event):
        """Relay a group message to this specific WebSocket connection."""
        await self.send(text_data=json.dumps({
            'author': event['author'],
            'content': event['content'],
            'timestamp': event['timestamp'],
            'is_self': event['author'] == self.user.enrollment_number,
        }))

    # ------------------------------------------------------------------
    # DB helpers (run in thread pool via database_sync_to_async)
    # ------------------------------------------------------------------

    @database_sync_to_async
    def _is_participant(self) -> bool:
        from coordinate.models import RideParticipant
        return RideParticipant.objects.filter(
            ride_id=self.ride_id,
            user=self.user,
        ).exists()

    @database_sync_to_async
    def _can_send(self) -> bool:
        from coordinate.models import RideRequest
        try:
            ride = RideRequest.objects.get(id=self.ride_id)
            return ride.status != 'COMPLETED' and ride.departure_time > timezone.now()
        except RideRequest.DoesNotExist:
            return False

    @database_sync_to_async
    def _save_message(self, content: str):
        from coordinate.models import RideMessage
        return RideMessage.objects.create(
            ride_id=self.ride_id,
            author=self.user,
            content=content,
        )
