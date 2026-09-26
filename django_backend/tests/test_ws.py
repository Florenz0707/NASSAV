#!/usr/bin/env python
"""
WebSocket 连接测试

功能：
1. 测试 WebSocket 连接建立
2. 测试任务队列状态查询（通过 WebSocket）
3. 验证 WebSocket 消息格式
4. 测试异步通信机制

运行方式：
    # 运行所有测试
    python manage.py test tests.test_ws

    # 运行单个测试
    python manage.py test tests.test_ws.WebSocketTest.test_ws_queue_status

    # 使用 pytest
    pytest tests/test_ws.py -v

注意：
    - 需要 Redis 服务运行
    - 需要 Channels 和 channels-redis 已安装
    - 测试使用 TransactionTestCase 以支持异步操作
"""

import asyncio

from channels.testing import WebsocketCommunicator
from django.test import TransactionTestCase
from unittest.mock import patch
from django_project.asgi import application


class WebSocketTest(TransactionTestCase):
    """Basic WebSocket skeleton test for task consumer."""

    async def _run(self):
        comm = WebsocketCommunicator(application, "/nassav/ws/tasks/")
        connected, _ = await comm.connect()
        self.assertTrue(connected)
        # request queue status
        await comm.send_json_to({"action": "get_queue_status"})
        msg = await comm.receive_json_from()
        # expecting a dict with type/ data
        self.assertIn("type", msg)
        await comm.disconnect()

    def test_ws_queue_status(self):
        empty = {
            "active_tasks": [],
            "pending_tasks": [],
            "active_count": 0,
            "pending_count": 0,
            "total_count": 0,
        }
        with patch("nassav.tasks.get_task_queue_status", return_value=empty):
            asyncio.run(self._run())


def test_slow_queue_inspection_does_not_block_concurrent_handshakes(monkeypatch):
    """Connecting clients must not wait behind synchronous Celery inspection."""
    import time
    from nassav import tasks

    def slow_status():
        time.sleep(0.2)
        return {
            "active_tasks": [],
            "pending_tasks": [],
            "active_count": 0,
            "pending_count": 0,
            "total_count": 0,
        }

    monkeypatch.setattr(tasks, "get_task_queue_status", slow_status)

    async def run():
        communicators = [
            WebsocketCommunicator(application, "/nassav/ws/tasks/") for _ in range(3)
        ]
        try:
            started = time.perf_counter()
            connected = await asyncio.gather(
                *(comm.connect(timeout=0.3) for comm in communicators)
            )
            elapsed = time.perf_counter() - started
            assert all(ok for ok, _ in connected)
            assert elapsed < 0.3
        finally:
            await asyncio.gather(
                *(comm.disconnect() for comm in communicators), return_exceptions=True
            )

    asyncio.run(run())


def test_download_and_scrape_events_remain_distinct(monkeypatch, settings):
    """The shared channel delivers both event types without rewriting download data."""
    from channels.layers import get_channel_layer
    from nassav import tasks

    settings.CHANNEL_LAYERS = {
        "default": {"BACKEND": "channels.layers.InMemoryChannelLayer"}
    }
    monkeypatch.setattr(
        tasks,
        "get_task_queue_status",
        lambda: {
            "active_tasks": [],
            "pending_tasks": [],
            "active_count": 0,
            "pending_count": 0,
            "total_count": 0,
        },
    )

    async def run():
        comm = WebsocketCommunicator(application, "/nassav/ws/tasks/")
        connected, _ = await comm.connect()
        assert connected
        await comm.receive_json_from()
        channel = get_channel_layer()
        try:
            await channel.group_send(
                "task_updates",
                {
                    "type": "task_update",
                    "update_type": "progress_update",
                    "data": {"task_id": "download-1", "percent": 42},
                },
            )
            download = await comm.receive_json_from()
            assert download == {
                "type": "progress_update",
                "data": {"task_id": "download-1", "percent": 42},
            }
            await channel.group_send(
                "task_updates",
                {
                    "type": "task_update",
                    "update_type": "scrape_job_update",
                    "data": {
                        "task_id": "scrape-1",
                        "job_type": "scrape",
                        "state": "running",
                        "stage": "saving",
                    },
                },
            )
            scrape = await comm.receive_json_from()
            assert scrape["type"] == "scrape_job_update"
            assert scrape["data"]["stage"] == "saving"
        finally:
            await comm.disconnect()

    asyncio.run(run())
