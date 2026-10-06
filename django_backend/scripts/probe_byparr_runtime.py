"""Real API/worker checks against disposable PostgreSQL and Redis only.

Usage in disposable runtime: python probe_byparr_runtime.py --phase serial|mixed
  --avids AVID AVID ...
Run a real scrape worker at concurrency 1 for serial and 2 for mixed.
No production stores are accepted. Output omits cookies, capabilities and URLs.
"""

import argparse
import asyncio
import json
import os
from time import monotonic
from urllib.parse import urlsplit


def emit(**fields):
    print(json.dumps(fields, sort_keys=True), flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--phase", choices=("serial", "mixed"), required=True)
    parser.add_argument("--avids", nargs="+", required=True)
    args = parser.parse_args()
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "django_project.settings")
    import django

    django.setup()
    import requests
    from django.conf import settings
    from django.contrib.auth import get_user_model
    from loguru import logger
    from nassav.models import AVResource, SourceCookie
    from rest_framework.test import APIClient

    logger.remove()
    if (
        settings.DATABASES["default"]["HOST"] != "nassav-wait-postgres"
        or urlsplit(settings.REDIS_URL).hostname != "nassav-wait-redis"
        or str(settings.RESOURCE_DIR) != "/tmp/acceptance-resource"
    ):
        parser.error("Disposable acceptance stores and resource directory required")
    user, _ = get_user_model().objects.get_or_create(
        username=settings.NASSAV_OPERATOR_USERNAME
    )
    client = APIClient()
    client.force_login(user)
    headers = [
        (b"host", b"localhost"),
        (b"origin", b"http://localhost"),
        (
            b"cookie",
            f"{settings.SESSION_COOKIE_NAME}={client.cookies[settings.SESSION_COOKIE_NAME].value}".encode(),
        ),
    ]
    av_ids = [s.upper() for s in args.avids]
    for avid in av_ids:
        AVResource.objects.get_or_create(
            avid=avid,
            defaults={"source": "Jable", "original_title": "Isolated acceptance"},
        )
    control = requests.Session()
    control.trust_env = False
    base = settings.BROWSER_FETCH_CONFIG.url.rstrip("/")

    def stats():
        return control.get(base + "/experiment-stats", timeout=5).json()

    def cookie_check():
        posted = client.post(
            "/nassav/api/source/cookie",
            {"source": "Jable", "cookie": "acceptance=manual"},
            format="json",
        )
        assert posted.status_code == 200
        row = SourceCookie.objects.filter(source_name__iexact="Jable").first()
        assert row and not row.user_agent and not row.egress_profile
        cleared = client.delete("/nassav/api/source/cookie?source=Jable")
        assert cleared.status_code == 200
        row.refresh_from_db()
        assert not row.cookie and not row.user_agent
        automatic = client.post(
            "/nassav/api/source/cookie",
            {"source": "Jable", "auto": True},
            format="json",
        )
        emit(
            stage="cookie_api",
            phase=args.phase,
            manual_status=posted.status_code,
            clear_status=cleared.status_code,
            automatic_status=automatic.status_code,
        )
        row.refresh_from_db()
        paired = bool(row.cookie and row.user_agent and row.egress_profile)
        emit(stage="cookie_pairing", phase=args.phase, paired=paired)
        listed = client.get("/nassav/api/source/cookie")
        assert listed.status_code == 200
        return automatic.status_code == 200 and paired

    def submit(avid):
        started = monotonic()
        response = client.post(
            "/nassav/api/resource/jobs",
            {
                "action": "refresh",
                "avid": avid,
                "refresh_metadata": False,
                "refresh_m3u8": True,
            },
            format="json",
        )
        assert response.status_code == 202
        result = response.json()["data"]
        emit(
            stage="submit",
            phase=args.phase,
            sample=avid,
            status=response.status_code,
            elapsed_ms=round((monotonic() - started) * 1000),
        )
        return result

    def status(job):
        response = client.get(
            job["status_url"], HTTP_X_RESOURCE_JOB_TOKEN=job["status_token"]
        )
        assert response.status_code == 200
        return response.json()["data"]

    def sync_refresh(avid):
        started = monotonic()
        response = client.post(
            f"/nassav/api/resource/refresh/{avid}",
            {"refresh_metadata": False, "refresh_m3u8": True},
            format="json",
        )
        emit(
            stage="sync_api",
            phase=args.phase,
            sample=avid,
            status=response.status_code,
            elapsed_ms=round((monotonic() - started) * 1000),
        )
        assert response.status_code == 200

    async def run():
        from channels.testing import WebsocketCommunicator
        from django_project.asgi import application

        comm = WebsocketCommunicator(application, "/nassav/ws/tasks/", headers=headers)
        connected, _ = await comm.connect(timeout=5)
        assert connected
        events = []
        stop = asyncio.Event()

        async def collect():
            while not stop.is_set():
                try:
                    events.append(await comm.receive_json_from(timeout=180))
                except asyncio.TimeoutError:
                    return

        listener = asyncio.create_task(collect())
        try:
            before = stats()["requests"]
            cookie_valid = True
            if args.phase == "serial":
                cookie_valid = await asyncio.to_thread(cookie_check)
            jobs = [await asyncio.to_thread(submit, avid) for avid in av_ids]
            sync = (
                asyncio.create_task(asyncio.to_thread(sync_refresh, av_ids[-1]))
                if args.phase == "mixed"
                else None
            )
            deadline = monotonic() + 180
            pending = list(jobs)
            while pending and monotonic() < deadline:
                remaining = []
                for job in pending:
                    snapshot = await asyncio.to_thread(status, job)
                    if snapshot["state"] in {"succeeded", "failed"}:
                        emit(
                            stage="terminal",
                            phase=args.phase,
                            sample=snapshot["avid"],
                            state=snapshot["state"],
                            error_code=snapshot["error_code"],
                        )
                        assert snapshot["state"] == "succeeded"
                    else:
                        remaining.append(job)
                pending = remaining
                if pending:
                    await asyncio.sleep(0.2)
            assert not pending
            if sync:
                await sync
            await asyncio.sleep(0.3)
            terminal_events = sum(
                e.get("type") == "scrape_job_update"
                and e.get("data", {}).get("state") == "succeeded"
                for e in events
            )
            assert terminal_events >= len(jobs)
            emit(
                stage="runtime_summary",
                phase=args.phase,
                tasks=len(jobs),
                terminal_websocket_events=terminal_events,
                browser_calls=stats()["requests"] - before,
                valid=cookie_valid,
            )
            return cookie_valid
        finally:
            stop.set()
            listener.cancel()
            await asyncio.gather(listener, return_exceptions=True)
            await comm.disconnect()

    try:
        valid = asyncio.run(run())
    except Exception as error:
        emit(stage="runtime_failure", phase=args.phase, error_type=type(error).__name__)
        return 2
    for avid in av_ids:
        assert AVResource.objects.get(avid=avid).m3u8
    return 0 if valid else 2


if __name__ == "__main__":
    raise SystemExit(main())
