"""Preparation workflow consumes explicit resolver; only owned facts may publish."""

from datetime import timedelta
import logging
import time
from dataclasses import asdict
from nassav.constants import HEADERS
from nassav.resource_cache import CacheKey, CachePolicy
from nassav.source.CookieRepository import proxy_route_profile
from .contracts import PlaybackResolver, PlaybackDescriptor, PlaybackStopped


class SourcePlaybackResolver(PlaybackResolver):
    def __init__(self, scope, cache, ttl_seconds):
        self.scope, self.cache, self.ttl_seconds = scope, cache, ttl_seconds

    def resolve(self, avid, source_name, control, *, force=False):
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
                force=force,
                check=control.check,
                fence=control.publish,
            )
            return PlaybackDescriptor(**facts.payload).validate()


logger = logging.getLogger(__name__)


def execute(session_id, resolver, records, validator=None):
    from nassav.task_network import TaskNetworkControl

    token = records.claim(session_id)
    if token is None:
        return
    started = time.monotonic()
    try:
        avid, source_name, remaining = records.preparation_input(token)
        control = TaskNetworkControl(
            lambda: records.check(token),
            publish_fence=lambda op: records.publish(token, op),
        )
        with control.phase(max(0, remaining)):
            refreshing, baseline = records.refresh_context(token)
            descriptor = resolver.resolve(avid, source_name, control, force=refreshing)
            if refreshing:
                if validator is None:
                    raise ValueError("Refresh validator unavailable")
                validator.validate(session_id, descriptor, baseline, control)
            control.check()
            records.ready(token, descriptor)
            logger.info(
                "Playback prepare session=%s generation=%s state=ready seconds=%.2f",
                session_id,
                token.generation,
                time.monotonic() - started,
            )
    except PlaybackStopped:
        logger.info(
            "Playback prepare session=%s generation=%s state=stopped",
            session_id,
            token.generation,
        )
        return
    except Exception as error:
        from .policy import PlaybackGatewayError

        code = (
            "media_identity_changed"
            if isinstance(error, PlaybackGatewayError)
            and error.code == "media_identity_changed"
            else "preparation_failed"
        )
        records.fail(token, code)
        logger.warning(
            "Playback prepare session=%s generation=%s state=failed code=%s seconds=%.2f",
            session_id,
            token.generation,
            code,
            time.monotonic() - started,
        )
