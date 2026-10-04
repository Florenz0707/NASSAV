"""P3 single-flight behavior across request sources and legacy Cookie API."""

import time
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from importlib import import_module
from threading import Barrier, Event, Lock, Thread

import pytest
import redis
from curl_cffi.requests.exceptions import HTTPError
from django.utils import timezone
from nassav.page_fetching import BrowserPageClient, PageFetchService, PageResult
from nassav.page_fetching.coordination import refresh_key
from nassav.source.CookieRepository import SourceCookieRecord, source_cookie_repository
from nassav.source.Jable import Jable
from nassav.source.MissAV import MissAV
from nassav.source.SourceManager import SourceManager

URL = "https://jable.tv/videos/jur-466/"
HTML = '<title>JUR-466 Sample - Jable.TV</title><script>var hlsUrl = "https://video.test/master.m3u8";</script>'
PROXY = "http://proxy.test:8080"

pytestmark = pytest.mark.usefixtures("fake_session_store")


class FakeBrowser(BrowserPageClient):
    provider = "byparr"

    def __init__(self, *, delay=0.0, url=URL, html=HTML, cookies=None, ua="browser-UA"):
        self.delay = delay
        self.url = url
        self.html = html
        self.cookies = cookies or (
            {
                "name": "session",
                "value": "new",
                "domain": "jable.tv",
                "path": "/",
                "expires": (timezone.now() + timedelta(minutes=10)).timestamp(),
            },
        )
        self.ua = ua
        self.calls = 0
        self.mutex = Lock()

    def fetch(self, url, *, timeout_ms):
        with self.mutex:
            self.calls += 1
        time.sleep(self.delay)
        return PageResult(
            html=self.html,
            final_url=self.url,
            provider="byparr",
            user_agent=self.ua,
            cookies=self.cookies,
        )


class DirectResponse:
    def __init__(self, *, status=200, html=HTML, url=URL):
        self.status_code = status
        self.text = html
        self.url = url

    def raise_for_status(self):
        if self.status_code >= 400:
            raise HTTPError("denied", response=self)


class MemorySessions:
    def __init__(self):
        self.record = None
        self.mutex = Lock()
        self.writes = 0

    def read(self, _name):
        with self.mutex:
            return self.record

    def save(
        self,
        _name,
        *,
        expected_updated_at,
        cookie,
        user_agent,
        expires_at,
        egress_profile,
        write_guard=None,
    ):
        with self.mutex:
            actual = self.record.updated_at if self.record else None
            if actual != expected_updated_at or (write_guard and not write_guard()):
                return None
            self.writes += 1
            self.record = SourceCookieRecord(
                "jable",
                cookie,
                f"v{self.writes}",
                user_agent,
                expires_at,
                egress_profile,
            )
            return self.record

    def manual(self, cookie):
        with self.mutex:
            self.writes += 1
            self.record = SourceCookieRecord("jable", cookie, f"v{self.writes}")


@pytest.fixture
def memory_sessions(monkeypatch):
    sessions = MemorySessions()
    monkeypatch.setattr(source_cookie_repository, "get_cookie_record", sessions.read)
    monkeypatch.setattr(
        source_cookie_repository, "set_session_if_version", sessions.save
    )
    return sessions


def direct_get(_url, **kwargs):
    if kwargs["headers"].get("Cookie") == "session=new":
        return DirectResponse()
    return DirectResponse(status=403, html="denied")


def direct_first(settings):
    settings.SOURCE_CONFIG = {
        **settings.SOURCE_CONFIG,
        "jable": {"browser_fetch_strategy": "direct_first"},
    }


def test_ten_concurrent_403_requests_share_one_browser_refresh(
    settings, monkeypatch, memory_sessions
):
    direct_first(settings)
    browser = FakeBrowser(delay=0.15)
    monkeypatch.setattr(
        import_module("nassav.source.SourceBase").requests, "get", direct_get
    )
    sources = [
        Jable(proxy=PROXY, page_fetcher=PageFetchService(browser)) for _ in range(10)
    ]
    barrier = Barrier(11)

    def lookup(source):
        barrier.wait()
        return source.get_html("JUR-466")

    with ThreadPoolExecutor(max_workers=10) as pool:
        futures = [pool.submit(lookup, source) for source in sources]
        barrier.wait()
        results = [future.result(timeout=5) for future in futures]

    assert results == [HTML] * 10
    assert browser.calls == 1
    assert memory_sessions.writes == 1
    assert memory_sessions.record.cookie == "session=new"


