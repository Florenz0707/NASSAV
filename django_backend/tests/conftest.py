import pytest
from nassav.models import Actor, AVResource


def pytest_collection_modifyitems(items):
    from django.conf import settings

    if not getattr(settings, "NASSAV_REFACTORING_OFFLINE", False):
        return
    for item in items:
        if item.get_closest_marker("external"):
            item.add_marker(
                pytest.mark.skip(reason="Live service test outside offline gate")
            )


@pytest.fixture(autouse=True)
def refactoring_offline_network_guard(monkeypatch, settings):
    """Fail even when application error handling swallows unmocked network use."""
    if not getattr(settings, "NASSAV_REFACTORING_OFFLINE", False):
        yield
        return

    import socket

    import requests
    from curl_cffi import requests as curl_requests

    attempts = []

    def blocked(*args, **kwargs):
        attempts.append("unmocked network request")
        raise AssertionError("Offline tests must replace the network transport")

    original_connect = socket.socket.connect

    def connect(sock, address):
        if sock.family in {socket.AF_INET, socket.AF_INET6}:
            return blocked()
        return original_connect(sock, address)

    monkeypatch.setattr(requests.Session, "request", blocked)
    monkeypatch.setattr(curl_requests.Session, "request", blocked)
    monkeypatch.setattr(socket.socket, "connect", connect)
    yield
    assert not attempts, "Unmocked network use was caught by the offline guard"


@pytest.fixture
def actor_factory(db):
    """返回一个可创建 Actor 的工厂函数"""

    def _create(**kwargs):
        defaults = {"name": "测试演员", "avatar_url": None, "avatar_filename": None}
        defaults.update(kwargs)
        return Actor.objects.create(**defaults)

    return _create


@pytest.fixture
def resource_factory(db):
    """返回一个可创建 AVResource 的工厂函数"""

    def _create(**kwargs):
        defaults = {"avid": "TEST-001", "original_title": "测试作品", "source": "test"}
        defaults.update(kwargs)
        res = AVResource.objects.create(**defaults)
        return res

    return _create


@pytest.fixture
def genre_factory(db):
    from nassav.models import Genre

    def _create(**kwargs):
        defaults = {"name": "测试类别"}
        defaults.update(kwargs)
        return Genre.objects.create(**defaults)

    return _create


@pytest.fixture
def operator_user(db, django_user_model, settings):
    """An isolated account matching the configured single operator."""
    return django_user_model.objects.create_user(
        username=settings.NASSAV_OPERATOR_USERNAME,
        password="p0-p1-test-only-password",
    )


@pytest.fixture
def api_client(operator_user):
    """Authenticated DRF client for existing business behavior tests."""
    from rest_framework.test import APIClient

    test_client = APIClient()
    test_client.force_login(operator_user)
    return test_client


@pytest.fixture
def client(operator_user):
    """Authenticated Django client for existing business behavior tests."""
    from django.test import Client

    test_client = Client()
    test_client.force_login(operator_user)
    return test_client


@pytest.fixture
def ws_headers(client, settings):
    """Same-origin WebSocket headers carrying the test operator session."""
    from django.conf import settings

    settings.CHANNEL_LAYERS = {
        "default": {"BACKEND": "channels.layers.InMemoryChannelLayer"}
    }
    session_cookie = settings.SESSION_COOKIE_NAME
    return [
        (b"host", b"localhost"),
        (b"origin", b"http://localhost"),
        (
            b"cookie",
            f"{session_cookie}={client.cookies[session_cookie].value}".encode(),
        ),
    ]


@pytest.fixture
def assert_api_response():
    """验证 API 响应格式的辅助函数"""

    def _assert(response, expected_code=200):
        assert response.status_code == expected_code
        data = response.json()
        assert "code" in data
        assert data["code"] == expected_code
        return data

    return _assert


@pytest.fixture
def resource_with_actors(db, resource_factory, actor_factory):
    """创建一个带有演员的资源"""

    def _create(actor_names, **resource_kwargs):
        resource = resource_factory(**resource_kwargs)
        for name in actor_names:
            actor = actor_factory(name=name)
            resource.actors.add(actor)
        return resource

    return _create


@pytest.fixture
def resource_with_genres(db, resource_factory, genre_factory):
    """创建一个带有类别的资源"""

    def _create(genre_names, **resource_kwargs):
        resource = resource_factory(**resource_kwargs)
        for name in genre_names:
            genre = genre_factory(name=name)
            resource.genres.add(genre)
        return resource

    return _create


@pytest.fixture
def bulk_resources(resource_factory):
    """批量创建资源"""

    def _create(count, **defaults):
        resources = []
        for i in range(count):
            kwargs = defaults.copy()
            if "avid" not in kwargs:
                kwargs["avid"] = f"TEST-{i + 1:03d}"
            if "original_title" not in kwargs:
                kwargs["original_title"] = f"测试作品{i + 1}"
            resources.append(resource_factory(**kwargs))
        return resources

    return _create


from nassav.page_fetching.coordination import RefreshStore


class FakeSessionRefreshStore(RefreshStore):
    """Process-shared Redis lease behavior for offline session tests."""

    def __init__(self):
        import threading

        self.mutex = threading.Lock()
        self.locks = {}
        self.results = {}
        self.unusable = set()

    def acquire(self, key, owner, ttl):
        with self.mutex:
            if key in self.locks:
                return False, self.locks[key]
            self.locks[key] = owner
            return True, None

    def owner(self, key):
        with self.mutex:
            return self.locks.get(key)

    def renew(self, key, owner, ttl):
        return self.owner(key) == owner

    def release(self, key, owner, outcome):
        with self.mutex:
            if self.locks.get(key) != owner:
                return False
            self.results[key] = owner + ":" + outcome
            del self.locks[key]
            return True

    def outcome(self, key):
        with self.mutex:
            return self.results.get(key)

    def mark_unusable(self, key):
        with self.mutex:
            self.unusable.add(key)

    def recently_unusable(self, key):
        with self.mutex:
            return key in self.unusable

    def clear_unusable(self, key):
        with self.mutex:
            self.unusable.discard(key)

    def expire(self, key):
        with self.mutex:
            self.locks.pop(key, None)


@pytest.fixture
def fake_session_store(monkeypatch):
    from nassav.page_fetching.coordination import session_refresh_coordinator

    store = FakeSessionRefreshStore()
    monkeypatch.setattr(session_refresh_coordinator, "store", store)
    return store
