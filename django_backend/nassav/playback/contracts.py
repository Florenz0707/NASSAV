"""Playback data and consumer contracts without Django/Celery dependencies."""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from urllib.parse import urlsplit
from uuid import UUID


class PlaybackStopped(RuntimeError):
    pass


@dataclass(frozen=True)
class PreparationToken:
    session_id: UUID
    execution_id: UUID
    generation: int


@dataclass(frozen=True)
class PlaybackDescriptor:
    manifest_url: str
    referer: str
    user_agent: str
    source: str
    route_profile: str | None
    source_session_version: str | None
    schema: str = "online-playback-v2"
    cookie_policy: str = "omit"

    def validate(self):
        for url in (self.manifest_url, self.referer):
            p = urlsplit(url)
            if (
                p.scheme != "https"
                or not p.hostname
                or p.username
                or p.password
                or p.fragment
                or p.port not in (None, 443)
                or len(url) > 8192
                or any(ord(c) < 32 or ord(c) == 127 for c in url)
            ):
                raise ValueError("Invalid playback URL")
        if (
            self.schema != "online-playback-v2"
            or self.cookie_policy != "omit"
            or not self.source
            or not self.user_agent
            or any(c in self.user_agent for c in "\r\n")
        ):
            raise ValueError("Invalid playback context")
        return self


class PlaybackResolver(ABC):
    @abstractmethod
    def resolve(
        self, avid: str, source: str, control, *, force=False
    ) -> PlaybackDescriptor: ...
