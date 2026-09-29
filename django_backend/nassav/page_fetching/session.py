"""Select a browser Cookie header applicable to one verified target page."""

from dataclasses import dataclass
from datetime import datetime, timezone
from urllib.parse import urlsplit

from .contracts import PageResult


@dataclass(frozen=True)
class BrowserSessionCandidate:
    cookie: str
    user_agent: str
    expires_at: datetime | None


def candidate_for_page(url: str, result: PageResult) -> BrowserSessionCandidate | None:
    """Keep all applicable cookies; reject duplicate names with ambiguous scope."""
    parsed = urlsplit(url)
    host = (parsed.hostname or "").lower()
    path = parsed.path or "/"
    if not host or not result.user_agent.strip():
        return None
    now = datetime.now(timezone.utc).timestamp()
    selected: dict[str, tuple[tuple[int, int], str, float | None]] = {}
    for item in result.cookies:
        name, value = item.get("name"), item.get("value")
        if (
            not isinstance(name, str)
            or not name
            or not isinstance(value, str)
            or not value
        ):
            continue
        if any(char in name + value for char in "\r\n;") or any(
            char.isspace() or char in "=," for char in name
        ):
            continue
        domain = str(item.get("domain") or host).lstrip(".").lower()
        host_only = item.get("hostOnly") is True
        if not domain or (
            host != domain
            if host_only
            else not (host == domain or host.endswith("." + domain))
        ):
            continue
        cookie_path = str(item.get("path") or "/")
        if not cookie_path.startswith("/") or not path.startswith(cookie_path):
            continue
        if (
            len(path) > len(cookie_path)
            and not cookie_path.endswith("/")
            and path[len(cookie_path)] != "/"
        ):
            continue
        expiry = item.get("expires")
        if (
            not isinstance(expiry, (int, float))
            or isinstance(expiry, bool)
            or expiry <= 0
        ):
            expiry = None
        elif expiry <= now:
            continue
        rank = (len(domain), len(cookie_path))
        previous = selected.get(name)
        if previous is not None and previous[0] == rank and previous[1] != value:
            return None
        if previous is None or rank > previous[0]:
            selected[name] = (rank, value, expiry)
    if not selected:
        return None
    expires = [entry[2] for entry in selected.values() if entry[2] is not None]
    return BrowserSessionCandidate(
        cookie="; ".join(f"{name}={selected[name][1]}" for name in sorted(selected)),
        user_agent=result.user_agent.strip(),
        expires_at=datetime.fromtimestamp(min(expires), timezone.utc)
        if expires
        else None,
    )
