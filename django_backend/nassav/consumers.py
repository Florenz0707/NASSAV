"""Authenticated task update WebSocket consumer."""

import asyncio
import json

from asgiref.sync import async_to_sync
from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.layers import get_channel_layer
from django.contrib.sessions.models import Session
from django.utils import timezone
from django.core.exceptions import ValidationError
from loguru import logger

from .access import is_admitted
from django.conf import settings


class TaskConsumer(AsyncWebsocketConsumer):
    """Send hints only while the admitted login and browser context remain current."""

    async def connect(self):
        self._joined = False
        self._initial_status_task = None
        session = self.scope.get("session")
        user = self.scope.get("user")
        self._session_key = session.session_key if session else None
        self._context = None
        if (
            user is None
            or not self._session_key
            or not await database_sync_to_async(is_admitted)(user)
        ):
            await self.close(code=4401)
            return
        self._user_id = user.pk
        if settings.MULTI_USER_ENABLED:
            protocols = self.scope.get("subprotocols", [])
            contexts = [
                value.removeprefix("nassav.context.")
                for value in protocols
                if value.startswith("nassav.context.")
            ]
            if "nassav.tasks.v1" not in protocols or len(contexts) != 1:
                await self.close(code=4409)
                return
            self._context = contexts[0]
        rejection = await self._session_status()
        if rejection is not None:
            await self.close(code=rejection)
            return
        from .account_policy import is_legacy_operator, is_app_admin

        self._legacy = await database_sync_to_async(is_legacy_operator)(user)
        self._admin = await database_sync_to_async(is_app_admin)(user)
        self._groups = (
            ["task_updates"] if self._legacy else [f"task_user_{self._user_id}"]
        )
        if self._admin:
            self._groups.append("task_admin_updates")
        for group in self._groups:
            await self.channel_layer.group_add(group, self.channel_name)
        self._joined = True
        await self.accept(
            subprotocol="nassav.tasks.v1" if settings.MULTI_USER_ENABLED else None
        )
        if self._legacy or self._admin:
            self._initial_status_task = asyncio.create_task(self._send_queue_status())

    async def disconnect(self, close_code):
        if self._initial_status_task and not self._initial_status_task.done():
            self._initial_status_task.cancel()
        if self._joined:
            for group in self._groups:
                await self.channel_layer.group_discard(group, self.channel_name)

    @database_sync_to_async
    def _session_status(self):
        from django.contrib.auth import get_user_model

        from .session_projection import browser_identity
        from django.utils.crypto import constant_time_compare

        user = get_user_model().objects.filter(pk=self._user_id).first()
        if not Session.objects.filter(
            session_key=self._session_key, expire_date__gt=timezone.now()
        ).exists() or not is_admitted(user):
            return 4401
        if settings.MULTI_USER_ENABLED and not constant_time_compare(
            self._context or "", browser_identity(user, self._session_key) or ""
        ):
            return 4409
        return None

    async def _require_session(self):
        rejection = await self._session_status()
        if rejection is None:
            return True
        await self.close(code=rejection)
        return False

    async def receive(self, text_data):
        if not await self._require_session():
            return
        try:
            data = json.loads(text_data)
            if data.get("action") == "get_queue_status":
                if self._legacy or self._admin:
                    await self._send_queue_status()
                else:
                    await self.send(
                        text_data=json.dumps(
                            {"type": "error", "message": "需要管理员权限"}
                        )
                    )
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
            if not self._legacy:
                from .admin_presentation import queue_snapshot

                queue_status = queue_snapshot(queue_status)
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


def send_operation_hint(owner_id: int, data: dict):
    """Private operation/version hint, never broadcast through the legacy group."""
    channel_layer = get_channel_layer()
    if channel_layer:
        async_to_sync(channel_layer.group_send)(
            f"task_user_{owner_id}",
            {
                "type": "task_update",
                "update_type": "user_operation_update",
                "data": {key: data[key] for key in ("operation_id", "version")},
            },
        )


def send_task_update(update_type: str, data: dict, *, owner_id=None):
    """Send a task event to connected operator sessions."""
    channel_layer = get_channel_layer()
    if channel_layer:
        async_to_sync(channel_layer.group_send)(
            "task_updates",
            {"type": "task_update", "update_type": update_type, "data": data},
        )
        administrative = False
        if data.get("job_id"):
            from .task_models import TaskJob

            try:
                job = TaskJob.objects.filter(pk=data["job_id"]).first()
            except (ValueError, TypeError, ValidationError):
                job = None
            if job:
                owner_id = job.owner_id
                administrative = True
        safe = {
            key: data[key]
            for key in ("job_id", "job_type", "task_id", "version")
            if key in data
        }
        event = {"type": "task_update", "update_type": update_type, "data": safe}
        if owner_id is not None:
            async_to_sync(channel_layer.group_send)(f"task_user_{owner_id}", event)
        if administrative:
            async_to_sync(channel_layer.group_send)("task_admin_updates", event)
