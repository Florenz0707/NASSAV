"""Provider-neutral cache identity and structured source facts acquisition."""

from datetime import timedelta
from urllib.parse import urlsplit, urlunsplit
from dataclasses import asdict, replace

from nassav.resource_cache import CacheKey, CachePolicy

SOURCE_POLICY = CachePolicy(
    "source-facts-v1",
    frozenset({"source_info", "cover_url", "relations", "detail"}),
    timedelta(days=7),
)
SCRAPER_POLICY = CachePolicy(
    "scraper-facts-v1", frozenset({"metadata", "scraped_by"}), timedelta(days=30)
)
PLAYBACK_POLICY = CachePolicy("playback-v1", frozenset({"m3u8"}), timedelta(minutes=5))


def source_credential_context(source):
    if getattr(source, "requires_bound_page", False) is True:
        return source.credential_context
    return None


def configured_policy(policy):
    from django.conf import settings

    key = {
        SOURCE_POLICY.parser_version: "SourceTTLSeconds",
        SCRAPER_POLICY.parser_version: "ScraperTTLSeconds",
        PLAYBACK_POLICY.parser_version: "PlaybackTTLSeconds",
    }[policy.parser_version]
    seconds = settings.RESOURCE_CACHE_POLICY[key]
    return replace(policy, ttl=timedelta(seconds=seconds))


def source_key(source, avid, detail_url=""):
    context = source_credential_context(source)
    return _source_key(
        source, avid, detail_url, context.scope_key if context is not None else "public"
    )


def _source_key(source, avid, detail_url, scope):
    url = detail_url or source.get_detail_url(avid)
    parts = urlsplit(url)
    normalized = urlunsplit(
        (
            parts.scheme.lower(),
            parts.netloc.lower(),
            parts.path.rstrip("/"),
            parts.query,
            "",
        )
    )
    return CacheKey.create(
        avid,
        "source",
        source.get_source_name(),
        scope=f"{source.domain}:{scope}",
        variant=normalized,
    )


def playback_key(source, avid, detail_url=""):
    from nassav.source.CookieRepository import proxy_route_profile

    key = source_key(source, avid, detail_url)
    context = source_credential_context(source)
    scope = f"{source.domain}:{proxy_route_profile(source.proxy)}:{source.browser_session_version()}"
    if context is not None:
        scope = f"{scope}:{context.scope_key}"
    return CacheKey(
        key.avid,
        key.provider_kind,
        key.provider_name,
        CacheKey.create(
            avid,
            "source",
            key.provider_name,
            scope=scope,
        ).scope_key,
        key.variant_key,
    )


class SourceFactsLookup:
    def __init__(self, cache, source):
        self.cache, self.source = cache, source

    def read_facts(self, candidates):
        result = {}
        context = source_credential_context(self.source)
        for offset in range(0, len(candidates), 200):
            scope = context.scope_key if context is not None else "public"
            keys = {
                _source_key(self.source, avid, url, scope): avid
                for avid, url in candidates[offset : offset + 200]
            }
            for key, value in self.cache.read_many(
                list(keys), configured_policy(SOURCE_POLICY)
            ).items():
                result[keys[key]] = value
            if context is not None:
                context.check()
        return result

    def read_details(self, candidates):
        context = source_credential_context(self.source)
        scope = context.scope_key if context is not None else "public"
        keys = {
            _source_key(self.source, avid, url, scope): avid
            for avid, url in candidates[:200]
        }
        result = {
            keys[key]: value["detail"]
            for key, value in self.cache.read_many(
                list(keys), configured_policy(SOURCE_POLICY)
            ).items()
            if value.get("detail")
        }
        if context is not None:
            context.check()
        return result

    def resolve(self, avid, detail_url="", *, force=False, require_playback=False):
        source = self.source
        key = source_key(source, avid, detail_url)
        pkey = playback_key(source, avid, detail_url)
        control = source.task_control
        check = control.check if control is not None else lambda: None
        fence = control.publish if control is not None else None
        context = source_credential_context(source)
        if context is not None:
            execution_check, execution_fence = check, fence

            def scoped_check():
                execution_check()
                context.check()

            def scoped_fence(publish):
                return context.publish(
                    lambda: (
                        execution_fence(publish)
                        if execution_fence is not None
                        else publish()
                    )
                )

            check, fence = scoped_check, scoped_fence
        playback = self.cache.read_many(
            [pkey], configured_policy(PLAYBACK_POLICY), playback=True
        ).get(pkey)
        captured = {}

        def fetch():
            metadata, link, html = source.fetch_provider_facts(avid, detail_url)
            captured["html"] = html
            if link:
                captured["playback"] = self.cache.resolve(
                    playback_key(source, avid, detail_url),
                    configured_policy(PLAYBACK_POLICY),
                    lambda: {"m3u8": link},
                    force=True,
                    playback=True,
                    check=check,
                    fence=fence,
                ).payload
            return metadata

        result = self.cache.resolve(
            key,
            configured_policy(SOURCE_POLICY),
            fetch,
            force=force or (require_playback and not playback),
            check=check,
            fence=fence,
        )
        return (
            result.payload,
            captured.get("playback", playback),
            captured.get("html"),
            result.hit,
        )


def parse_source_facts(source, avid, html, detail=None):
    info = source.parse_html(html)
    if (
        info is None
        or not info.m3u8
        or (info.avid and info.avid.upper() != avid.upper())
    ):
        raise ValueError("Source identity or playback information is invalid")
    info.avid = avid.upper()
    data = asdict(info)
    link = data.pop("m3u8")
    return {
        "source_info": data,
        "cover_url": source.get_cover_url(html),
        "relations": asdict(source.parse_relations(html)),
        "detail": detail or {},
    }, link
