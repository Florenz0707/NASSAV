"""Business-content predicate for the isolated wait experiment only."""

import re
from urllib.parse import urlsplit


def detail_identity(url: str) -> tuple[str, str] | None:
    parsed = urlsplit(url)
    if parsed.hostname == "jable.tv":
        match = re.fullmatch(r"/videos/([a-z0-9-]+)/?", parsed.path, re.I)
        return ("jable", match[1]) if match else None
    if parsed.hostname == "missav.ai":
        match = re.fullmatch(r"/(?:cn|en)/([a-z0-9-]+)/?", parsed.path, re.I)
        return ("missav", match[1].removesuffix("-chinese-subtitle")) if match else None
    return None


def has_business_content(html: str, url: str) -> bool:
    identity = detail_identity(url)
    if identity is None:
        return False
    site, avid = identity
    if site == "jable":
        title = re.search(r"<title[^>]*>(.*?)</title>", html, re.I | re.S)
        media = re.search(r"var hlsUrl = [\"']([^\"']+)[\"']", html)
        if not re.search(r'<meta property="og:image" content="[^"]+"', html):
            return False
    else:
        title = re.search(r'<meta property="og:title" content="(.*?)"', html)
        media = re.search(r"m3u8\|([a-f0-9|]+)\|com\|surrit\|https\|video", html)
    return bool(
        title
        and media
        and re.search(rf"(?<![a-z0-9]){re.escape(avid)}(?![a-z0-9])", title[1], re.I)
    )
