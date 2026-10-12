"""WebSocket URL routing for the coordinate app."""

from django.urls import re_path

from .consumers import RideChatConsumer

websocket_urlpatterns = [
    re_path(r'^ws/ride/(?P<ride_id>\d+)/$', RideChatConsumer.as_asgi()),
]
