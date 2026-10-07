"""Spawn-safe worker for the isolated proxy capacity acceptance test."""

import os

import redis
from nassav.page_fetching.proxy_capacity import RedisProxyCapacity


def request_slot(socket_path, endpoint, release, acquired):
    client = redis.Redis(unix_socket_path=socket_path, socket_timeout=2)
    try:
        with RedisProxyCapacity(client, endpoint, 2).slot(2000, check=lambda: None):
            acquired.put(os.getpid())
            assert release.wait(5)
    finally:
        client.close()