def test_redis_disconnect_uses_browser_without_shared_write(
    settings, monkeypatch, memory_sessions, fake_session_store
):
    direct_first(settings)
    browser = FakeBrowser()
    source = Jable(proxy=PROXY, page_fetcher=PageFetchService(browser))
    monkeypatch.setattr(
        import_module("nassav.source.SourceBase").requests, "get", direct_get
    )
    monkeypatch.setattr(
        fake_session_store,
        "acquire",
        lambda *_args: (_ for _ in ()).throw(redis.ConnectionError("offline")),
    )
    assert source.get_html("JUR-466") == HTML
    assert browser.calls == 1
    assert memory_sessions.writes == 0


def test_expired_owner_cannot_write_and_new_owner_can(
    settings, monkeypatch, memory_sessions, fake_session_store
):
    direct_first(settings)
    entered = Event()
    resume = Event()
    first_browser = FakeBrowser()
    original_fetch = first_browser.fetch

    def delayed_fetch(url, *, timeout_ms):
        entered.set()
        assert resume.wait(3)
        return original_fetch(url, timeout_ms=timeout_ms)

    monkeypatch.setattr(first_browser, "fetch", delayed_fetch)
    monkeypatch.setattr(
        import_module("nassav.source.SourceBase").requests, "get", direct_get
    )
    first = Jable(proxy=PROXY, page_fetcher=PageFetchService(first_browser))
    first_result = []
    thread = Thread(target=lambda: first_result.append(first.get_html("JUR-466")))
    thread.start()
    assert entered.wait(3)
    key = next(iter(fake_session_store.locks))
    fake_session_store.expire(key)

    second_browser = FakeBrowser()
    second = Jable(proxy=PROXY, page_fetcher=PageFetchService(second_browser))
    assert second.get_html("JUR-466") == HTML
    resume.set()
    thread.join(3)
    assert not thread.is_alive()
    assert first_result == [HTML]
    assert memory_sessions.writes == 1
    assert second_browser.calls == 1
    assert fake_session_store.locks == {}


def test_crashed_owner_wait_is_bounded_then_browser_falls_back(
    settings, monkeypatch, memory_sessions, fake_session_store
):
    direct_first(settings)
    browser = FakeBrowser()
    source = Jable(proxy=PROXY, page_fetcher=PageFetchService(browser))
    monkeypatch.setattr(
        import_module("nassav.source.SourceBase").requests, "get", direct_get
    )
    original_acquire = fake_session_store.acquire

    def crashed_owner(key, owner, ttl):
        original_acquire(key, "crashed", ttl)
        fake_session_store.expire(key)
        return False, "crashed"

    monkeypatch.setattr(fake_session_store, "acquire", crashed_owner)
    assert source.get_html("JUR-466") == HTML
    assert browser.calls == 1
    assert memory_sessions.writes == 0


def test_manual_update_during_browser_fetch_rejects_late_result(
    settings, monkeypatch, memory_sessions
):
    direct_first(settings)
    browser = FakeBrowser()
    original_fetch = browser.fetch

    def fetch_and_manual(url, *, timeout_ms):
        memory_sessions.manual("manual=new")
        return original_fetch(url, timeout_ms=timeout_ms)

    monkeypatch.setattr(browser, "fetch", fetch_and_manual)
    monkeypatch.setattr(
        import_module("nassav.source.SourceBase").requests, "get", direct_get
    )
    source = Jable(proxy=PROXY, page_fetcher=PageFetchService(browser))
    assert source.get_html("JUR-466") == HTML
    assert memory_sessions.record.cookie == "manual=new"
    assert memory_sessions.writes == 1


