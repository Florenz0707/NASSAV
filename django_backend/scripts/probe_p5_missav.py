"""Read-only MissAV P5 comparison in the configured API container.

Usage: python scripts/probe_p5_missav.py --window W1 --allow-session-replay
Emits sanitized JSONL. It never reads or writes SourceCookie, Redis, or tasks.
"""

import argparse
import json
import os
import re
from statistics import median
from time import sleep
from urllib.parse import urlsplit

import django
from bs4 import BeautifulSoup

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "django_project.settings")
django.setup()

from django.conf import settings  # noqa: E402
from nassav.page_fetching import (  # noqa: E402
    PageFetchService,
    create_page_fetch_service,
)
from nassav.page_fetching.session import candidate_for_page  # noqa: E402
from nassav.source.CookieRepository import (  # noqa: E402
    SourceCookieRecord,
    proxy_route_profile,
)
from nassav.source.MissAV import MissAV  # noqa: E402

AVID_PREFIX = re.compile(r"(?P<avid>[a-z][a-z0-9]*(?:-[a-z]+)*-\d+)(?:-|$)")


def detail_candidates(html: str, host: str) -> list[tuple[str, str]]:
    """Extract only same-host, query-free detail links with a recognizable AVID."""
    found = {}
    for link in BeautifulSoup(html, "html.parser").select("a[href]"):
        parsed = urlsplit(str(link.get("href") or ""))
        if parsed.scheme and parsed.scheme != "https":
            continue
        if parsed.hostname and parsed.hostname != host:
            continue
        if parsed.query or parsed.fragment:
            continue
        parts = parsed.path.strip("/").split("/")
        if len(parts) == 3 and re.fullmatch(r"dm[0-9]+", parts[0]):
            parts = parts[1:]
        if len(parts) == 2 and parts[0] in {"cn", "en"}:
            slug = parts[1]
        elif len(parts) == 1:
            slug = parts[0]
        else:
            continue
        if not re.fullmatch(r"[a-z0-9-]+", slug):
            continue
        match = AVID_PREFIX.match(slug)
        if match:
            avid = match.group("avid").upper()
            found.setdefault(avid, parsed.path)
    return [(path, avid) for avid, path in found.items()]


def checked(url, result, validator):
    return PageFetchService.validate_result(url, result, validator)


def emit(**fields):
    print(json.dumps(fields, ensure_ascii=False, sort_keys=True), flush=True)


