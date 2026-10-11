"""Await bounded owned work despite repeated cancellation; callers propagate cancellation."""

import asyncio


async def finish_owned_task(task):
    """Repeated caller cancellation cannot abandon an owned bounded operation."""
    while not task.done():
        try:
            await asyncio.shield(task)
        except asyncio.CancelledError:
            continue
    return task.result()
