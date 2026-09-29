"""Short-lived process cache for complete, immutable session snapshots."""

import time
from dataclasses import dataclass, replace

from nassav.source.CookieRepository import SourceCookieRecord


@dataclass(frozen=True)
class CookieRuntimeState:
    session: SourceCookieRecord | None
    expires_at: float

    @property
    def cookie(self) -> str:
        return self.session.cookie if self.session else ""

    @property
    def updated_at(self) -> str | None:
        return self.session.updated_at if self.session else None

    @property
    def user_agent(self) -> str | None:
        return self.session.user_agent if self.session else None

    @property
    def session_expires_at(self):
        return self.session.expires_at if self.session else None

    @property
    def egress_profile(self) -> str | None:
        return self.session.egress_profile if self.session else None


class SourceCookieRuntimeCache:
    """Local cache only; the SourceCookie row remains authoritative."""

    def __init__(self, default_ttl_seconds: float = 30.0):
        self.default_ttl_seconds = default_ttl_seconds
        self._states: dict[str, CookieRuntimeState] = {}

    def get_state(self, source_name: str) -> CookieRuntimeState | None:
        return self._states.get(self._normalize(source_name))

    def set_state(
        self,
        source_name: str,
        session: SourceCookieRecord | None,
        *,
        ttl_seconds: float | None = None,
    ) -> CookieRuntimeState:
        ttl = self.default_ttl_seconds if ttl_seconds is None else ttl_seconds
        state = CookieRuntimeState(
            session=session,
            expires_at=time.monotonic() + ttl,
        )
        self._states[self._normalize(source_name)] = state
        return state

    def invalidate(self, source_name: str) -> None:
        self._states.pop(self._normalize(source_name), None)

    def expire_now(self, source_name: str) -> None:
        state = self.get_state(source_name)
        if state is not None:
            self._states[self._normalize(source_name)] = replace(state, expires_at=0.0)

    def clear(self) -> None:
        self._states.clear()

    @staticmethod
    def _normalize(source_name: str) -> str:
        return source_name.lower()


source_cookie_runtime_cache = SourceCookieRuntimeCache()
