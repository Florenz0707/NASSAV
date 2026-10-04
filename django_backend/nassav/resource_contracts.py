"""Capabilities consumed by resource workflow and asset adapters."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Optional
from pathlib import Path
from dataclasses import dataclass

if TYPE_CHECKING:
    from nassav.models import AVResource
    from nassav.source.jable_actor_mapping import JableModelCandidate
    from nassav.resource_data import AVDownloadInfo
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


@dataclass(frozen=True)
class SourceRelations:
    actor_names: tuple[str, ...] = ()
    actor_candidates: tuple[JableModelCandidate, ...] = ()


class ResourceReader(ABC):
    @abstractmethod
    def get(self, avid: str) -> AVResource | None:
        raise NotImplementedError


@dataclass(frozen=True)
class AssetResult:
    path: Path
    saved: bool


class ResourceAssets(ABC):
    @abstractmethod
    def save_page(self, avid: str, html: str) -> AssetResult:
        raise NotImplementedError

    @abstractmethod
    def save_cover(
        self,
        avid: str,
        scraped_data: Optional[dict],
        scraped_by: Optional[str],
        source_inst: SourceBase | None,
        html: str | None,
    ) -> bool:
        raise NotImplementedError

    @abstractmethod
    def save_avatars(self, scraped_data: dict) -> None:
        raise NotImplementedError


class TranslationSubmitter(ABC):
    @abstractmethod
    def submit(self, avid: str) -> Optional[str]:
        raise NotImplementedError


class ResourceEvents(ABC):
    @abstractmethod
    def publish(self, event: str, sender: type, avid: str, result: dict) -> None:
        raise NotImplementedError


@dataclass(frozen=True)
class ResourceSaveInput:
    avid: str
    info: AVDownloadInfo
    source_name: str
    scraped_data: dict | None = None
    relations: SourceRelations = SourceRelations()


class ResourcePersistence(ABC):
    """Write a resource and its metadata relations as one application operation."""

    @abstractmethod
    def save(self, data: ResourceSaveInput) -> AVResource:
        """Save parsed data without mutating its download info or scraper payload."""
        raise NotImplementedError
