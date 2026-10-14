"""Credential validation and immutable references, independent of persistence."""

import re
from dataclasses import dataclass
from urllib.parse import urlsplit
from uuid import UUID


class CredentialConflict(RuntimeError):
    pass


CHALLENGE_COOKIE_NAMES = frozenset({"cf_clearance", "__cf_bm", "__cflb"})


def cookie_values(value):
    if not isinstance(value, str) or not 1 <= len(value) <= 32768:
        raise ValueError("Invalid Cookie header")
    result = {}
    for part in value.split(";"):
        name, separator, content = part.strip().partition("=")
        if (
            not separator
            or not re.fullmatch(r"[!#$%&'*+.^_`|~0-9a-zA-Z-]+", name)
            or name in result
            or not content
            or any(
                ord(char) < 33 or ord(char) > 126 or char in ',;"\\' for char in content
            )
        ):
            raise ValueError("Invalid Cookie header")
        result[name] = content
    return result


def validate_secret(payload, *, kind):
    if not isinstance(payload, dict) or set(payload) != {"cookie", "user_agent"}:
        raise ValueError("Cookie and user_agent are required")
    values = cookie_values(payload["cookie"])
    agent = payload["user_agent"]
    if (
        not isinstance(agent, str)
        or not 1 <= len(agent) <= 2048
        or any(ord(char) < 32 or ord(char) > 126 for char in agent)
    ):
        raise ValueError("Invalid User-Agent")
    if not isinstance(kind, str) or kind not in {"clearance", "account"}:
        raise ValueError("Invalid credential kind")
    if kind == "clearance" and set(values) - CHALLENGE_COOKIE_NAMES:
        raise ValueError("System clearance contains unclassified cookies")
    return {
        "cookie": "; ".join(f"{key}={value}" for key, value in values.items()),
        "user_agent": agent,
    }


def origin_host(value):
    if not isinstance(value, str):
        raise ValueError("Invalid source origin")
    parsed = urlsplit("https://" + value)
    host = parsed.hostname
    if (
        not host
        or len(host) > 253
        or parsed.netloc != host
        or parsed.path
        or parsed.query
        or parsed.fragment
        or not re.fullmatch(r"[a-z0-9](?:[a-z0-9.-]*[a-z0-9])?", host)
        or ".." in host
    ):
        raise ValueError("Invalid source origin")
    return host


def reference_id(value):
    try:
        return UUID(str(value))
    except (ValueError, TypeError):
        raise ValueError("Invalid credential ID") from None


@dataclass(frozen=True)
class CredentialReference:
    id: UUID
    source_name: str
    scope: str
    owner_id: int | None
    origin_host: str
    version: int
    kind: str

    @property
    def cache_scope(self):
        return f"credential:{self.id}:{self.version}:{self.origin_host}"


@dataclass(frozen=True)
class RefreshClaim:
    snapshot_id: UUID
    credential: CredentialReference
    generation: int
    owner: UUID
    context: str


def credential_context(ref):
    return f"source-credential:{ref.id}:{ref.source_name}:{ref.scope}:{ref.owner_id}:{ref.origin_host}:{ref.version}:{ref.kind}"


def snapshot_context(row):
    return f"source-session:{row.pk}:{row.credential_id}:{row.credential_version}:{row.origin_host}:{row.egress_profile}:{row.browser_context}:{row.version}"
