"""Read-only paired blockMedia experiment against an isolated timing instance.

Usage in API container: python probe_byparr_media.py --window W1 --count 20
  --base-url http://nassav-byparr-media-experiment:8191
Second window: add --samples-file /tmp/media-w1.jsonl to reuse the exact AVIDs.
Output is sanitized JSONL. No Cookie, Redis, task, or configuration writes.
The experiment stops on a valid baseline paired with an invalid candidate page.
Wait PoC: --ready-base-url http://nassav-byparr-ready-experiment:8191
keeps blockMedia=false in both arms; --source Jable restricts the comparison.
"""

import argparse
import json
from math import ceil
import os
import re
from statistics import median
from time import perf_counter, sleep

import requests


def arm_order(index, window):
    return (False, True) if (index + (window == "W2")) % 2 else (True, False)


def summarize(rows):
    """Include failed attempts in latency; never silently drop slow failures."""
    times = sorted(row["client_ms"] for row in rows)
    if not times:
        return {"attempts": 0, "valid": 0}
    stages = {
        key for row in rows for key in row.get("timings", {}) if key.endswith("_ms")
    }
    return {
        "attempts": len(rows),
        "valid": sum(row["valid"] for row in rows),
        "p50_ms": median(times),
        "p95_ms": times[ceil(len(times) * 0.95) - 1],
        "stage_medians_ms": {
            key: median(
                row["timings"][key] for row in rows if key in row.get("timings", {})
            )
            for key in sorted(stages)
        },
    }


class MediaSession(requests.Session):
    def __init__(self):
        super().__init__()
        self.trust_env = False
        self.block_media = False
        self.timings = {}

    def post(self, url, **kwargs):
        kwargs["json"] = {**kwargs["json"], "blockMedia": self.block_media}
        self.timings = {}
        response = super().post(url, **kwargs)
        try:
            data = response.json()
            if isinstance(data, dict) and isinstance(
                data.get("experimentTimings"), dict
            ):
                self.timings = data["experimentTimings"]
        except ValueError:
            pass
        return response


