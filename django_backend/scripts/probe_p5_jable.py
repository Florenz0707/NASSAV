"""Read-only Jable P5 warm-session prescreen; run inside the configured API container.

Usage: python scripts/probe_p5_jable.py --window W1 --allow-session-replay
The script prints sanitized JSONL and never reads or writes SourceCookie. It does
not exercise shared Redis coordination, API tasks, or the 24-hour gray rollout.
"""

import argparse
import json
import os
import re
from datetime import datetime, timezone
from statistics import median
from time import monotonic, sleep
from urllib.parse import urlsplit

import django
from bs4 import BeautifulSoup

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "django_project.settings")
django.setup()

from django.conf import settings
from nassav.page_fetching import (
    PageFetchService,
    create_page_fetch_service,
)
from nassav.page_fetching.session import candidate_for_page
from nassav.source.CookieRepository import (
    SourceCookieRecord,
    proxy_route_profile,
)
from nassav.source.Jable import Jable


def detail_paths(html: str, host: str) -> list[str]:
    """Select only simple detail paths on the configured Jable host."""
    paths = set()
    for link in BeautifulSoup(html, "html.parser").select("a[href]"):
        parsed = urlsplit(str(link.get("href") or ""))
        if parsed.hostname and parsed.hostname != host:
            continue
        if parsed.query or parsed.fragment:
            continue
        if re.fullmatch(r"/videos/[a-z0-9-]+/", parsed.path):
            paths.add(parsed.path)
    return sorted(paths)


def checked(url, result, validator):
    return PageFetchService.validate_result(url, result, validator)


