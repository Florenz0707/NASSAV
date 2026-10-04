"""R2: uv run pytest tests/test_session_lifecycle_contracts.py -v."""

import shutil
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor

import pytest
import redis

from nassav.page_fetching import PageResult
from nassav.page_fetching.coordination import (
    RedisRefreshStore,
    SessionRefreshCoordinator,
    refresh_key,
)
from nassav.source.CookieRepository import CookieRepository, SourceCookieRecord
from nassav.source.Jable import Jable
from nassav.source.session_lifecycle import SourceSessionLifecycle


class MemoryCookieRepository(CookieRepository):
    def __init__(self, record=None):
        self.record = record

    def get_cookie_record(self, source_name):
        return self.record

    def set_cookie(self, source_name, cookie, *, user_agent=None):
        self.record = SourceCookieRecord(source_name, cookie, "manual", user_agent)
        return self.record

    def set_session_if_version(
        self,
        source_name,
        *,
        expected_updated_at,
        cookie,
        user_agent,
        expires_at,
        egress_profile,
        write_guard=None,
    ):
        actual = self.record.updated_at if self.record else None
        if actual != expected_updated_at or (write_guard and not write_guard()):
            return None
        self.record = SourceCookieRecord(
            source_name, cookie, "saved", user_agent, expires_at, egress_profile
        )
        return self.record

    def set_automatic_cookie_if_version(
        self, source_name, *, expected_updated_at, cookie, write_guard=None
    ):
        actual = self.record.updated_at if self.record else None
        if actual != expected_updated_at or (write_guard and not write_guard()):
            return None
        return self.set_cookie(source_name, cookie)

    def invalidate_cookie(self, source_name):
        pass


def test_source_session_dependency_can_be_replaced_without_database():
    record = SourceCookieRecord("jable", "session=old", "v1", "UA")
    repository = MemoryCookieRepository(record)
    source = Jable(cookie_repository=repository)
    assert source.load_cookie_from_db()
    assert source.cookie == record.cookie
    assert source.browser_session_version() == "v1"
    repository.set_cookie("jable", "manual=new")
    assert source.load_cookie_from_db()
    assert source.cookie == "manual=new" and source._session_snapshot.user_agent is None


def test_session_lifecycle_rejects_lost_owner_without_database(fake_session_store):
    repository = MemoryCookieRepository()
    source = Jable(
        proxy="http://proxy.test:8080",
        cookie_repository=repository,
        refresh_coordinator=SessionRefreshCoordinator(fake_session_store),
    )
    source.fetch_page = lambda *args, **kwargs: PageResult(
        html="business page", target_status=200, final_url="https://jable.tv/"
    )
    result = PageResult(
        html="business page",
        provider="byparr",
        user_agent="UA",
        cookies=({"name": "session", "value": "new", "domain": "jable.tv"},),
    )
    lifecycle = SourceSessionLifecycle(
        source, repository, SessionRefreshCoordinator(fake_session_store)
    )
    assert not lifecycle.accept_browser_session(
        "https://jable.tv/", result, lambda html: True, None, write_guard=lambda: False
    )
    assert repository.record is None


@pytest.fixture
def isolated_redis(tmp_path):
    executable = shutil.which("redis-server")
    if executable is None:
        pytest.fail("R2 Redis acceptance requires redis-server")
    socket_path = tmp_path / "redis.sock"
    process = subprocess.Popen(
        [
            executable,
            "--port",
            "0",
            "--unixsocket",
            str(socket_path),
            "--unixsocketperm",
            "700",
            "--save",
            "",
            "--appendonly",
            "no",
            "--dir",
            str(tmp_path),
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
    )
    client = redis.Redis(unix_socket_path=str(socket_path), socket_timeout=1)
    try:
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline:
            try:
                if client.ping():
                    break
            except redis.ConnectionError:
                if process.poll() is not None:
                    pytest.fail("Isolated Redis exited before readiness")
                time.sleep(0.01)
        else:
            pytest.fail("Isolated Redis readiness timeout")
        yield client
    finally:
        client.close()
        process.terminate()
        try:
            process.wait(timeout=3)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=3)
        if process.stderr:
            process.stderr.close()


def test_real_redis_contract_fences_racing_owners_and_old_leases(isolated_redis):
    store = RedisRefreshStore(isolated_redis)
    key = refresh_key("jable", "https://jable.tv/", "route")
    with ThreadPoolExecutor(max_workers=4) as pool:
        outcomes = list(
            pool.map(
                lambda owner: (owner, store.acquire(key, owner, 90)),
                ["a", "b", "c", "d"],
            )
        )
    winners = [owner for owner, (acquired, _) in outcomes if acquired]
    assert len(winners) == 1
    owner = winners[0]
    assert isolated_redis.ttl(key) > 0
    assert not store.renew(key, "wrong", 90)
    assert not store.release(key, "wrong", "reused")
    assert store.owner(key) == owner
    isolated_redis.delete(key)  # expired lease, followed by a new owner
    assert store.acquire(key, "new", 90) == (True, None)
    assert not store.renew(key, owner, 90)
    assert not store.release(key, owner, "reused")
    assert store.outcome(key) is None
    assert store.release(key, "new", "reused")
    assert store.outcome(key) == "new:reused"
    assert 0 < isolated_redis.ttl(key + ":result") <= 15
    other = refresh_key("jable", "https://other.test/", "route")
    assert store.acquire(other, "other", 90) == (True, None)
    store.mark_unusable(key)
    assert store.recently_unusable(key) and not store.recently_unusable(other)
    store.clear_unusable(key)
    assert not store.recently_unusable(key)
