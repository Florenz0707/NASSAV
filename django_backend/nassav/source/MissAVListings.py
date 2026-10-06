"""MissAV listing URLs and business validation, without network or persistence."""

import re
from urllib.parse import quote, unquote, urlencode, urljoin, urlsplit

from bs4 import BeautifulSoup

from nassav.source.search_contracts import SourceSearchError

SORTS = {"-views": "views", "-likes": "saved", "-latest": "released_at"}


def listing_url(domain: str, kind: str, term: str, page: int, ordering: str) -> str:
    if kind not in {"search", "actresses", "genres"} or not term.strip():
        raise ValueError("Invalid MissAV listing target")
    if ordering not in SORTS:
        raise ValueError("MissAV supports -views, -likes and -latest ordering")
    query = urlencode({"page": max(1, page), "sort": SORTS[ordering]})
    return f"https://{domain}/cn/{kind}/{quote(unquote(term.strip()), safe='')}?{query}"


def normalized_path(url: str) -> str:
    return unquote(re.sub(r"^/dm\d+(?=/)", "", urlsplit(url).path)).rstrip("/")


def parse_listing(html: str, domain: str) -> list[dict]:
    soup = BeautifulSoup(html, "html.parser")
    items = []
    seen = set()
    for card in soup.select(".thumbnail"):
        title_link = card.select_one("div.my-2 a[href]")
        if title_link is None:
            continue
        detail_url = urljoin(f"https://{domain}/", str(title_link.get("href", "")))
        if urlsplit(detail_url).hostname != domain:
            continue
        slug = normalized_path(detail_url).rsplit("/", 1)[-1]
        # Only a video identifier, never a navigation/taxonomy link.
        match = re.fullmatch(
            r"([a-z0-9]+(?:-[a-z0-9]+)*-\d+)"
            r"(?:-(?:chinese-subtitle|english-subtitle|uncensored-leak|4k))*",
            slug,
            re.IGNORECASE,
        )
        if match is None:
            continue
        avid = match.group(1).upper()
        if avid in seen:
            continue
        seen.add(avid)
        image = card.select_one("img")
        cover = str(image.get("data-src") or image.get("src") or "") if image else ""
        items.append(
            {
                "avid": avid,
                "title": title_link.get_text(" ", strip=True),
                "detail_url": detail_url,
                "cover_url": urljoin(detail_url, cover) if cover else "",
                "source": "MissAV",
                "metrics": {},
            }
        )
    return items


def valid_listing(html: str, domain: str) -> bool:
    soup = BeautifulSoup(html, "html.parser")
    if not soup.select_one("h1") or "missav" not in html.lower():
        return False
    return bool(parse_listing(html, domain)) or any(
        marker in soup.get_text(" ", strip=True).lower()
        for marker in (
            "no results found",
            "no videos found",
            "no results",
            "no videos",
            "没有找到",
            "未找到",
            "暂无视频",
            "沒有找到",
            "未找到影片",
        )
    )


def verify_listing_url(requested: str, final: str) -> None:
    if urlsplit(requested).hostname != urlsplit(final).hostname or normalized_path(
        requested
    ) != normalized_path(final):
        raise SourceSearchError("missav_listing_path_mismatch")
