"""Compatibility API for older FlareSolverr callers.

New Source code uses ``nassav.page_fetching`` directly. This wrapper keeps the
old ``get``/``get_html``/``get_cookies_str`` methods on the shared GET adapter.
"""

import requests

from nassav.page_fetching.browser import FlareSolverrPageClient


class FlareSolverrClient:
    def __init__(
        self,
        base_url: str,
        timeout_ms: int = 60000,
        proxy: str | None = None,
    ):
        self.base_url = base_url.rstrip("/")
        self.timeout_ms = timeout_ms
        self.proxy = str(proxy or "").strip() or None
        self._client = FlareSolverrPageClient(self.base_url)

    def is_available(self) -> bool:
        try:
            response = requests.get(f"{self.base_url}/health", timeout=5)
            return response.status_code == 200
        except requests.RequestException:
            return False

    def get(self, url: str) -> dict | None:
        result = self._client.fetch(url, timeout_ms=self.timeout_ms)
        if not result.ok:
            return None
        return {
            "status": result.target_status,
            "url": result.final_url,
            "response": result.html,
            "cookies": list(result.cookies),
            "userAgent": result.user_agent,
        }

    def get_html(self, url: str) -> str | None:
        solution = self.get(url)
        return solution["response"] if solution else None

    def get_cookies_str(self, url: str) -> str | None:
        solution = self.get(url)
        if not solution:
            return None
        cookies = solution["cookies"]
        values = [
            f"{c['name']}={c['value']}"
            for c in cookies
            if c.get("name") and c.get("value")
        ]
        return "; ".join(values) or None