def test_unusable_session_suppresses_probe_but_not_other_pages_browser(
    settings, monkeypatch, memory_sessions, fake_session_store
):
    direct_first(settings)
    browser = FakeBrowser()
    monkeypatch.setattr(
        import_module("nassav.source.SourceBase").requests,
        "get",
        lambda *_args, **_kwargs: DirectResponse(status=403, html="denied"),
    )
    sources = [
        Jable(proxy=PROXY, page_fetcher=PageFetchService(browser)) for _ in range(2)
    ]
    probes = []
    for source in sources:
        original = source.fetch_page

        def track(*args, _original=original, **kwargs):
            if kwargs.get("session_override") is not None:
                probes.append(1)
            return _original(*args, **kwargs)

        monkeypatch.setattr(source, "fetch_page", track)
    assert sources[0].get_html("JUR-466") == HTML
    assert sources[1].get_html("JUR-467") == HTML
    assert browser.calls == 2
    assert len(probes) == 1
    assert memory_sessions.writes == 0
    assert fake_session_store.unusable


def test_refresh_keys_isolate_site_and_route():
    first = refresh_key("JABLE", URL, "route-a")
    assert first == refresh_key("jable", URL, "route-a")
    assert first != refresh_key("MissAV", URL, "route-a")
    assert first != refresh_key("Jable", URL, "route-b")
    assert first != refresh_key("Jable", "https://other.test/video", "route-a")
    assert "proxy.test" not in first


@pytest.mark.django_db
def test_old_auto_cookie_api_uses_same_lease_and_preserves_response(
    client, monkeypatch, fake_session_store
):
    import nassav.http.source_views as views

    home = "https://missav.ai/"
    browser = FakeBrowser(
        url=home,
        html="<html>MissAV home</html>",
        cookies=({"name": "session", "value": "new", "domain": "missav.ai"},),
    )
    manager = SourceManager.__new__(SourceManager)
    manager.sources = {
        "MissAV": MissAV(proxy=PROXY, page_fetcher=PageFetchService(browser))
    }
    monkeypatch.setattr(views, "source_manager", manager)
    response = client.post(
        "/nassav/api/source/cookie",
        data={"source": "MissAV", "auto": True},
        content_type="application/json",
    )
    assert response.status_code == 200
    assert response.json()["data"] == {"source": "MissAV", "cookie_set": True}
    assert browser.calls == 1
    assert source_cookie_repository.get_cookie("MissAV") == "session=new"
    assert fake_session_store.locks == {}


def test_different_sites_acquire_independent_leases(fake_session_store):
    from nassav.page_fetching.coordination import session_refresh_coordinator

    first_key = refresh_key("Jable", URL, "route-a")
    second_key = refresh_key("MissAV", "https://missav.ai/cn/example", "route-a")
    first, first_busy = session_refresh_coordinator.acquire(first_key, 60000)
    second, second_busy = session_refresh_coordinator.acquire(second_key, 60000)
    try:
        assert first is not None and second is not None
        assert first_busy is None and second_busy is None
        assert first.owned() and second.owned()
    finally:
        first.close("unusable")
        second.close("unusable")


def test_busy_owner_timeout_falls_back_without_write(
    settings, monkeypatch, memory_sessions, fake_session_store
):
    direct_first(settings)
    browser = FakeBrowser()
    source = Jable(proxy=PROXY, page_fetcher=PageFetchService(browser))
    monkeypatch.setattr(
        import_module("nassav.source.SourceBase").requests, "get", direct_get
    )
    original_acquire = fake_session_store.acquire

    def permanent_owner(actual_key, owner, ttl):
        original_acquire(actual_key, "stuck", ttl)
        return False, "stuck"

    monkeypatch.setattr(fake_session_store, "acquire", permanent_owner)
    import nassav.page_fetching.coordination as coordination

    monkeypatch.setattr(coordination, "lease_seconds", lambda _timeout_ms: -5)
    assert source.get_html("JUR-466") == HTML
    assert browser.calls == 1
    assert memory_sessions.writes == 0


