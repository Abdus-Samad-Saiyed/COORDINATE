"""WebSocket consumer for 1-on-1 direct messaging between friends.

Path: /ws/chat/direct/<friend_enrollment>/
Channel group: direct_chat_<min_id>_<max_id>
Features:
  - Strict friendship verification on connection
  - Real-time typing indicators
  - Online presence broadcasts
  - Message persistence in DirectMessage model
"""

import json
from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncWebsocketConsumer
from django.db.models import Q


class FriendChatConsumer(AsyncWebsocketConsumer):

    async def connect(self):
        self.user = self.scope.get('user')
        if not self.user or not self.user.is_authenticated:
            await self.close()
            return

        self.friend_enrollment = self.scope['url_route']['kwargs']['friend_enrollment'].strip().upper()
        self.friend = await self._get_friend_user()

        if not self.friend or not await self._are_friends():
            await self.close()
            return

        # Canonical group naming
        u1_id, u2_id = sorted([self.user.id, self.friend.id])
        self.group_name = f'direct_chat_{u1_id}_{u2_id}'

        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()

        # Announce online presence to the friend if not hidden
        user_hides_online = await self._user_hides_online()
        if not user_hides_online:
            await self.channel_layer.group_send(
                self.group_name,
                {
                    'type': 'chat.presence',
                    'sender': self.user.enrollment_number,
                    'status': 'online',
                }
            )

    async def disconnect(self, close_code):
        if hasattr(self, 'group_name'):
            user_hides_online = await self._user_hides_online()
            if not user_hides_online:
                await self.channel_layer.group_send(
                    self.group_name,
                    {
                        'type': 'chat.presence',
                        'sender': self.user.enrollment_number,
                        'status': 'offline',
                    }
                )
            await self.channel_layer.group_discard(self.group_name, self.channel_name)

    async def receive(self, text_data=None, bytes_data=None):
        if bytes_data is not None or not text_data:
            return

        try:
            data = json.loads(text_data)
        except (json.JSONDecodeError, TypeError):
            return

        event_type = data.get('type')

        # Real-time typing indicator (suppressed if user hid online status)
        if event_type == 'typing':
            user_hides_online = await self._user_hides_online()
            if not user_hides_online:
                is_typing = bool(data.get('is_typing', False))
                await self.channel_layer.group_send(
                    self.group_name,
                    {
                        'type': 'chat.typing',
                        'sender': self.user.enrollment_number,
                        'is_typing': is_typing,
                    }
                )
            return

        # Chat message
        if event_type == 'message':
            content = (data.get('content') or '').strip()
            if not content or len(content) > 2000:
                return

            msg = await self._save_direct_message(content)

            await self.channel_layer.group_send(
                self.group_name,
                {
                    'type': 'chat.direct_message',
                    'message_id': msg.id,
                    'sender': self.user.enrollment_number,
                    'content': msg.content,
                    'timestamp': msg.created_at.strftime('%b %d, %H:%M'),
                }
            )

            await self.send(text_data=json.dumps({
                'type': 'ack',
                'status': 'sent',
                'message_id': msg.id,
            }))

    # ------------------------------------------------------------------
    # Group handlers
    # ------------------------------------------------------------------

    async def chat_direct_message(self, event):
        await self.send(text_data=json.dumps({
            'type': 'message',
            'message_id': event['message_id'],
            'sender': event['sender'],
            'content': event['content'],
            'timestamp': event['timestamp'],
            'is_self': event['sender'] == self.user.enrollment_number,
        }))

    async def chat_typing(self, event):
        if event['sender'] != self.user.enrollment_number:
            await self.send(text_data=json.dumps({
                'type': 'typing',
                'sender': event['sender'],
                'is_typing': event['is_typing'],
            }))

    async def chat_presence(self, event):
        if event['sender'] != self.user.enrollment_number:
            await self.send(text_data=json.dumps({
                'type': 'presence',
                'sender': event['sender'],
                'status': event['status'],
            }))

    # ------------------------------------------------------------------
    # Database queries
    # ------------------------------------------------------------------

    @database_sync_to_async
    def _get_friend_user(self):
        from accounts.models import User
        try:
            return User.objects.get(enrollment_number=self.friend_enrollment)
        except User.DoesNotExist:
            return None

    @database_sync_to_async
    def _are_friends(self) -> bool:
        from accounts.models import Friendship
        return Friendship.objects.filter(
            Q(user1=self.user, user2=self.friend) |
            Q(user1=self.friend, user2=self.user)
        ).exists()

    @database_sync_to_async
    def _save_direct_message(self, content: str):
        from accounts.models import DirectMessage
        return DirectMessage.objects.create(
            sender=self.user,
            recipient=self.friend,
            content=content,
        )

    @database_sync_to_async
    def _user_hides_online(self) -> bool:
        from accounts.models import User
        try:
            return User.objects.filter(id=self.user.id, hide_online_status=True).exists()
        except Exception:
            return False
