"""Authenticated task WebSocket behavior using an isolated session and channel layer."""

import asyncio
import time

import pytest
from channels.layers import get_channel_layer
from channels.testing import WebsocketCommunicator

from django_project.asgi import application
from nassav import tasks


@pytest.mark.django_db(transaction=True)
def test_ws_queue_status(monkeypatch, ws_headers):
    monkeypatch.setattr(
        tasks,
        "get_task_queue_status",
        lambda: {"active_tasks": [], "pending_tasks": []},
    )

    async def run():
        communicator = WebsocketCommunicator(
            application, "/nassav/ws/tasks/", headers=ws_headers
        )
        connected, _ = await communicator.connect()
        assert connected
        assert (await communicator.receive_json_from())["type"] == "queue_status"
        await communicator.send_json_to({"action": "get_queue_status"})
        assert (await communicator.receive_json_from())["type"] == "queue_status"
        await communicator.disconnect()

    asyncio.run(run())


@pytest.mark.django_db(transaction=True)
def test_slow_queue_inspection_does_not_block_concurrent_handshakes(
    monkeypatch, ws_headers
):
    """Connecting clients must not wait behind synchronous Celery inspection."""

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
            WebsocketCommunicator(application, "/nassav/ws/tasks/", headers=ws_headers)
            for _ in range(3)
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


@pytest.mark.django_db(transaction=True)
def test_download_and_scrape_events_remain_distinct(monkeypatch, ws_headers):
    """The shared channel delivers both event types without rewriting download data."""
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
        comm = WebsocketCommunicator(
            application, "/nassav/ws/tasks/", headers=ws_headers
        )
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
