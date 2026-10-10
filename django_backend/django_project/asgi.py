"""
ASGI config for django_project project.
"""

import os

from channels.auth import AuthMiddlewareStack
from channels.routing import ProtocolTypeRouter, URLRouter
from channels.security.websocket import AllowedHostsOriginValidator
from django.core.asgi import get_asgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "django_project.settings")

# Initialize Django ASGI application early to ensure the AppRegistry
# is populated before importing code that may import ORM models.
django_asgi_app = get_asgi_application()

import logging
from nassav.playback.access_log import PlaybackAccessFilter

logging.getLogger("uvicorn.access").addFilter(PlaybackAccessFilter())

# Import routing after Django is initialized
from nassav.routing import websocket_urlpatterns
from nassav.ws_origin import SameOriginWebSocketValidator

application = ProtocolTypeRouter(
    {
        "http": django_asgi_app,
        "websocket": AllowedHostsOriginValidator(
            SameOriginWebSocketValidator(
                AuthMiddlewareStack(URLRouter(websocket_urlpatterns))
            )
        ),
    }
)
