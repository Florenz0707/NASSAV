"""Adapters for the GET subset shared by Byparr and FlareSolverr."""

from time import monotonic
from urllib.parse import unquote, urlsplit, urlunsplit

import requests

from .contracts import BrowserPageClient, FetchFailure, PageResult


class _V1BrowserClient(BrowserPageClient):
    provider = ""

    def __init__(self, base_url: str):
        self.base_url = base_url.rstrip("/")
        self._session = requests.Session()
        # The control request must not inherit the target-site proxy from the host.
        self._session.trust_env = False

    def _request_headers(self) -> dict[str, str]:
        return {}

    def set_task_transport(self, session) -> None:
        """Install transport only on a newly constructed task-local adapter."""
        self._session.close()
        self._session = session

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

        request_options = {}
        headers = self._request_headers()
        if headers:
            request_options["headers"] = headers
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
                **request_options,
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

    def __init__(self, base_url: str, *, proxy_url: str | None = None):
        super().__init__(base_url)
        self._proxy_headers = _byparr_proxy_headers(proxy_url) if proxy_url else {}

    def _request_headers(self) -> dict[str, str]:
        return self._proxy_headers


def _byparr_proxy_headers(proxy_url: str) -> dict[str, str]:
    """Translate a host proxy URL into Byparr's per-request browser headers."""
    parsed = urlsplit(proxy_url)
    try:
        port = parsed.port
    except ValueError as error:
        raise ValueError("Proxy.url has an invalid port") from error
    if (
        parsed.scheme not in {"http", "https", "socks5"}
        or not parsed.hostname
        or parsed.path not in {"", "/"}
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError("Proxy.url must be an absolute proxy URL without a path")

    host = parsed.hostname
    if host in {"localhost", "127.0.0.1", "::1"}:
        host = "host.docker.internal"
    elif ":" in host:
        host = f"[{host}]"
    server = urlunsplit((parsed.scheme, f"{host}:{port}" if port else host, "", "", ""))
    headers = {"X-Proxy-Server": server}
    if parsed.username is not None:
        headers["X-Proxy-Username"] = unquote(parsed.username)
    if parsed.password is not None:
        headers["X-Proxy-Password"] = unquote(parsed.password)
    return headers


class FlareSolverrPageClient(_V1BrowserClient):
    provider = "flaresolverr"
