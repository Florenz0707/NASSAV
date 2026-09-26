"""
WebSocket consumers for real-time task notifications
"""

import asyncio
import json

from asgiref.sync import async_to_sync
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.layers import get_channel_layer
from loguru import logger


class TaskConsumer(AsyncWebsocketConsumer):
    """
    WebSocket consumer for task status updates

    Frontend can connect to this consumer to receive real-time updates
    about task queue status and task completion notifications.
    """

    async def connect(self):
        """Handle WebSocket connection"""
        # Join task status group
        await self.channel_layer.group_add("task_updates", self.channel_name)

        await self.accept()

        # Celery inspect is synchronous and can take seconds. Let the handshake
        # finish before fetching the initial snapshot in a worker thread.
        self._initial_status_task = asyncio.create_task(self._send_queue_status())

    async def disconnect(self, close_code):
        """Handle WebSocket disconnection"""
        # Leave task status group
        if self._initial_status_task and not self._initial_status_task.done():
            self._initial_status_task.cancel()
        await self.channel_layer.group_discard("task_updates", self.channel_name)

    async def receive(self, text_data):
        """
        Handle messages from WebSocket (if needed)
        Currently just returns current queue status
        """
        try:
            data = json.loads(text_data)
            if data.get("action") == "get_queue_status":
                await self._send_queue_status()
        except json.JSONDecodeError:
            await self.send(
                text_data=json.dumps({"type": "error", "message": "Invalid JSON"})
            )

    async def _send_queue_status(self):
        from .tasks import get_task_queue_status

        try:
            queue_status = await asyncio.to_thread(get_task_queue_status)
            await self.send(
                text_data=json.dumps({"type": "queue_status", "data": queue_status})
            )
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("获取 WebSocket 任务队列状态失败")

    async def task_update(self, event):
        """
        Handle task update messages from channel layer
        Called when a task status changes
        """
        await self.send(
            text_data=json.dumps({"type": event["update_type"], "data": event["data"]})
        )


def send_task_update(update_type: str, data: dict):
    """
    Send task update to all connected WebSocket clients

    Args:
        update_type: Type of update ('task_started', 'task_completed', 'task_failed', 'queue_status')
        data: Task data to send
    """
    channel_layer = get_channel_layer()
    if channel_layer:
        async_to_sync(channel_layer.group_send)(
            "task_updates",
            {"type": "task_update", "update_type": update_type, "data": data},
        )
