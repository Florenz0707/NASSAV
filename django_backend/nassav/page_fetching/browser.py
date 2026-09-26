"""Adapters for the GET subset shared by Byparr and FlareSolverr."""

from time import monotonic

import requests

from .contracts import BrowserPageClient, FetchFailure, PageResult


class _V1BrowserClient(BrowserPageClient):
    provider = ""

    def __init__(self, base_url: str):
        self.base_url = base_url.rstrip("/")
        self._session = requests.Session()
        # The control request must not inherit the target-site proxy from the host.
        self._session.trust_env = False

    def fetch(self, url: str, *, timeout_ms: int) -> PageResult:
        started = monotonic()

        def failed(reason: FetchFailure, status: int | None = None) -> PageResult:
            return PageResult(
                final_url=url,
                provider=self.provider,
                elapsed_ms=round((monotonic() - started) * 1000),
                provider_status=status,
                failure=reason,
            )

        try:
            response = self._session.post(
                f"{self.base_url}/v1",
                json={
                    "cmd": "request.get",
                    "url": url,
                    "maxTimeout": timeout_ms,
                    "returnOnlyCookies": False,
                },
                timeout=(5, timeout_ms / 1000 + 10),
            )
        except requests.exceptions.ConnectTimeout:
            return failed(FetchFailure.CONNECTION)
        except requests.exceptions.ReadTimeout:
            return failed(FetchFailure.TIMEOUT)
        except requests.exceptions.ConnectionError:
            return failed(FetchFailure.CONNECTION)
        except requests.exceptions.RequestException:
            return failed(FetchFailure.PROVIDER)

        if response.status_code in (408, 504):
            return failed(FetchFailure.TIMEOUT, response.status_code)
        if response.status_code != 200:
            return failed(FetchFailure.API_HTTP, response.status_code)
        try:
            data = response.json()
        except ValueError:
            return failed(FetchFailure.INVALID_RESPONSE, response.status_code)
        if not isinstance(data, dict) or "status" not in data:
            return failed(FetchFailure.INVALID_RESPONSE, response.status_code)
        if data["status"] != "ok":
            return failed(FetchFailure.PROVIDER, response.status_code)
        if not isinstance(data.get("solution"), dict):
            return failed(FetchFailure.INVALID_RESPONSE, response.status_code)

        solution = data["solution"]
        html = solution.get("response")
        final_url = solution.get("url")
        reported_status = solution.get("status")
        if not isinstance(html, str) or not isinstance(final_url, str):
            return failed(FetchFailure.INVALID_RESPONSE, response.status_code)
        if not html.strip():
            return failed(FetchFailure.EMPTY, response.status_code)
        if not isinstance(reported_status, int):
            return failed(FetchFailure.INVALID_RESPONSE, response.status_code)
        target_status = reported_status if self.provider == "flaresolverr" else None
        if target_status is not None and target_status != 200:
            return failed(FetchFailure.TARGET_HTTP, response.status_code)
        cookies = solution.get("cookies")
        if not isinstance(cookies, list):
            cookies = []
        return PageResult(
            html=html,
            final_url=final_url,
            provider=self.provider,
            elapsed_ms=round((monotonic() - started) * 1000),
            cookies=tuple(c for c in cookies if isinstance(c, dict)),
            user_agent=str(solution.get("userAgent") or ""),
            provider_status=response.status_code,
            target_status=target_status,
        )


class ByparrPageClient(_V1BrowserClient):
    provider = "byparr"


class FlareSolverrPageClient(_V1BrowserClient):
    provider = "flaresolverr"
