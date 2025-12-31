import asyncio
import json
from channels.testing import WebsocketCommunicator
from django.test import TransactionTestCase

from django_project.asgi import application


class WebSocketTest(TransactionTestCase):
    """Basic WebSocket skeleton test for task consumer."""

    async def _run(self):
        comm = WebsocketCommunicator(application, '/nassav/ws/tasks/')
        connected, _ = await comm.connect()
        self.assertTrue(connected)
        # request queue status
        await comm.send_json_to({'action': 'get_queue_status'})
        msg = await comm.receive_json_from()
        # expecting a dict with type/ data
        self.assertIn('type', msg)
        await comm.disconnect()

    def test_ws_queue_status(self):
        asyncio.get_event_loop().run_until_complete(self._run())
