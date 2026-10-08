"""Task-local source/metadata gateway; parsed JSON and private assets cross its seam."""

from dataclasses import asdict
from pathlib import Path

from PIL import Image

from nassav.resource_contracts import ResourceSaveInput, SourceRelations
from nassav.resource_data import AVDownloadInfo
from nassav.provider_facts import SourceFactsLookup, SCRAPER_POLICY, configured_policy
from nassav.resource_cache import CacheKey, CachePublicationLost
from nassav.source.jable_actor_mapping import JableModelCandidate


def valid_image(path: Path) -> bool:
    try:
        with Image.open(path) as image:
            image.verify()
        return True
    except (OSError, ValueError):
        return False


def resource_input(avid: str, prepared: dict) -> ResourceSaveInput:
    relations = prepared.get("relations", {})
    return ResourceSaveInput(
        avid,
        AVDownloadInfo(**prepared["info"]),
        prepared["source_name"],
        prepared.get("metadata"),
        SourceRelations(
            tuple(relations.get("actor_names", [])),
            tuple(
                JableModelCandidate(**item)
                for item in relations.get("actor_candidates", [])
            ),
        ),
    )


class ScrapePreparation:
    def __init__(self, sources, metadata, control, *, facts_cache=None):
        self.sources, self.metadata, self.control = sources, metadata, control
        self.facts_cache = facts_cache

    def source(
        self, avid: str, source: str, *, force=False
    ) -> tuple[dict, bytes | None]:
        with self.control.phase(180):
            if self.facts_cache is not None:
                return self._cached_source(avid, source, force=force)
            info, adapter, html, errors = (
                self.sources.get_info_from_any_source(avid)
                if source == "any"
                else self.sources.get_info_from_source(avid, source)
            )
            self.control.check()
            if info is None or adapter is None or not html:
                raise ValueError(
                    f"来源获取失败: { {key: str(value) for key, value in errors.items()} }"
                )
            prepared = {
                "info": asdict(info),
                "source_name": adapter.get_source_name(),
                "cover_url": adapter.get_cover_url(html),
                "relations": asdict(adapter.parse_relations(html)),
            }
            return prepared, html.encode("utf-8")

    def _cached_source(self, avid, source, *, force=False):
        adapters = (
            self.sources.get_sorted_sources()
            if source == "any"
            else [(source, self.sources.get_source(source))]
        )
        errors = {}
        for name, adapter in adapters:
            self.control.check()
            if adapter is None:
                continue
            try:
                self.sources.refresh_source_cookie(adapter.get_source_name())
                data, playback, html, _ = SourceFactsLookup(
                    self.facts_cache, adapter
                ).resolve(avid, force=force, require_playback=True)
                self.control.check()
                return {
                    "info": {**data["source_info"], "m3u8": playback["m3u8"]},
                    "source_name": adapter.get_source_name(),
                    "cover_url": data["cover_url"],
                    "relations": data["relations"],
                }, html.encode("utf-8") if html is not None else None
            except CachePublicationLost:
                raise
            except Exception as error:
                self.control.check()
                errors[name] = str(error)
        raise ValueError(f"来源获取失败: {errors}")

    def scrape(self, avid: str, *, force=False) -> dict:
        with self.control.phase(60):
            if self.facts_cache is not None:
                return self._cached_scrape(avid, force=force)
            data, by = self.metadata.scrape_with_source(avid)
            self.control.check()
            return {"metadata": data, "scraped_by": by}

    def _cached_scrape(self, avid, *, force=False):
        assert self.facts_cache is not None
        for name, scraper in self.metadata.get_scrapers():
            self.control.check()
            key = CacheKey.create(avid, "scraper", name, scope=scraper.domain)

            def fetch():
                data = scraper.scrape(avid)
                self.control.check()
                if not data or not data.get("title"):
                    return {}
                if str(data.get("avid", "")).upper() != avid.upper():
                    raise ValueError("Scraper resource identity is invalid")
                return {"metadata": data, "scraped_by": name}

            result = self.facts_cache.resolve(
                key,
                configured_policy(SCRAPER_POLICY),
                fetch,
                force=force,
                check=self.control.check,
                fence=self.control.publish,
            )
            if result.payload:
                return result.payload
        return {"metadata": None, "scraped_by": None}

    def cover(self, prepared: dict, path: Path) -> bool:
        data = prepared.get("metadata") or {}
        with self.control.phase(45):
            if data.get("cover_url") and self.metadata.download_cover(
                data["cover_url"], str(path), prepared.get("scraped_by")
            ):
                self.control.check()
                if valid_image(path):
                    return True
            self.control.check()
            source = self.sources.get_source(prepared["source_name"])
            if source is not None and prepared.get("cover_url"):
                return source.download_file(prepared["cover_url"], str(path))
        return False

    @staticmethod
    def avatars(prepared: dict) -> list[tuple[str, str]]:
        data = prepared.get("metadata") or {}
        result = dict(data.get("actor_avatars") or {})
        for actor in data.get("actors", []):
            if (
                isinstance(actor, dict)
                and actor.get("name")
                and actor.get("avatar_url")
            ):
                result[actor["name"]] = actor["avatar_url"]
        return list(result.items())

    def avatar(self, url: str, path: Path) -> bool:
        with self.control.phase(45):
            scrapers = self.metadata.get_scrapers()
            return bool(scrapers and scrapers[0][1].download_avatar(url, str(path)))