def valid_detail(source, url, avid, result):
    return checked(url, result, lambda html: source._is_detail_page_html(html, avid))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--window", required=True, choices=("W1", "W2"))
    parser.add_argument("--count", type=int, default=20)
    parser.add_argument("--allow-session-replay", action="store_true")
    args = parser.parse_args()
    if not args.allow_session_replay:
        parser.error("Explicit --allow-session-replay is required")
    if args.count < 20 or args.count > 100:
        parser.error("--count must be between 20 and 100")
    if not settings.BROWSER_FETCH_CONFIG.enabled:
        parser.error("BrowserFetch must be enabled")
    proxy = settings.PROXY_URL if settings.PROXY_ENABLED else None
    if not proxy or proxy_route_profile(proxy) is None:
        parser.error("A configured proxy route is required")
    fetcher = create_page_fetch_service(settings.BROWSER_FETCH_CONFIG, proxy_url=proxy)
    browser = fetcher.browser
    if browser is None or getattr(browser, "provider", None) != "byparr":
        parser.error("The configured browser provider must be Byparr")
    fetcher.session_reuse_enabled = True  # Process-local only.
    source = MissAV(proxy, page_fetcher=fetcher)
    base = f"https://{source.domain}"
    home = base + "/"
    listing = checked(
        home,
        browser.fetch(home, timeout_ms=fetcher.timeout_ms),
        lambda html: "missav" in html.lower(),
    )
    candidates = detail_candidates(listing.html, source.domain) if listing.ok else []
    emit(
        stage="discovery",
        window=args.window,
        valid=listing.ok,
        failure=str(listing.failure or "none"),
        candidates=len(candidates),
        byparr_ms=listing.elapsed_ms,
        provider_status=listing.provider_status,
    )
    if not listing.ok or len(candidates) < args.count + 5:
        return 2

    controls = {}
    control_calls = 0
    session = None
    for path, avid in candidates[:12]:
        if len(controls) >= 5:
            break
        url = base + path
        control_calls += 1
        sleep(1)
        page = valid_detail(
            source, url, avid, browser.fetch(url, timeout_ms=fetcher.timeout_ms)
        )
        emit(
            stage="control",
            window=args.window,
            sample=avid,
            valid=page.ok,
            failure=str(page.failure or "none"),
            byparr_ms=page.elapsed_ms,
            provider_status=page.provider_status,
        )
        if not page.ok:
            continue
        controls[path] = page
        if session is not None:
            continue
        candidate = candidate_for_page(url, page)
        if candidate is None:
            emit(
                stage="seed",
                window=args.window,
                sample=avid,
                candidate_complete=False,
                valid=False,
            )
            continue
        proposed = SourceCookieRecord(
            "missav",
            candidate.cookie,
            user_agent=candidate.user_agent,
            expires_at=candidate.expires_at,
            egress_profile=proxy_route_profile(proxy),
        )
        probe = valid_detail(
            source,
            url,
            avid,
            source.fetch_page(url, session_override=proposed, timeout_seconds=3),
        )
        verified = probe.ok and probe.target_status == 200 and probe.elapsed_ms <= 3000
        emit(
            stage="seed",
            window=args.window,
            sample=avid,
            candidate_complete=True,
            valid=verified,
            status=probe.target_status,
            failure=str(probe.failure or "none"),
            direct_ms=probe.elapsed_ms,
        )
        if verified:
            session = proposed
    if len(controls) < 5:
        return 2

    records = []
    for path, avid in (item for item in candidates if item[0] not in controls):
        if len(records) >= args.count:
            break
        url = base + path

        def validator(html):
            return source._is_detail_page_html(html, avid)

        if len(records) % 2:
            warm = (
                checked(
                    url, source.fetch_page(url, session_override=session), validator
                )
                if session
                else None
            )
            plain = checked(url, source.fetch_page(url), validator)
        else:
            plain = checked(url, source.fetch_page(url), validator)
            warm = (
                checked(
                    url, source.fetch_page(url, session_override=session), validator
                )
                if session
                else None
            )
        browser_page = None
        if (warm is not None and not warm.ok) or (warm is None and not plain.ok):
            browser_page = valid_detail(
                source, url, avid, browser.fetch(url, timeout_ms=fetcher.timeout_ms)
            )
        if not (plain.ok or (warm and warm.ok) or (browser_page and browser_page.ok)):
            emit(
                stage="rejected",
                window=args.window,
                sample=avid,
                plain_status=plain.target_status,
                warm_status=warm.target_status if warm else None,
                browser_valid=browser_page.ok if browser_page else None,
            )
            continue
        record = {
            "stage": "detail",
            "window": args.window,
            "index": len(records) + 1,
            "sample": avid,
            "cache_hit": False,
            "plain_valid": plain.ok and plain.target_status == 200,
            "plain_status": plain.target_status,
            "plain_failure": str(plain.failure or "none"),
            "plain_ms": plain.elapsed_ms,
            "warm_valid": warm.ok and warm.target_status == 200 if warm else None,
            "warm_request_valid": (warm.ok or bool(browser_page and browser_page.ok))
            if warm
            else None,
            "warm_status": warm.target_status if warm else None,
            "warm_failure": str(warm.failure or "none") if warm else None,
            "warm_ms": warm.elapsed_ms if warm else None,
            "warm_total_ms": warm.elapsed_ms
            + (browser_page.elapsed_ms if not warm.ok and browser_page else 0)
            if warm
            else None,
            "browser_valid": browser_page.ok if browser_page else None,
            "browser_ms": browser_page.elapsed_ms if browser_page else None,
            "browser_call": int(browser_page is not None),
        }
        emit(**record)
        records.append(record)
        sleep(0.25)

    browser_times = [page.elapsed_ms for page in controls.values()]

    def p95(name):
        if len(records) != args.count:
            return None
        values = sorted(row[name] for row in records if row[name] is not None)
        return values[max(0, int(len(values) * 0.95 + 0.999) - 1)]

    emit(
        stage="summary",
        window=args.window,
        valid_pages=len(records),
        candidate_count=len(candidates),
        session_verified=session is not None,
        plain_valid=sum(row["plain_valid"] for row in records),
        warm_valid=sum(bool(row["warm_valid"]) for row in records),
        plain_direct_p95_ms=p95("plain_ms"),
        warm_p95_ms=p95("warm_total_ms") if session else None,
        warm_request_valid=sum(bool(row["warm_request_valid"]) for row in records)
        if session
        else None,
        byparr_median_ms=round(median(browser_times)),
        browser_calls=1 + control_calls + sum(row["browser_call"] for row in records),
    )
    return 0 if len(records) == args.count else 2


if __name__ == "__main__":
    raise SystemExit(main())
