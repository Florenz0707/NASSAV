"""Authenticated task update WebSocket consumer."""

import asyncio
import json

from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.layers import get_channel_layer
from django.contrib.sessions.models import Session
from django.utils import timezone
from asgiref.sync import async_to_sync
from loguru import logger

from .access import is_operator


class TaskConsumer(AsyncWebsocketConsumer):
    """Send task updates only while the operator's session remains active."""

    async def connect(self):
        self._joined = False
        self._initial_status_task = None
        session = self.scope.get("session")
        self._session_key = session.session_key if session else None
        if not self._session_key or not await database_sync_to_async(is_operator)(
            self.scope.get("user")
        ):
            await self.close(code=4401)
            return
        if not await self._session_active():
            await self.close(code=4401)
            return
        await self.channel_layer.group_add("task_updates", self.channel_name)
        self._joined = True
        await self.accept()
        self._initial_status_task = asyncio.create_task(self._send_queue_status())

    async def disconnect(self, close_code):
        if self._initial_status_task and not self._initial_status_task.done():
            self._initial_status_task.cancel()
        if self._joined:
            await self.channel_layer.group_discard("task_updates", self.channel_name)

    @database_sync_to_async
    def _session_active(self):
        return Session.objects.filter(
            session_key=self._session_key, expire_date__gt=timezone.now()
        ).exists()

    async def _require_session(self):
        if await self._session_active():
            return True
        await self.close(code=4401)
        return False

    async def receive(self, text_data):
        if not await self._require_session():
            return
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
            if not await self._require_session():
                return
            queue_status = await asyncio.to_thread(get_task_queue_status)
            if await self._require_session():
                await self.send(
                    text_data=json.dumps({"type": "queue_status", "data": queue_status})
                )
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("获取 WebSocket 任务队列状态失败")

    async def task_update(self, event):
        if await self._require_session():
            await self.send(
                text_data=json.dumps(
                    {"type": event["update_type"], "data": event["data"]}
                )
            )


def send_task_update(update_type: str, data: dict):
    """Send a task event to connected operator sessions."""
    channel_layer = get_channel_layer()
    if channel_layer:
        async_to_sync(channel_layer.group_send)(
            "task_updates",
            {"type": "task_update", "update_type": update_type, "data": data},
        )
