"""Consumers use the same proxy capacity interface for every provider."""

import threading
from concurrent.futures import ThreadPoolExecutor

import pytest
import redis
from nassav.page_fetching.contracts import BrowserPageClient, PageResult
from nassav.page_fetching.proxy_capacity import RedisProxyCapacity
from nassav.page_fetching.proxy_client import ProxyPageClient
from nassav.page_fetching.proxy_server import OrderedProxyServer, ProxyCapacityError
from test_session_lifecycle_contracts import isolated_redis as _isolated_redis

proxy_redis = _isolated_redis


def test_ordered_results_overlap_and_early_exit_stops_unscheduled_work():
    second_started = threading.Event()
    calls = []

    def operation(value, check):
        calls.append(value)
        if value == 1:
            assert second_started.wait(2)
        else:
            second_started.set()
        check()
        return value

    with OrderedProxyServer(2).ordered(operation, range(1, 7)) as results:
        assert next(results) == 1
    assert sorted(calls) == [1, 2]


def test_operation_timeout_is_not_swallowed_as_future_wait():
    def operation(value, check):
        raise TimeoutError("source timeout")

    with pytest.raises(TimeoutError, match="source timeout"):
        with OrderedProxyServer(2).ordered(operation, [1]) as results:
            list(results)


def test_cancelled_results_are_not_delivered():
    cancelled = threading.Event()

    def check():
        if cancelled.is_set():
            raise ValueError("cancelled")

    def operation(value, checkpoint):
        cancelled.set()
        return value

    with pytest.raises(ValueError, match="cancelled"):
        with OrderedProxyServer(2).ordered(operation, [1, 2], check=check) as results:
            list(results)


@pytest.mark.parametrize("provider", ["provider-a", "provider-b"])
def test_capacity_decorator_preserves_protocol_and_closes_transport(provider):
    class Client(BrowserPageClient):
        closed = False

        def fetch(self, url, *, timeout_ms):
            return PageResult(html="business", final_url=url, provider=provider)

        def close(self):
            self.closed = True

    raw = Client()
    client = ProxyPageClient(raw, OrderedProxyServer(2))
    assert client.fetch("https://example.test/", timeout_ms=1000).provider == provider
    client.close()
    assert raw.closed


def test_multiple_servers_share_capacity_and_release_their_own_slots(proxy_redis):
    capacities = [
        RedisProxyCapacity(proxy_redis, "http://proxy:8191", 2) for _ in range(3)
    ]
    release, two_started = threading.Event(), threading.Event()
    mutex = threading.Lock()
    active, maximum, started = 0, 0, 0

    def request(index):
        nonlocal active, maximum, started
        with capacities[index].slot(2000, check=lambda: None):
            with mutex:
                active += 1
                started += 1
                maximum = max(maximum, active)
                if started == 2:
                    two_started.set()
            assert release.wait(3)
            with mutex:
                active -= 1

    with ThreadPoolExecutor(3) as pool:
        futures = [pool.submit(request, i) for i in range(3)]
        try:
            assert two_started.wait(2)
            assert proxy_redis.zcard(capacities[0].key) == 2
        finally:
            release.set()
        for future in futures:
            future.result(timeout=3)
    assert maximum == 2 and started == 3
    assert proxy_redis.zcard(capacities[0].key) == 0


def test_expired_holder_does_not_release_replacement(proxy_redis):
    capacity = RedisProxyCapacity(proxy_redis, "http://proxy:8191", 1)
    with pytest.raises(ProxyCapacityError, match="lease lost"):
        with capacity.slot(1000, check=lambda: None):
            proxy_redis.delete(capacity.key)
            proxy_redis.zadd(capacity.key, {"replacement": 99999999999})
    assert proxy_redis.zcard(capacity.key) == 1


def test_capacity_unavailable_fails_closed():
    class Offline:
        def eval(self, *args):
            raise redis.ConnectionError("offline")

    with pytest.raises(ProxyCapacityError, match="unavailable"):
        with RedisProxyCapacity(Offline(), "http://proxy:8191", 2).slot(
            1000, check=lambda: None
        ):
            pytest.fail("No capacity bypass")


def test_capacity_wait_observes_cancellation(proxy_redis):
    capacity = RedisProxyCapacity(proxy_redis, "http://proxy:8191", 1)
    proxy_redis.zadd(capacity.key, {"other": 99999999999})
    attempts = 0

    def check():
        nonlocal attempts
        attempts += 1
        if attempts > 1:
            raise ValueError("cancelled")

    with pytest.raises(ValueError, match="cancelled"):
        with capacity.slot(1000, check=check):
            pytest.fail("Busy capacity was bypassed")
    assert proxy_redis.zcard(capacity.key) == 1


@pytest.mark.parametrize("concurrency", [1, 2])
def test_iterator_cannot_schedule_operations_after_scope_exit(concurrency):
    calls = []
    with OrderedProxyServer(concurrency).ordered(
        lambda value, check: calls.append(value), [1, 2]
    ) as results:
        pass
    with pytest.raises(RuntimeError, match="stopped"):
        next(results)
    assert calls == []


def test_separate_worker_processes_share_proxy_capacity(proxy_redis):
    import multiprocessing
    import queue
    from proxy_capacity_worker import request_slot

    context = multiprocessing.get_context("spawn")
    release, acquired = context.Event(), context.Queue()
    ready = context.Barrier(4)
    endpoint = "http://shared-proxy:8191"
    key = RedisProxyCapacity(proxy_redis, endpoint, 2).key

    socket_path = proxy_redis.connection_pool.connection_kwargs["path"]
    processes = [
        context.Process(
            target=request_slot, args=(socket_path, endpoint, release, acquired, ready)
        )
        for _ in range(3)
    ]
    for process in processes:
        process.start()
    try:
        ready.wait(timeout=10)
        first = [acquired.get(timeout=2), acquired.get(timeout=2)]
        assert proxy_redis.zcard(key) == 2
        with pytest.raises(queue.Empty):
            acquired.get(timeout=0.1)
        release.set()
        assert acquired.get(timeout=2) not in first
        for process in processes:
            process.join(timeout=3)
            assert process.exitcode == 0
        assert proxy_redis.zcard(key) == 0
    finally:
        release.set()
        for process in processes:
            if process.is_alive():
                process.terminate()
            process.join(timeout=3)
        acquired.close()
