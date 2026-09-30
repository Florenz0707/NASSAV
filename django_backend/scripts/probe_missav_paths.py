"""Read-only comparison of MissAV detail URL patterns in the API container.

Usage: python scripts/probe_missav_paths.py --count 20 --subtitle-count 8
       python scripts/probe_missav_paths.py --resource-targets --count 20
Prints sanitized JSONL; resource-targets only reads existing MissAV AVIDs.
"""

import argparse
import json
import os
from time import sleep

import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "django_project.settings")
django.setup()

from django.conf import settings  # noqa: E402
from nassav.models import AVResource  # noqa: E402
from nassav.page_fetching import (  # noqa: E402
    PageFetchService,
    create_page_fetch_service,
)
from nassav.source.MissAV import MissAV  # noqa: E402
from scripts.probe_p5_missav import detail_candidates  # noqa: E402


def emit(**fields):
    print(json.dumps(fields, ensure_ascii=False, sort_keys=True), flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--count", type=int, default=20)
    parser.add_argument("--offset", type=int, default=0)
    parser.add_argument("--subtitle-count", type=int, default=8)
    parser.add_argument("--root-count", type=int, default=0)
    parser.add_argument("--resource-targets", action="store_true")
    args = parser.parse_args()
    if not 1 <= args.count <= 100:
        parser.error("--count must be between 1 and 100")
    if args.offset < 0:
        parser.error("--offset must be non-negative")
    if args.resource_targets and args.offset:
        parser.error("--offset is only supported for homepage discovery")
    if not 0 <= args.subtitle_count <= args.count:
        parser.error("--subtitle-count must be between 0 and --count")
    if not 0 <= args.root_count <= args.count:
        parser.error("--root-count must be between 0 and --count")
    if not settings.BROWSER_FETCH_CONFIG.enabled:
        parser.error("BrowserFetch must be enabled")
    proxy = settings.PROXY_URL if settings.PROXY_ENABLED else None
    fetcher = create_page_fetch_service(settings.BROWSER_FETCH_CONFIG, proxy_url=proxy)
    browser = fetcher.browser
    if browser is None or getattr(browser, "provider", None) != "byparr":
        parser.error("The configured browser provider must be Byparr")
    source = MissAV(proxy, page_fetcher=fetcher)
    base = f"https://{source.domain}"
    home = base + "/"
    if args.resource_targets:
        avids = list(
            AVResource.objects.filter(source="MissAV")
            .order_by("-metadata_updated_at")
            .values_list("avid", flat=True)[: args.count]
        )
        candidates = [(None, avid) for avid in avids]
        emit(stage="discovery", source="resources", candidates=len(candidates))
    else:
        listing = PageFetchService.validate_result(
            home,
            browser.fetch(home, timeout_ms=fetcher.timeout_ms),
            lambda html: "missav" in html.lower(),
        )
        candidates = (
            detail_candidates(listing.html, source.domain) if listing.ok else []
        )
        emit(
            stage="discovery",
            source="homepage",
            valid=listing.ok,
            failure=str(listing.failure or "none"),
            candidates=len(candidates),
            byparr_ms=listing.elapsed_ms,
        )
        if not listing.ok or len(candidates) < args.offset + args.count:
            return 2
        candidates = candidates[args.offset : args.offset + args.count]

    for index, (path, avid) in enumerate(candidates[: args.count], start=1):
        slug = avid.lower()
        variants = [("plain_cn", f"/cn/{slug}")]
        variants.append(("discovered", path) if path else ("plain_en", f"/en/{slug}"))
        if index <= args.root_count:
            variants.append(("plain_root", f"/{slug}"))
        if index <= args.subtitle_count:
            variants += [
                ("subtitle_cn", f"/cn/{slug}-chinese-subtitle"),
                ("subtitle_root", f"/{slug}-chinese-subtitle"),
            ]
        if index % 2 == 0:
            variants.reverse()
        seen = set()
        for kind, candidate_path in variants:
            if candidate_path in seen:
                emit(
                    stage="detail", index=index, sample=avid, kind=kind, duplicate=True
                )
                continue
            seen.add(candidate_path)
            url = base + candidate_path
            result = PageFetchService.validate_result(
                url,
                browser.fetch(url, timeout_ms=fetcher.timeout_ms),
                lambda html: source._is_detail_page_html(html, avid),
            )
            emit(
                stage="detail",
                index=index,
                sample=avid,
                kind=kind,
                discovered_kind=path.split("/")[1] if path else None,
                valid=result.ok,
                failure=str(result.failure or "none"),
                target_status=result.target_status,
                byparr_ms=result.elapsed_ms,
            )
            sleep(0.25)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
