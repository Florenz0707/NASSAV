"""Preparation workflow consumes explicit resolver; only owned facts may publish."""

from datetime import timedelta
from dataclasses import asdict
from nassav.constants import HEADERS
from nassav.resource_cache import CacheKey, CachePolicy
from nassav.source.CookieRepository import proxy_route_profile
from .contracts import PlaybackResolver, PlaybackDescriptor, PlaybackStopped


class SourcePlaybackResolver(PlaybackResolver):
    def __init__(self, scope, cache, ttl_seconds):
        self.scope, self.cache, self.ttl_seconds = scope, cache, ttl_seconds

    def resolve(self, avid, source_name, control):
        with self.scope(source_name, control) as source:
            profile = proxy_route_profile(source.proxy)
            version = source.browser_session_version()
            key = CacheKey.create(
                avid,
                "source",
                source_name,
                scope=f"{source.domain}:{profile}:{version}",
                variant="online-playback-v2",
            )
            policy = CachePolicy(
                "online-playback-v2",
                frozenset(PlaybackDescriptor.__dataclass_fields__),
                timedelta(seconds=self.ttl_seconds),
            )

            def fetch():
                html = source.get_html(avid)
                control.check()
                info = source.parse_html(html) if html else None
                if (
                    not info
                    or not info.m3u8
                    or (info.avid and info.avid.upper() != avid.upper())
                ):
                    raise ValueError("Source playback unavailable")
                return asdict(
                    PlaybackDescriptor(
                        info.m3u8,
                        source.last_final_url or source.get_detail_url(avid),
                        HEADERS["User-Agent"],
                        source_name,
                        profile,
                        version,
                    ).validate()
                )

            facts = self.cache.resolve(
                key,
                policy,
                fetch,
                playback=True,
                check=control.check,
                fence=control.publish,
            )
            return PlaybackDescriptor(**facts.payload).validate()


def execute(session_id, resolver, records):
    from nassav.task_network import TaskNetworkControl

    token = records.claim(session_id)
    if token is None:
        return
    try:
        avid, source_name, remaining = records.preparation_input(token)
        control = TaskNetworkControl(
            lambda: records.check(token),
            publish_fence=lambda op: records.publish(token, op),
        )
        with control.phase(max(0, remaining)):
            descriptor = resolver.resolve(avid, source_name, control)
            control.check()
            records.ready(token, descriptor)
    except PlaybackStopped:
        return
    except Exception:
        records.fail(token)
