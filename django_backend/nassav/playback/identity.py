"""Conservative VOD compatibility: tracks/time axis, encryption and init bytes.

Signed URIs may change; compatibility is not proof of byte-identical video.
No upstream URL, key or media bytes are persisted by this module.
"""

import asyncio
import hashlib
from .manifest import parse_manifest
from .body import read_limited
from .policy import PlaybackGatewayError


def byte_digest(body):
    return hashlib.sha256(body).hexdigest()


def manifest_digest(parsed):
    return byte_digest(
        parsed.render([f"asset:{r.kind}:{i}" for i, r in enumerate(parsed.references)])
    )


class PlaybackIdentityValidator:
    def __init__(self, transport, policy, capacity):
        self.transport, self.policy, self.capacity = transport, policy, capacity

    def validate(self, session_id, descriptor, baseline, control):
        # Sync worker owns orchestration; all network stays outside publication fences.
        asyncio.run(self.verify(session_id, descriptor, baseline, control.check))

    async def verify(self, session_id, descriptor, baseline, check):
        if not baseline or "root" not in baseline or len(baseline) > 128:
            raise PlaybackGatewayError("media_identity_changed", 422)
        targets = {"root": (descriptor.manifest_url, "manifest")}
        headers = {"Referer": descriptor.referer, "User-Agent": descriptor.user_agent}
        async with asyncio.timeout(120):
            for path in sorted(baseline, key=lambda p: (p.count("/"), p)):
                await asyncio.to_thread(check)
                target = targets.get(path)
                expected = baseline[path]
                if not target or target[1] != expected["kind"]:
                    raise PlaybackGatewayError("media_identity_changed", 422)
                url, kind = target
                async with self.capacity.slot(session_id) as lease:
                    async with self.transport.open(url, headers) as (response, final):
                        lease()
                        if response.status_code != 200 or response.headers.get(
                            "content-encoding", "identity"
                        ) not in {"identity", ""}:
                            raise PlaybackGatewayError("refresh_source_unavailable")
                        body = await read_limited(
                            response,
                            {"manifest": 1024 * 1024, "key": 16, "init": 256 * 1024}[
                                kind
                            ],
                        )
                if kind == "manifest":
                    parsed = parse_manifest(body, final, self.policy)
                    digest = manifest_digest(parsed)
                    for i, ref in enumerate(parsed.references):
                        if ref.kind in {"manifest", "key", "init"}:
                            targets[f"{path}/{i}"] = (ref.url, ref.kind)
                else:
                    digest = byte_digest(body)
                if digest != expected["digest"]:
                    raise PlaybackGatewayError("media_identity_changed", 422)
                await asyncio.to_thread(check)
