"""Target authorization and DNS checks; no client-supplied forwarding URL."""

import asyncio
import ipaddress
import socket
from urllib.parse import urlsplit


class PlaybackGatewayError(RuntimeError):
    def __init__(self, code, status=502):
        super().__init__(code)
        self.code, self.status = code, status


async def resolve_public(host):
    results = await asyncio.get_running_loop().getaddrinfo(
        host, 443, type=socket.SOCK_STREAM
    )
    return list(dict.fromkeys(item[4][0] for item in results))


class TargetPolicy:
    def __init__(self, allowed_hosts, *, resolve=resolve_public):
        self.hosts = tuple(allowed_hosts)
        self.resolve = resolve
        for host in self.hosts:
            base = host[2:] if host.startswith("*.") else host
            if not base or "." not in base or any(c in base for c in "/:@%\\ *"):
                raise ValueError("Invalid playback host allowlist")

    def validate(self, url):
        try:
            p = urlsplit(url)
            host = (p.hostname or "").lower()
            allowed = any(
                host == h
                or (h.startswith("*.") and host.endswith(h[1:]) and host != h[2:])
                for h in self.hosts
            )
            if (
                p.scheme != "https"
                or not allowed
                or p.username
                or p.password
                or p.port not in (None, 443)
                or p.fragment
                or len(url) > 8192
                or "\\" in url
                or "%" in host
                or any(ord(c) <= 32 or ord(c) == 127 for c in url)
            ):
                raise ValueError
            try:
                ip = ipaddress.ip_address(host)
            except ValueError:
                ip = None
            if ip is not None and not ip.is_global:
                raise ValueError
            return host
        except ValueError as error:
            raise PlaybackGatewayError("target_rejected", 403) from error

    async def target(self, url):
        host = self.validate(url)
        try:
            addresses = await asyncio.wait_for(self.resolve(host), timeout=5)
            if not addresses or any(
                not ipaddress.ip_address(ip).is_global for ip in addresses
            ):
                raise ValueError
        except (ValueError, OSError, TimeoutError) as error:
            raise PlaybackGatewayError("target_dns_rejected", 403) from error
        return host, addresses[0]
