import time
from dataclasses import dataclass


@dataclass
class CookieRuntimeState:
    cookie: str
    updated_at: str | None
    expires_at: float


class SourceCookieRuntimeCache:
    """进程内 Cookie 运行时缓存。

    该对象只负责短期缓存，不是 Cookie 真值；真值始终在 `SourceCookie` 表。
    """

    def __init__(self, default_ttl_seconds: float = 30.0):
        self.default_ttl_seconds = default_ttl_seconds
        self._states: dict[str, CookieRuntimeState] = {}

    def get_state(self, source_name: str) -> CookieRuntimeState | None:
        return self._states.get(self._normalize(source_name))

    def set_state(
        self,
        source_name: str,
        cookie: str,
        *,
        updated_at: str | None = None,
        ttl_seconds: float | None = None,
    ) -> CookieRuntimeState:
        ttl = self.default_ttl_seconds if ttl_seconds is None else ttl_seconds
        state = CookieRuntimeState(
            cookie=cookie,
            updated_at=updated_at,
            expires_at=time.monotonic() + ttl,
        )
        self._states[self._normalize(source_name)] = state
        return state

    def invalidate(self, source_name: str) -> None:
        self._states.pop(self._normalize(source_name), None)

    def expire_now(self, source_name: str) -> None:
        state = self.get_state(source_name)
        if state is None:
            return
        state.expires_at = 0.0

    def clear(self) -> None:
        self._states.clear()

    @staticmethod
    def _normalize(source_name: str) -> str:
        return source_name.lower()


source_cookie_runtime_cache = SourceCookieRuntimeCache()
