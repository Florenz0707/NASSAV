"""Regression checks for bounded business polling and original-wait fallback."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from scripts.byparr.bounded_wait import wait_bounded

URL = "https://jable.tv/videos/test-001/"
HTML = '<title>TEST-001 Title</title><meta property="og:image" content="cover"><script>var hlsUrl = "playlist";</script>'


def test_valid_page_returns_early_and_cleans_up_idle_task():
    async def run():
        stopped = asyncio.Event()

        async def idle():
            try:
                await asyncio.Future()
            finally:
                stopped.set()

        page = SimpleNamespace(url=URL, content=AsyncMock(return_value=HTML))
        assert await wait_bounded(
            page, URL, SimpleNamespace(remaining=lambda: 60), idle
        )
        assert stopped.is_set()

    asyncio.run(run())


@pytest.mark.parametrize(
    "html,host", [("<title>Not found</title>", URL), (HTML, "https://wrong.test/")]
)
def test_absent_marker_or_wrong_host_retains_original_wait(html, host):
    async def run():
        finished = asyncio.Event()

        async def idle():
            await asyncio.sleep(0.02)
            finished.set()

        page = SimpleNamespace(url=host, content=AsyncMock(return_value=html))
        assert not await wait_bounded(
            page, URL, SimpleNamespace(remaining=lambda: 60), idle
        )
        assert finished.is_set()

    asyncio.run(run())


def test_slow_content_is_bounded_and_original_wait_runs_once():
    async def run():
        started, stopped = asyncio.Event(), asyncio.Event()
        calls = 0

        async def content():
            started.set()
            try:
                await asyncio.Future()
            finally:
                stopped.set()

        async def idle():
            nonlocal calls
            calls += 1
            await started.wait()
            await asyncio.sleep(0.02)

        page = SimpleNamespace(url=URL, content=content)
        result = await asyncio.wait_for(
            wait_bounded(
                page,
                URL,
                SimpleNamespace(remaining=lambda: 60),
                idle,
                probe_seconds=0.005,
            ),
            0.2,
        )
        assert not result
        assert calls == 1
        assert stopped.is_set()

    asyncio.run(run())


def test_request_cancellation_closes_background_tasks():
    async def run():
        started, stopped = asyncio.Event(), asyncio.Event()

        async def idle():
            started.set()
            try:
                await asyncio.Future()
            finally:
                stopped.set()

        page = SimpleNamespace(url=URL, content=AsyncMock(return_value="partial"))
        task = asyncio.create_task(
            wait_bounded(page, URL, SimpleNamespace(remaining=lambda: 60), idle)
        )
        await started.wait()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert stopped.is_set()

    asyncio.run(run())


def test_exhausted_budget_and_original_error_are_not_hidden():
    async def run():
        page = SimpleNamespace(url=URL, content=AsyncMock(return_value=HTML))
        idle = AsyncMock(side_effect=RuntimeError("original wait failure"))
        with pytest.raises(RuntimeError, match="original wait failure"):
            await wait_bounded(page, URL, SimpleNamespace(remaining=lambda: 0), idle)
        page.content.assert_not_awaited()

    asyncio.run(run())


def test_successful_snapshot_does_not_hide_simultaneous_original_error():
    async def run():
        page = SimpleNamespace(url=URL, content=AsyncMock(return_value=HTML))
        idle = AsyncMock(side_effect=RuntimeError("original wait failure"))
        with pytest.raises(RuntimeError, match="original wait failure"):
            await wait_bounded(page, URL, SimpleNamespace(remaining=lambda: 60), idle)

    asyncio.run(run())
