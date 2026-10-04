"""Capabilities consumed by resource workflow and asset adapters."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from nassav.scraper import AVDownloadInfo
    from nassav.source.SourceBase import SourceBase
    from nassav.scraper.ScraperBase import ScraperBase


class SourceLookup(ABC):
    @abstractmethod
    def get_info_from_any_source(
        self, avid: str
    ) -> tuple[
        AVDownloadInfo | None,
        "SourceBase | None",
        str | None,
        dict[str, int | str | None],
    ]:
        raise NotImplementedError

    @abstractmethod
    def get_info_from_source(
        self, avid: str, source_str: str
    ) -> tuple[
        AVDownloadInfo | None,
        "SourceBase | None",
        str | None,
        dict[str, int | str | None],
    ]:
        raise NotImplementedError


class MetadataProvider(ABC):
    @abstractmethod
    def scrape_with_source(self, avid: str) -> tuple[dict | None, str | None]:
        raise NotImplementedError

    @abstractmethod
    def download_cover(
        self, url: str, save_path: str, scraper_name: str | None = None
    ) -> bool:
        raise NotImplementedError

    @abstractmethod
    def get_scrapers(self) -> list[tuple[str, "ScraperBase"]]:
        raise NotImplementedError


class ResourceWorkflow(ABC):
    @abstractmethod
    def add_resource(self, avid: str, source: str = "any", **options) -> dict:
        raise NotImplementedError

    @abstractmethod
    def refresh_resource(self, avid: str, **options) -> dict:
        raise NotImplementedError

    @abstractmethod
    def load_cached_metadata(self, avid: str) -> AVDownloadInfo | None:
        raise NotImplementedError
