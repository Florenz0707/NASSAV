"""Bounded business-ready race for isolated experiments, not production.

Start the original idle wait immediately so missing markers add no new budget.
"""

import asyncio
from urllib.parse import urlsplit

try:
    from .business_ready import has_business_content
except ImportError:  # Standalone files copied into the pinned Byparr image.
    from business_ready import has_business_content


async def wait_bounded(page, url, timer, networkidle, *, probe_seconds=2.0):
    """Return True for a complete requested page; otherwise retain original wait."""
    budget = min(probe_seconds, timer.remaining())

    async def probe():
        if budget <= 0:
            return False
        try:
            async with asyncio.timeout(budget):
                while True:
                    html = await page.content()
                    if urlsplit(page.url).hostname == urlsplit(
                        url
                    ).hostname and has_business_content(html, url):
                        return True
                    await asyncio.sleep(0.1)
        except TimeoutError:
            return False

    idle = asyncio.create_task(networkidle())
    check = asyncio.create_task(probe())
    try:
        done, _ = await asyncio.wait((idle, check), return_when=asyncio.FIRST_COMPLETED)
        if idle in done:
            idle.result()  # Preserve upstream errors even when the check also wins.
        if check in done and check.result():
            return True
        await idle
        return False
    finally:
        for task in (idle, check):
            if not task.done():
                task.cancel()
        await asyncio.gather(idle, check, return_exceptions=True)
