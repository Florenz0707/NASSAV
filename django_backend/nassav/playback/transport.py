"""One bounded HTTPX stream, fixed route and checked redirects per operation."""

from abc import ABC, abstractmethod
from contextlib import asynccontextmanager
from urllib.parse import urljoin
import httpx
from .policy import PlaybackGatewayError


class PlaybackTransport(ABC):
    @abstractmethod
    def open(self, url, headers, *, method="GET"): ...


class HttpxPlaybackTransport(PlaybackTransport):
    def __init__(
        self,
        policy,
        proxy=None,
        *,
        proxy_targets_trusted=False,
        client_factory=httpx.AsyncClient,
    ):
        self.policy, self.proxy, self.trusted, self.factory = (
            policy,
            proxy,
            proxy_targets_trusted,
            client_factory,
        )

    @asynccontextmanager
    async def open(self, url, headers, *, method="GET"):
        if self.proxy and not self.trusted:
            raise PlaybackGatewayError("proxy_target_policy_required", 503)
        async with self.factory(
            proxy=self.proxy,
            trust_env=False,
            follow_redirects=False,
            timeout=httpx.Timeout(15, connect=5),
            limits=httpx.Limits(max_connections=1),
        ) as client:
            response = None
            try:
                for hop in range(4):
                    host, ip = await self.policy.target(url)
                    requested = (
                        url if self.proxy else str(httpx.URL(url).copy_with(host=ip))
                    )
                    client.cookies.clear()
                    request = client.build_request(
                        method,
                        requested,
                        headers={
                            **headers,
                            "Host": host,
                            "Accept-Encoding": "identity",
                        },
                    )
                    if not self.proxy:
                        request.extensions["sni_hostname"] = host
                    response = await client.send(request, stream=True)
                    if response.status_code not in {301, 302, 303, 307, 308}:
                        break
                    destination = response.headers.get("location")
                    await response.aclose()
                    response = None
                    if not destination or hop == 3:
                        raise PlaybackGatewayError("redirect_rejected")
                    url = urljoin(url, destination)
                if response is None:
                    raise PlaybackGatewayError("upstream_unavailable")
                # The final URI is the manifest base, not the pinned-IP request URL.
                yield response, url
            except httpx.HTTPError as error:
                raise PlaybackGatewayError("upstream_unavailable") from error
            finally:
                if response is not None:
                    await response.aclose()
