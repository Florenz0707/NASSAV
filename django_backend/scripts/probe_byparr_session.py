"""Read-only P0 browser-session comparison; see scripts/README.md for arguments."""

import argparse
import json
import os
from datetime import datetime, timezone
from time import monotonic
from urllib.parse import urlsplit

import django
from curl_cffi import requests

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "django_project.settings")
django.setup()

from django.conf import settings  # noqa: E402
from nassav.constants import HEADERS, IMPERSONATE  # noqa: E402
from nassav.page_fetching import PageFetchService, create_page_fetch_service  # noqa: E402
from nassav.source.Jable import Jable  # noqa: E402
from nassav.source.MissAV import MissAV  # noqa: E402
from nassav.models import SourceCookie  # noqa: E402


def valid_page(source, kind, avid, requested, final, html):
    if not PageFetchService.same_site(requested, final):
        return "wrong_site"
    if PageFetchService.is_challenge(html):
        return "challenge"
    if kind == "detail":
        valid = (
            source._is_detail_page_html(html, avid)
            if isinstance(source, MissAV)
            else source._is_detail_page_html(html)
        )
    elif kind == "listing" and isinstance(source, Jable):
        valid = source._is_listing_page_html(html)
    else:
        valid = False
    return "valid" if valid else "invalid_structure"


def cookie_header(items, host, path):
    selected = {}
    now = datetime.now(timezone.utc).timestamp()
    for item in items:
        name, value = item.get("name"), item.get("value")
        domain = str(item.get("domain") or host).lstrip(".").lower()
        cookie_path = str(item.get("path") or "/")
        expiry = item.get("expires")
        if (
            not name
            or not value
            or not (host == domain or host.endswith("." + domain))
            or not path.startswith(cookie_path)
            or (isinstance(expiry, (int, float)) and expiry > 0 and expiry <= now)
        ):
            continue
        # Prefer the most specific domain and path for duplicate names.
        rank = (len(domain), len(cookie_path))
        if name not in selected or rank > selected[name][0]:
            selected[name] = (rank, value)
    return "; ".join(f"{name}={selected[name][1]}" for name in sorted(selected))


def direct_probe(source, kind, avid, url, label, cookie, user_agent):
    headers = HEADERS.copy()
    if cookie:
        headers["Cookie"] = cookie
    if user_agent:
        headers["User-Agent"] = user_agent
    started = monotonic()
    try:
        response = requests.get(
            url,
            headers=headers,
            proxies=source.proxies,
            timeout=source.timeout,
            impersonate=IMPERSONATE,
        )
        return {
            "arm": label,
            "status": response.status_code,
            "validation": valid_page(
                source, kind, avid, url, str(response.url), response.text
            ),
            "elapsed_ms": round((monotonic() - started) * 1000),
        }
    except Exception as error:
        return {
            "arm": label,
            "status": None,
            "validation": type(error).__name__,
            "elapsed_ms": round((monotonic() - started) * 1000),
        }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", choices=("jable", "missav"))
    parser.add_argument("kind", choices=("detail", "listing"))
    parser.add_argument("url")
    parser.add_argument("--avid", default="", help="Required for detail validation")
    parser.add_argument(
        "--allow-session-replay",
        action="store_true",
        help="Explicitly allow sending stored and browser session cookies to the target",
    )
    args = parser.parse_args()
    host = urlsplit(args.url).hostname or ""
    expected_host = settings.SOURCE_CONFIG[args.source]["domain"]
    parsed = urlsplit(args.url)
    if (
        parsed.scheme != "https"
        or host != expected_host
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
    ):
        parser.error("URL must use HTTPS and the configured source host")
    if args.source == "missav" and (args.kind != "detail" or not args.avid):
        parser.error("MissAV requires a detail URL and --avid")
    if args.source == "jable" and args.kind == "detail" and not args.avid:
        parser.error("Detail probes require --avid")

    proxy = settings.PROXY_URL if settings.PROXY_ENABLED else None
    source = Jable(proxy) if args.source == "jable" else MissAV(proxy)
    browser = create_page_fetch_service(
        settings.BROWSER_FETCH_CONFIG, proxy_url=proxy
    ).browser
    if browser is None:
        parser.error("BrowserFetch must be enabled")
    old_cookie = ""
    if args.allow_session_replay:
        old = SourceCookie.objects.filter(source_name__iexact=args.source).first()
        old_cookie = old.cookie if old else ""
    browser_result = browser.fetch(
        args.url, timeout_ms=settings.BROWSER_FETCH_CONFIG.timeout_ms
    )
    browser_validation = (
        valid_page(
            source,
            args.kind,
            args.avid,
            args.url,
            browser_result.final_url,
            browser_result.html,
        )
        if browser_result.ok
        else str(browser_result.failure)
    )
    browser_cookie = cookie_header(browser_result.cookies, host, parsed.path or "/")
    browser_ua = browser_result.user_agent
    output = {
        "time_utc": datetime.now(timezone.utc).isoformat(),
        "source": args.source,
        "kind": args.kind,
        "url": args.url,
        "avid": args.avid,
        "browser": {
            "provider_status": browser_result.provider_status,
            "target_status": browser_result.target_status,
            "validation": browser_validation,
            "elapsed_ms": browser_result.elapsed_ms,
            "cookie_present": bool(browser_cookie),
            "ua_present": bool(browser_ua),
            "cookie_count": browser_cookie.count("; ") + 1 if browser_cookie else 0,
        },
        "browser_calls": 1,
        "direct": [],
    }
    arms = [
        ("no_cookie_default_ua", "", ""),
        ("old_cookie_default_ua", old_cookie, ""),
        ("browser_cookie_default_ua", browser_cookie, ""),
        ("browser_ua_no_cookie", "", browser_ua),
        ("browser_cookie_and_ua", browser_cookie, browser_ua),
    ]
    # An invalid browser page cannot certify its returned cookie or UA.
    for label, cookie, ua in arms:
        if cookie and not args.allow_session_replay:
            output["direct"].append(
                {"arm": label, "validation": "not_run_session_replay_disabled"}
            )
        elif label.startswith("browser_") and browser_validation != "valid":
            output["direct"].append(
                {"arm": label, "validation": "not_run_invalid_browser"}
            )
        elif label == "browser_cookie_default_ua" and not browser_cookie:
            output["direct"].append(
                {"arm": label, "validation": "not_run_no_browser_cookie"}
            )
        elif label == "browser_ua_no_cookie" and not browser_ua:
            output["direct"].append(
                {"arm": label, "validation": "not_run_no_browser_ua"}
            )
        elif label == "old_cookie_default_ua" and not old_cookie:
            output["direct"].append(
                {"arm": label, "validation": "not_run_no_old_cookie"}
            )
        elif label == "browser_cookie_and_ua" and (not cookie or not ua):
            output["direct"].append(
                {"arm": label, "validation": "not_run_incomplete_session"}
            )
        else:
            output["direct"].append(
                direct_probe(source, args.kind, args.avid, args.url, label, cookie, ua)
            )
    print(json.dumps(output, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