def emit(**fields):
    fields["recorded_at"] = datetime.now(timezone.utc).isoformat()
    print(json.dumps(fields, ensure_ascii=False, sort_keys=True), flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--window", required=True, choices=("W1", "W2"))
    parser.add_argument("--count", type=int, default=20)
    parser.add_argument("--allow-session-replay", action="store_true")
    parser.add_argument("--browser-base-url", help="Optional isolated v3.0.4 instance")
    args = parser.parse_args()
    if not args.allow_session_replay:
        parser.error("Explicit --allow-session-replay is required")
    if args.count < 20 or args.count > 100:
        parser.error("--count must be between 20 and 100")
    if not settings.BROWSER_FETCH_CONFIG.enabled:
        parser.error("BrowserFetch must be enabled")
    proxy = settings.PROXY_URL if settings.PROXY_ENABLED else None
    if not proxy:
        parser.error("A configured proxy route is required for this prescreen")
    fetcher = create_page_fetch_service(settings.BROWSER_FETCH_CONFIG, proxy_url=proxy)
    if args.browser_base_url:
        from nassav.page_fetching.browser import ByparrPageClient

        isolated = ByparrPageClient(args.browser_base_url, proxy_url=proxy)
        ready = isolated._session.get(
            args.browser_base_url.rstrip("/") + "/ready", timeout=5
        )
        if ready.status_code != 200 or ready.json().get("version") != "3.0.4":
            parser.error("Use an isolated v3.0.4 instance")
        fetcher.browser = isolated
    browser = fetcher.browser
    if browser is None or getattr(browser, "provider", None) != "byparr":
        parser.error("The configured browser provider must be Byparr")
    # Enable reuse only on this process-local Source; the running config and DB stay intact.
    fetcher.session_reuse_enabled = True
    source = Jable(proxy, page_fetcher=fetcher)
    base = f"https://{source.domain}"
    listing_url = base + "/latest-updates/"
    listing = checked(
        listing_url,
        browser.fetch(listing_url, timeout_ms=fetcher.timeout_ms),
        source._is_listing_page_html,
    )
    paths = detail_paths(listing.html, source.domain) if listing.ok else []
    emit(
        stage="discovery",
        window=args.window,
        valid=listing.ok,
        failure=str(listing.failure or "none"),
        detail_paths=len(paths),
        browser_ms=listing.elapsed_ms,
    )
    if not listing.ok or len(paths) < args.count + 1:
        return 2

    seed_path = None
    session = None
    seed_browser_ms = []
    for path in paths[:5]:
        seed_url = base + path
        seed = checked(
            seed_url,
            browser.fetch(seed_url, timeout_ms=fetcher.timeout_ms),
            source._is_detail_page_html,
        )
        seed_browser_ms.append(seed.elapsed_ms)
        candidate = candidate_for_page(seed_url, seed) if seed.ok else None
        emit(
            stage="seed",
            window=args.window,
            sample=path.removeprefix("/videos/").strip("/"),
            valid=seed.ok,
            candidate_complete=bool(candidate),
            failure=str(seed.failure or "none"),
            browser_ms=seed.elapsed_ms,
        )
        if candidate is None:
            continue
        profile = proxy_route_profile(proxy)
        if profile is None:
            return 2
        proposed = SourceCookieRecord(
            "jable",
            candidate.cookie,
            user_agent=candidate.user_agent,
            expires_at=candidate.expires_at,
            egress_profile=profile,
        )
        probe = checked(
            seed_url,
            source.fetch_page(seed_url, session_override=proposed, timeout_seconds=3),
            source._is_detail_page_html,
        )
        verified = probe.ok and probe.target_status == 200 and probe.elapsed_ms <= 3000
        emit(
            stage="seed_probe",
            window=args.window,
            sample=path.removeprefix("/videos/").strip("/"),
            valid=verified,
            status=probe.target_status,
            failure=str(probe.failure or "none"),
            direct_ms=probe.elapsed_ms,
        )
        if verified:
            seed_path = path
            session = proposed
            break
    if session is None or seed_path is None:
        return 2
    source.set_session(session)

    def valid_detail(html, avid):
        parsed = source.parse_html(html)
        return bool(
            parsed
            and parsed.avid.upper() == avid.upper()
            and parsed.m3u8
            and parsed.source_title
            and source.get_cover_url(html)
        )

    records = []
    for index, path in enumerate(
        [path for path in paths if path != seed_path][: args.count], 1
    ):
        url = base + path
        started = monotonic()
        avid = path.removeprefix("/videos/").strip("/")

        def validator(html):
            return valid_detail(html, avid)

        direct = checked(url, source.fetch_page(url), validator)
        browser_result = None
        if not direct.ok:
            browser_result = checked(
                url,
                browser.fetch(url, timeout_ms=fetcher.timeout_ms),
                validator,
            )
        record = {
            "stage": "warm",
            "window": args.window,
            "sample": path.removeprefix("/videos/").strip("/"),
            "index": index,
            "cache_hit": False,
            "direct_valid": direct.ok and direct.target_status == 200,
            "direct_status": direct.target_status,
            "direct_failure": str(direct.failure or "none"),
            "direct_ms": direct.elapsed_ms,
            "browser_calls": int(browser_result is not None),
            "browser_valid": browser_result.ok if browser_result else None,
            "browser_failure": str(browser_result.failure or "none")
            if browser_result
            else None,
            "byparr_ms": browser_result.elapsed_ms if browser_result else 0,
            "valid_page": direct.ok or bool(browser_result and browser_result.ok),
            "total_ms": round((monotonic() - started) * 1000),
        }
        emit(**record)
        records.append(record)
        sleep(0.25)

    valid = [item for item in records if item["valid_page"]]
    direct_valid = [item for item in valid if item["direct_valid"]]
    browser_times = [item["byparr_ms"] for item in records if item["browser_valid"]]
    emit(
        stage="summary",
        window=args.window,
        requested=len(records),
        valid_pages=len(valid),
        direct_valid=len(direct_valid),
        browser_calls=sum(item["browser_calls"] for item in records),
        first_ten_browser_calls=sum(item["browser_calls"] for item in records[:10]),
        direct_valid_rate=round(len(direct_valid) / len(records), 4)
        if records
        else None,
        warm_p95_ms=sorted(item["total_ms"] for item in records)[
            max(0, int(len(records) * 0.95 + 0.999) - 1)
        ]
        if records
        else None,
        byparr_median_ms=round(median(browser_times))
        if browser_times
        else round(median([listing.elapsed_ms, *seed_browser_ms])),
    )
    # Invalid target pages cannot count toward the plan's 20 valid requests.
    return 0 if len(valid) >= 20 else 2


if __name__ == "__main__":
    raise SystemExit(main())
