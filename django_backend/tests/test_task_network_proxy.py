"""Actual curl requests must honor configured proxies inside controlled scraping."""

from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread
from urllib.parse import urlsplit

from curl_cffi import requests

import pytest

from nassav.scraper.Javbus import Javbus, Busdmm, Dmmsee
from nassav.task_network import TaskBrowserSession, TaskNetworkControl


_REAL_REQUEST = requests.Session.request


@pytest.fixture(autouse=True)
def refactoring_offline_network_guard(monkeypatch):
    """This module permits actual curl only to its loopback HTTP fixtures."""

    def local_request(session, method, url, **kwargs):
        assert urlsplit(url).hostname == "127.0.0.1"
        proxies = [kwargs.get("proxy"), *(kwargs.get("proxies") or {}).values()]
        for proxy in proxies:
            if proxy:
                assert urlsplit(proxy).hostname == "127.0.0.1"
        return _REAL_REQUEST(session, method, url, **kwargs)

    monkeypatch.setattr(requests.Session, "request", local_request)
    for name in (
        "HTTP_PROXY",
        "HTTPS_PROXY",
        "ALL_PROXY",
        "http_proxy",
        "https_proxy",
        "all_proxy",
        "NO_PROXY",
        "no_proxy",
    ):
        monkeypatch.delenv(name, raising=False)


@contextmanager
def endpoint(body, *, required_referer=None):
    calls = []

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            calls.append(self.path)
            self.send_response(
                200
                if required_referer is None
                or self.headers.get("Referer") == required_referer
                else 403
            )
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_POST(self):
            self.do_GET()

        def do_CONNECT(self):
            calls.append(self.path)
            self.send_response(502)
            self.send_header("Content-Length", "0")
            self.end_headers()

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}", calls
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


@pytest.mark.parametrize("scraper_type", [Javbus, Busdmm, Dmmsee])
@pytest.mark.parametrize("operation", ["html", "cover", "avatar"])
def test_controlled_scraper_uses_proxy_for_all_io(
    scraper_type, operation, tmp_path, monkeypatch
):
    monkeypatch.setenv("NO_PROXY", "*")
    monkeypatch.setenv("no_proxy", "*")
    with (
        endpoint(b"direct") as (origin, origin_calls),
        endpoint(b"proxied") as (proxy, proxy_calls),
    ):
        scraper = scraper_type(proxy=proxy)
        scraper.set_task_control(TaskNetworkControl(lambda: None))
        target = f"{origin}/FIXTURE-1"
        if operation == "html":
            assert scraper.fetch_html(target) == "proxied"
        else:
            dest = tmp_path / f"{operation}.jpg"
            if operation == "cover":
                assert scraper.download_cover(target, str(dest))
            else:
                assert scraper.download_avatar(target, str(dest), max_retries=1)
            assert dest.read_bytes() == b"proxied"
        assert proxy_calls == [target]
        assert origin_calls == []


def test_task_browser_control_stays_direct_despite_environment_proxy(monkeypatch):
    with (
        endpoint(b"direct") as (origin, origin_calls),
        endpoint(b"environment") as (proxy, proxy_calls),
    ):
        for name in (
            "HTTP_PROXY",
            "HTTPS_PROXY",
            "ALL_PROXY",
            "http_proxy",
            "https_proxy",
            "all_proxy",
        ):
            monkeypatch.setenv(name, proxy)
        monkeypatch.setenv("NO_PROXY", "")
        monkeypatch.setenv("no_proxy", "")
        browser = TaskBrowserSession(TaskNetworkControl(lambda: None))
        response = browser.post(f"{origin}/v1", timeout=(1, 2), json={})
        assert response.content == b"direct"
        assert origin_calls == ["/v1"]
        assert proxy_calls == []


@pytest.mark.parametrize("scraper_type", [Javbus, Busdmm, Dmmsee])
def test_scraper_https_page_uses_proxy_connect(scraper_type):
    with endpoint(b"direct") as (origin, _), endpoint(b"proxy") as (proxy, proxy_calls):
        scraper = scraper_type(proxy=proxy)
        scraper.domain = origin.removeprefix("http://")
        scraper.set_task_control(TaskNetworkControl(lambda: None))
        # The local proxy deliberately refuses the tunnel. Reaching CONNECT proves
        # get_html's actual HTTPS path used the proxy, without external TLS traffic.
        assert scraper.get_html("FIXTURE-1") is None
        assert proxy_calls == [scraper.domain]


@pytest.mark.parametrize("proxy_argument", ["proxy", "proxies"])
def test_explicit_proxy_wins_over_environment(proxy_argument, monkeypatch):
    with (
        endpoint(b"direct") as (origin, origin_calls),
        endpoint(b"configured") as (proxy, proxy_calls),
        endpoint(b"environment") as (environment, environment_calls),
    ):
        monkeypatch.setenv("HTTP_PROXY", environment)
        monkeypatch.setenv("http_proxy", environment)
        options = {
            proxy_argument: proxy
            if proxy_argument == "proxy"
            else {"http": proxy, "https": proxy}
        }
        response = TaskNetworkControl(lambda: None).request(
            "GET", origin, timeout=2, **options
        )
        assert response.content == b"configured"
        assert proxy_calls == [f"{origin}/"]
        assert not origin_calls and not environment_calls


@pytest.mark.parametrize("operation", ["page", "cover"])
def test_recommendation_worker_source_uses_global_proxy(
    operation, settings, tmp_path, monkeypatch
):
    from nassav.composition import build_recommendation_manager

    monkeypatch.setenv("NO_PROXY", "*")
    with (
        endpoint(b"direct") as (origin, origin_calls),
        endpoint(b"proxied") as (proxy, proxy_calls),
    ):
        settings.PROXY_ENABLED = True
        settings.PROXY_URL = proxy
        settings.SOURCE_CONFIG = {"jable": {"weight": 1}}
        control = TaskNetworkControl(lambda: None)
        manager = build_recommendation_manager(control=control)
        source = manager.build_recommender(
            "jable_page_lookup", manager.get_strategy()
        ).jable
        target = f"{origin}/fixture"
        if operation == "page":
            assert source.fetch_html(target) == "proxied"
        else:
            dest = tmp_path / "recommendation-cover.jpg"
            assert source.download_file(target, str(dest))
            assert dest.read_bytes() == b"proxied"
        assert proxy_calls == [target]
        assert origin_calls == []


@pytest.mark.parametrize("controlled", [False, True])
def test_missav_playlist_uses_source_proxy_and_referer(controlled, monkeypatch):
    from nassav.source.MissAV import MissAV

    referer = "https://missav.ai/dm17/cn/ipzz-912-chinese-subtitle"
    body = (
        b"#EXTM3U\n#EXT-X-STREAM-INF:BANDWIDTH=1000,RESOLUTION=1920x1080\n1080.m3u8\n"
    )
    monkeypatch.setenv("NO_PROXY", "*")
    monkeypatch.setenv("no_proxy", "*")
    with (
        endpoint(b"direct forbidden", required_referer="never") as (
            origin,
            origin_calls,
        ),
        endpoint(body, required_referer=referer) as (proxy, proxy_calls),
    ):
        source = MissAV(proxy)
        if controlled:
            source.set_task_control(TaskNetworkControl(lambda: None))
        target = f"{origin}/video/playlist.m3u8"
        assert source._get_highest_quality_m3u8(target, referer=referer) == (
            f"{origin}/video/1080.m3u8",
            "1920x1080",
        )
        assert proxy_calls == [target]
        assert origin_calls == []
