"""Timing wrapper for the pinned Byparr image; run only in an isolated container.

Usage inside Byparr: /app/.venv/bin/python /tmp/instrument_media_experiment.py
POST /v1 in default mode preserves upstream behavior and adds experimentTimings.
Optional BYPARR_EXPERIMENT_WAIT=business is an initial PoC: missing business
markers consume the request budget, so this mode is not production ready.
GET /ready checks the wrapper without launching a browser. No URLs, cookies,
headers, proxy credentials, or HTML are included in the timing fields.
"""

import functools
import os
from asyncio import sleep
from contextvars import ContextVar
from time import perf_counter
from urllib.parse import urlsplit

import uvicorn
from fastapi import FastAPI, Header, HTTPException
from fastapi.responses import JSONResponse
from playwright.async_api import Browser, BrowserContext, Page, Route
from playwright.async_api import TimeoutError as PlaywrightTimeoutError
from src import endpoints, utils
from src.consts import VERSION
from src.models import LinkRequest

state: ContextVar[dict | None] = ContextVar("media_experiment", default=None)
target_url: ContextVar[str] = ContextVar("experiment_target", default="")
WAIT_MODE = os.getenv("BYPARR_EXPERIMENT_WAIT", "networkidle")


def add_time(key, started):
    current = state.get()
    if current is not None:
        current[key] = current.get(key, 0) + round((perf_counter() - started) * 1000, 3)


def timed(function, key):
    @functools.wraps(function)
    async def wrapped(*args, **kwargs):
        started = perf_counter()
        try:
            return await function(*args, **kwargs)
        finally:
            add_time(key, started)

    return wrapped


original_factory = utils.InvisiblePlaywright


class TimedBrowser:
    def __init__(self, *args, **kwargs):
        self.delegate = original_factory(*args, **kwargs)

    async def __aenter__(self):
        started = perf_counter()
        try:
            return await self.delegate.__aenter__()
        finally:
            add_time("browser_startup_ms", started)

    async def __aexit__(self, *args):
        started = perf_counter()
        try:
            return await self.delegate.__aexit__(*args)
        finally:
            add_time("browser_cleanup_ms", started)


utils.InvisiblePlaywright = TimedBrowser
Browser.new_context = timed(Browser.new_context, "context_ms")
original_new_page = BrowserContext.new_page


async def new_page(self, *args, **kwargs):
    started = perf_counter()
    try:
        page = await original_new_page(self, *args, **kwargs)
    finally:
        add_time("page_ms", started)
    current = state.get()
    if current is not None:

        def requested(request):
            counts = current.setdefault("resource_requests", {})
            kind = request.resource_type
            counts[kind] = counts.get(kind, 0) + 1

        page.on("request", requested)
    return page


BrowserContext.new_page = new_page
Page.goto = timed(Page.goto, "navigation_ms")
original_wait = Page.wait_for_load_state


async def wait_for_load_state(self, *args, **kwargs):
    load_state = kwargs.get("state") or (args[0] if args else "load")
    started = perf_counter()
    try:
        return await original_wait(self, *args, **kwargs)
    except PlaywrightTimeoutError:
        if state.get() is not None:
            state.get()[f"{load_state}_timed_out"] = True
        raise
    finally:
        add_time(f"{load_state}_ms", started)


Page.wait_for_load_state = wait_for_load_state
original_detect = endpoints.challenge_present


async def challenge_present(*args, **kwargs):
    started = perf_counter()
    try:
        detected = await original_detect(*args, **kwargs)
        if state.get() is not None:
            state.get()["challenge_detected"] = detected
        return detected
    finally:
        add_time("challenge_detection_ms", started)


endpoints.challenge_present = challenge_present
endpoints.solve_challenge = timed(endpoints.solve_challenge, "challenge_solving_ms")
original_content = endpoints.build_response_content


async def build_content(*args, **kwargs):
    current = state.get()
    if current and current.get("business_ready"):
        kwargs["page_html"] = None  # Return a fresh, verified post-wait HTML snapshot.
    return await original_content(*args, **kwargs)


endpoints.build_response_content = timed(build_content, "content_ms")
original_networkidle = endpoints._wait_for_networkidle


async def wait_for_page(dep, timer):
    url = target_url.get()
    if WAIT_MODE != "business":
        return await original_networkidle(dep, timer)
    from business_ready import detail_identity, has_business_content

    if detail_identity(url) is None:
        return await original_networkidle(dep, timer)
    started = perf_counter()
    try:
        while timer.remaining() > 0:
            html = await dep.page.content()
            if urlsplit(dep.page.url).hostname == urlsplit(
                url
            ).hostname and has_business_content(html, url):
                state.get()["business_ready"] = True
                return
            await sleep(min(0.25, timer.remaining()))
        raise PlaywrightTimeoutError("Business content unavailable before budget")
    finally:
        add_time("business_wait_ms", started)


endpoints._wait_for_networkidle = wait_for_page
original_abort = Route.abort


async def abort(self, *args, **kwargs):
    current = state.get()
    if current is not None:
        current["aborted_resources"] = current.get("aborted_resources", 0) + 1
    return await original_abort(self, *args, **kwargs)


Route.abort = abort
app = FastAPI()


@app.get("/ready")
async def ready():
    return {
        "version": VERSION,
        "experiment": "blockMedia timings",
        "waitMode": WAIT_MODE,
    }


@app.post("/v1")
async def fetch(
    request: LinkRequest,
    x_proxy_server: str | None = Header(default=None, alias="X-Proxy-Server"),
    x_proxy_username: str | None = Header(default=None, alias="X-Proxy-Username"),
    x_proxy_password: str | None = Header(default=None, alias="X-Proxy-Password"),
):
    timings = {"challenge_detected": False, "aborted_resources": 0}
    token = state.set(timings)
    target_token = target_url.set(request.url)
    started = perf_counter()
    generator = utils.get_browser(x_proxy_server, x_proxy_username, x_proxy_password)
    try:
        dep = await anext(generator)
        try:
            response = await endpoints.read_item(request, dep)
        finally:
            await generator.aclose()
        timings["server_total_ms"] = round((perf_counter() - started) * 1000, 3)
        payload = response.model_dump(by_alias=True)
        payload["experimentTimings"] = timings
        return payload
    except HTTPException as error:
        timings["server_total_ms"] = round((perf_counter() - started) * 1000, 3)
        return JSONResponse(
            status_code=error.status_code,
            content={"status": "error", "experimentTimings": timings},
        )
    finally:
        target_url.reset(target_token)
        state.reset(token)


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8191, access_log=False)
