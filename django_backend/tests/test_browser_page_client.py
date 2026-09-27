"""Offline protocol contract tests for browser page providers."""

import requests
from nassav.page_fetching.browser import ByparrPageClient, FlareSolverrPageClient
from nassav.page_fetching.contracts import FetchFailure


class FakeResponse:
    status_code = 200

    def __init__(self, data=None, *, status_code=200, invalid_json=False):
        self.data = data
        self.status_code = status_code
        self.invalid_json = invalid_json

    def json(self):
        if self.invalid_json:
            raise ValueError("bad JSON")
        return self.data


def test_byparr_get_protocol_and_untrusted_target_status(monkeypatch):
    client = ByparrPageClient("http://127.0.0.1:8192/")
    seen = {}

    def post(url, **kwargs):
        seen.update(url=url, **kwargs)
        return FakeResponse(
            {
                "status": "ok",
                "solution": {
                    "url": "https://site.test/page",
                    "status": 200,
                    "response": "<html>valid</html>",
                    "cookies": [{"name": "a", "value": "b"}],
                    "userAgent": "UA",
                },
            }
        )

    monkeypatch.setattr(client._session, "post", post)
    result = client.fetch("https://site.test/page", timeout_ms=60000)
    assert result.ok and result.target_status is None and result.provider_status == 200
    assert result.cookies[0]["name"] == "a" and result.user_agent == "UA"
    assert seen["url"] == "http://127.0.0.1:8192/v1"
    assert seen["json"] == {
        "cmd": "request.get",
        "url": "https://site.test/page",
        "maxTimeout": 60000,
        "returnOnlyCookies": False,
    }
    assert seen["timeout"] == (5, 70)
    assert client._session.trust_env is False


def test_flaresolverr_reports_target_status(monkeypatch):
    client = FlareSolverrPageClient("http://localhost:8191")
    monkeypatch.setattr(
        client._session,
        "post",
        lambda *_args, **_kwargs: FakeResponse(
            {
                "status": "ok",
                "solution": {
                    "url": "https://site.test/",
                    "status": 404,
                    "response": "not found",
                },
            }
        ),
    )
    assert (
        client.fetch("https://site.test/", timeout_ms=60000).failure
        == FetchFailure.TARGET_HTTP
    )


def test_browser_error_classification(monkeypatch):
    client = ByparrPageClient("http://localhost:8192")
    cases = [
        (FakeResponse(status_code=408), FetchFailure.TIMEOUT),
        (FakeResponse(status_code=502), FetchFailure.API_HTTP),
        (FakeResponse(invalid_json=True), FetchFailure.INVALID_RESPONSE),
        (FakeResponse({"status": "ok"}), FetchFailure.INVALID_RESPONSE),
        (FakeResponse({"status": "error"}), FetchFailure.PROVIDER),
        (
            FakeResponse(
                {
                    "status": "ok",
                    "solution": {
                        "url": "https://site.test/",
                        "status": 200,
                        "response": "",
                    },
                }
            ),
            FetchFailure.EMPTY,
        ),
    ]
    for response, expected in cases:
        monkeypatch.setattr(client._session, "post", lambda *_a, **_k: response)
        assert client.fetch("https://site.test/", timeout_ms=60000).failure == expected

    def disconnected(*_args, **_kwargs):
        raise requests.exceptions.ConnectionError("offline")

    monkeypatch.setattr(client._session, "post", disconnected)
    assert (
        client.fetch("https://site.test/", timeout_ms=60000).failure
        == FetchFailure.CONNECTION
    )


def test_byparr_uses_project_proxy_for_browser_only(monkeypatch):
    client = ByparrPageClient(
        "http://127.0.0.1:8192",
        proxy_url="http://user%40example:p%3Ass@127.0.0.1:7890",
    )
    seen = {}

    def post(url, **kwargs):
        seen.update(url=url, **kwargs)
        return FakeResponse(
            {
                "status": "ok",
                "solution": {
                    "url": "https://site.test/",
                    "status": 200,
                    "response": "<html>valid</html>",
                },
            }
        )

    monkeypatch.setattr(client._session, "post", post)
    assert client.fetch("https://site.test/", timeout_ms=60000).ok
    assert seen["url"] == "http://127.0.0.1:8192/v1"
    assert seen["headers"] == {
        "X-Proxy-Server": "http://host.docker.internal:7890",
        "X-Proxy-Username": "user@example",
        "X-Proxy-Password": "p:ss",
    }
    assert client._session.trust_env is False


def test_byparr_preserves_remote_proxy_host_and_omits_headers_when_disabled(
    monkeypatch,
):
    seen = {}
    direct = ByparrPageClient("http://localhost:8192")
    monkeypatch.setattr(
        direct._session,
        "post",
        lambda _url, **kwargs: seen.update(kwargs) or FakeResponse(status_code=502),
    )
    direct.fetch("https://site.test/", timeout_ms=60000)
    assert "headers" not in seen

    proxied = ByparrPageClient(
        "http://localhost:8192", proxy_url="socks5://proxy.example:1080"
    )
    assert proxied._request_headers() == {
        "X-Proxy-Server": "socks5://proxy.example:1080"
    }


def test_flaresolverr_does_not_receive_byparr_proxy_headers(monkeypatch):
    client = FlareSolverrPageClient("http://localhost:8191")
    seen = {}
    monkeypatch.setattr(
        client._session,
        "post",
        lambda _url, **kwargs: seen.update(kwargs) or FakeResponse(status_code=502),
    )
    client.fetch("https://site.test/", timeout_ms=60000)
    assert "headers" not in seen