def test_two_old_auto_entrypoints_share_refresh_result(
    monkeypatch, memory_sessions, fake_session_store
):
    entered = Event()
    continue_fetch = Event()
    calls = []

    class AutoSource:
        proxy = PROXY
        page_fetcher = PageFetchService(None)

        def __init__(self):
            self.cookie = ""

        def get_source_name(self):
            return "Jable"

        def get_home_url(self):
            return "https://jable.tv/"

        def set_session(self, record):
            self.cookie = record.cookie

        def set_cookie_auto(self, *, force_refresh, write_guard):
            calls.append(1)
            entered.set()
            assert continue_fetch.wait(3)
            assert write_guard()
            memory_sessions.manual("automatic=new")
            return True

    first = SourceManager.__new__(SourceManager)
    first.sources = {"Jable": AutoSource()}
    second = SourceManager.__new__(SourceManager)
    second.sources = {"Jable": AutoSource()}
    results = []
    first_thread = Thread(
        target=lambda: results.append(first.auto_source_cookie("Jable"))
    )
    second_thread = Thread(
        target=lambda: results.append(second.auto_source_cookie("Jable"))
    )
    first_thread.start()
    assert entered.wait(3)
    second_thread.start()
    time.sleep(0.05)
    continue_fetch.set()
    first_thread.join(3)
    second_thread.join(3)
    assert not first_thread.is_alive() and not second_thread.is_alive()
    assert results == [True, True]
    assert calls == [1]
    assert memory_sessions.record.cookie == "automatic=new"


@pytest.mark.django_db
def test_old_auto_cookie_late_result_does_not_replace_manual_write(
    client, monkeypatch, fake_session_store
):
    import nassav.http.source_views as views

    home = "https://missav.ai/"
    browser = FakeBrowser(
        url=home,
        html="<html>MissAV home</html>",
        cookies=({"name": "session", "value": "automatic", "domain": "missav.ai"},),
    )
    original_fetch = browser.fetch

    def fetch_and_update(url, *, timeout_ms):
        source_cookie_repository.set_cookie("MissAV", "manual=new")
        return original_fetch(url, timeout_ms=timeout_ms)

    monkeypatch.setattr(browser, "fetch", fetch_and_update)
    manager = SourceManager.__new__(SourceManager)
    manager.sources = {
        "MissAV": MissAV(proxy=PROXY, page_fetcher=PageFetchService(browser))
    }
    monkeypatch.setattr(views, "source_manager", manager)
    response = client.post(
        "/nassav/api/source/cookie",
        data={"source": "MissAV", "auto": True},
        content_type="application/json",
    )
    assert response.status_code == 500
    assert source_cookie_repository.get_cookie("MissAV") == "manual=new"


@pytest.mark.django_db
def test_jable_legacy_auto_cookie_uses_versioned_write(
    client, monkeypatch, fake_session_store
):
    import nassav.http.source_views as views

    class Cookies:
        def get_dict(self):
            return {"legacy": "new"}

    class Session:
        cookies = Cookies()

        def get(self, *_args, **_kwargs):
            return DirectResponse()

    monkeypatch.setattr(
        import_module("nassav.source.SourceBase").requests,
        "Session",
        Session,
    )
    manager = SourceManager.__new__(SourceManager)
    manager.sources = {"Jable": Jable(proxy=PROXY, page_fetcher=PageFetchService(None))}
    monkeypatch.setattr(views, "source_manager", manager)
    response = client.post(
        "/nassav/api/source/cookie",
        data={"source": "Jable", "auto": True},
        content_type="application/json",
    )
    assert response.status_code == 200
    record = source_cookie_repository.get_cookie_record("Jable")
    assert record is not None and record.cookie == "legacy=new"
    assert record.user_agent is None and record.egress_profile is None
    assert fake_session_store.locks == {}


@pytest.mark.django_db
def test_auto_api_redis_disconnect_preserves_existing_cookie(
    client, monkeypatch, fake_session_store
):
    import nassav.http.source_views as views

    source_cookie_repository.set_cookie("MissAV", "manual=old")
    browser = FakeBrowser(url="https://missav.ai/", html="MissAV home")
    manager = SourceManager.__new__(SourceManager)
    manager.sources = {
        "MissAV": MissAV(proxy=PROXY, page_fetcher=PageFetchService(browser))
    }
    monkeypatch.setattr(views, "source_manager", manager)
    monkeypatch.setattr(
        fake_session_store,
        "acquire",
        lambda *_args: (_ for _ in ()).throw(redis.ConnectionError("offline")),
    )
    response = client.post(
        "/nassav/api/source/cookie",
        data={"source": "MissAV", "auto": True},
        content_type="application/json",
    )
    assert response.status_code == 500
    assert browser.calls == 0
    assert source_cookie_repository.get_cookie("MissAV") == "manual=old"
