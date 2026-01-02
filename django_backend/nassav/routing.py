"""
WebSocket routing configuration
"""
from django.urls import re_path

from . import consumers

websocket_urlpatterns = [
    re_path(r"nassav/ws/tasks/$", consumers.TaskConsumer.as_asgi()),
]
