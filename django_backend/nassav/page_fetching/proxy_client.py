"""Capacity decoration independent of the browser provider protocol."""

from .contracts import BrowserPageClient, PageResult
from .proxy_server import ProxyServer


class ProxyPageClient(BrowserPageClient):
    def __init__(self, client: BrowserPageClient, server: ProxyServer):
        self.client, self.server = client, server
        self.provider = getattr(client, "provider", "")
        self.control = None

    def set_task_control(self, control) -> None:
        self.control = control

    def set_task_transport(self, session) -> None:
        self.client.set_task_transport(session)

    def close(self) -> None:
        self.client.close()

    def fetch(self, url: str, *, timeout_ms: int) -> PageResult:
        check = self.control.check if self.control is not None else (lambda: None)
        with self.server.slot(timeout_ms, check=check):
            if self.control is not None:
                timeout_ms = max(
                    100, int(self.control.timeout(timeout_ms / 1000) * 1000)
                )
            return self.client.fetch(url, timeout_ms=timeout_ms)