def emit(**fields):
    print(json.dumps(fields, ensure_ascii=False, sort_keys=True), flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--window", required=True, choices=("W1", "W2"))
    parser.add_argument("--count", type=int, default=20)
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--samples-file")
    parser.add_argument("--source", choices=("both", "Jable", "MissAV"), default="both")
    parser.add_argument(
        "--ready-base-url", help="Optional separate business-wait PoC instance"
    )
    args = parser.parse_args()
    if not 1 <= args.count <= 100:
        parser.error("--count must be between 1 and 100")

    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "django_project.settings")
    import django

    django.setup()
    from django.conf import settings
    from nassav.page_fetching import PageFetchService
    from nassav.page_fetching.browser import ByparrPageClient
    from nassav.source.Jable import Jable
    from nassav.source.MissAV import MissAV
    from scripts.probe_p5_jable import detail_paths
    from scripts.probe_p5_missav import detail_candidates

    proxy = settings.PROXY_URL if settings.PROXY_ENABLED else None
    if not proxy:
        parser.error("Use the configured API proxy route")
    client = ByparrPageClient(args.base_url, proxy_url=proxy)
    session = MediaSession()
    client._session = session
    ready = session.get(args.base_url.rstrip("/") + "/ready", timeout=5)
    if ready.status_code != 200 or ready.json().get("version") != "3.0.4":
        parser.error("Use the isolated v3.0.4 timing instance")
    candidate_client, candidate_session = client, session
    if args.ready_base_url:
        candidate_client = ByparrPageClient(args.ready_base_url, proxy_url=proxy)
        candidate_session = MediaSession()
        candidate_client._session = candidate_session
        candidate_ready = candidate_session.get(
            args.ready_base_url.rstrip("/") + "/ready", timeout=5
        )
        if (
            candidate_ready.status_code != 200
            or candidate_ready.json().get("version") != "3.0.4"
            or candidate_ready.json().get("waitMode") != "business"
            or ready.json().get("waitMode", "networkidle") != "networkidle"
        ):
            parser.error(
                "Wait comparison needs separate networkidle/business instances"
            )

    def select_arm(candidate):
        active_client = candidate_client if candidate else client
        active_session = candidate_session if candidate else session
        active_session.block_media = False if args.ready_base_url else candidate
        variant = "business_ready" if args.ready_base_url else "block_media"
        return active_client, active_session, variant if candidate else "default"

    sources = {"Jable": Jable(proxy), "MissAV": MissAV(proxy)}
    if args.source != "both":
        sources = {args.source: sources[args.source]}
    samples = {}
    if args.samples_file:
        with open(args.samples_file) as stream:
            for line in stream:
                row = json.loads(line)
                if row.get("stage") == "samples" and row.get("source") in sources:
                    samples[row["source"]] = row["samples"]

    def validate(source, avid, url, result):
        def business(html):
            if isinstance(source, MissAV):
                return source._is_detail_page_html(html, avid)
            title = re.search(r"<title[^>]*>(.*?)</title>", html, re.I | re.S)
            if args.ready_base_url:
                parsed = source.parse_html(html)
                if not (
                    parsed
                    and parsed.avid.upper() == avid.upper()
                    and parsed.m3u8
                    and parsed.source_title
                    and source.get_cover_url(html)
                ):
                    return False
            return bool(
                source._is_detail_page_html(html)
                and title
                and re.search(
                    rf"(?<![a-z0-9]){re.escape(avid)}(?![a-z0-9])", title[1], re.I
                )
            )

        started = perf_counter()
        checked = PageFetchService.validate_result(url, result, business)
        return checked, round((perf_counter() - started) * 1000, 3)

    for name, source in sources.items():
        base = f"https://{source.domain}"
        if name not in samples:
            session.block_media = False
            listing_url = base + ("/latest-updates/" if name == "Jable" else "/")
            listing = client.fetch(listing_url, timeout_ms=60000)
            validator = (
                source._is_listing_page_html
                if isinstance(source, Jable)
                else lambda html: "missav" in html.lower()
            )
            checked = PageFetchService.validate_result(listing_url, listing, validator)
            if not checked.ok:
                emit(stage="discovery", source=name, window=args.window, valid=False)
                return 2
            if name == "Jable":
                found = [
                    p.strip("/").split("/")[-1].upper()
                    for p in detail_paths(checked.html, source.domain)
                ]
            else:
                found = [
                    avid for _, avid in detail_candidates(checked.html, source.domain)
                ]
            samples[name] = found[: args.count]
        chosen = samples[name]
        if len(chosen) < args.count or any(
            not re.fullmatch(r"[A-Za-z0-9-]+", a) for a in chosen
        ):
            parser.error("Insufficient or invalid AVID samples")
        emit(
            stage="samples",
            source=name,
            window=args.window,
            samples=chosen[: args.count],
        )
        records = []
        for index, avid in enumerate(chosen[: args.count], 1):
            path = (
                f"/videos/{avid.lower()}/" if name == "Jable" else f"/cn/{avid.lower()}"
            )
            url = base + path
            pair = {}
            for block_media in arm_order(index, args.window):
                active_client, active_session, variant = select_arm(block_media)
                page = active_client.fetch(url, timeout_ms=60000)
                checked, validation_ms = validate(source, avid, url, page)
                pair[block_media] = checked.ok
                row = dict(
                    stage="detail",
                    source=name,
                    sample=avid,
                    index=index,
                    window=args.window,
                    block_media=active_session.block_media,
                    candidate=block_media,
                    variant=variant,
                    valid=checked.ok,
                    failure=str(checked.failure or "none"),
                    provider_status=page.provider_status,
                    client_ms=page.elapsed_ms,
                    validation_ms=validation_ms,
                    timings=active_session.timings,
                )
                emit(**row)
                records.append(row)
                sleep(0.5)
            if pair.get(False) and not pair.get(True):
                emit(
                    stage="stop",
                    source=name,
                    window=args.window,
                    reason="candidate_validity_regression",
                )
                return 2
        for block_media in (False, True):
            emit(
                stage="summary",
                source=name,
                window=args.window,
                candidate=block_media,
                **summarize([r for r in records if r["candidate"] == block_media]),
            )
        for block_media in (False, True):
            active_client, active_session, variant = select_arm(block_media)
            avid = "NASSAV-NONEXISTENT-999999999"
            path = (
                f"/videos/{avid.lower()}/" if name == "Jable" else f"/cn/{avid.lower()}"
            )
            page = active_client.fetch(base + path, timeout_ms=60000)
            checked, validation_ms = validate(source, avid, base + path, page)
            emit(
                stage="negative",
                source=name,
                window=args.window,
                block_media=active_session.block_media,
                candidate=block_media,
                variant=variant,
                valid=checked.ok,
                failure=str(checked.failure or "none"),
                client_ms=page.elapsed_ms,
                validation_ms=validation_ms,
                timings=active_session.timings,
            )
            if checked.ok:
                emit(
                    stage="stop",
                    source=name,
                    window=args.window,
                    reason="negative_false_positive",
                )
                return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
