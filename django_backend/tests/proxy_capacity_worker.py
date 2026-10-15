"""Spawn-safe worker for the isolated proxy capacity acceptance test."""

import os

import redis
from nassav.page_fetching.proxy_capacity import RedisProxyCapacity


def request_slot(socket_path, endpoint, release, acquired, ready=None):
    client = redis.Redis(unix_socket_path=socket_path, socket_timeout=2)
    try:
        if ready is not None:
            ready.wait(timeout=10)
        with RedisProxyCapacity(client, endpoint, 2).slot(30000, check=lambda: None):
            acquired.put(os.getpid())
            # The parent owns the observation window and always releases/joins
            # children in finally. A child watchdog must not release the very
            # slots whose continued ownership the parent is checking.
            release.wait()
    finally:
        client.close()
