"""Default adapter factories; business managers also accept injected factories.

Concrete adapters are imported inside each builder to avoid package initialization
cycles. Builders construct dependencies without performing network requests.
"""

from collections.abc import Callable
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from nassav.page_fetching.factory import BrowserFetchConfig
    from nassav.scraper.ScraperBase import ScraperBase
    from nassav.source.SourceBase import SourceBase
    from nassav.translator.TranslatorBase import TranslatorBase


def source_factories(
    proxy: str | None,
    browser_config: "BrowserFetchConfig",
    save_cookie: Callable[[str, str], bool],
) -> dict[str, Callable[[], "SourceBase"]]:
    from nassav.page_fetching import create_page_fetch_service
    from nassav.source.Jable import Jable
    from nassav.source.Memo import Memo
    from nassav.source.MissAV import MissAV

    return {
        "missav": lambda: MissAV(
            proxy,
            page_fetcher=create_page_fetch_service(browser_config, proxy_url=proxy),
            cookie_saver=lambda cookie: save_cookie("MissAV", cookie),
        ),
        "jable": lambda: Jable(
            proxy,
            page_fetcher=create_page_fetch_service(browser_config, proxy_url=proxy),
        ),
        "memo": lambda: Memo(proxy),
    }


def scraper_factories(proxy: str | None) -> dict[str, Callable[[], "ScraperBase"]]:
    from nassav.scraper.Javbus import Busdmm, Dmmsee, Javbus

    return {
        "javbus": lambda: Javbus(proxy),
        "busdmm": lambda: Busdmm(proxy),
        "dmmsee": lambda: Dmmsee(proxy),
    }


def translator_factories() -> dict[str, Callable[[int, str], "TranslatorBase"]]:
    from nassav.translator.OllamaTranslator import OllamaTranslator

    return {
        "ollama": lambda timeout, name: OllamaTranslator(
            timeout=timeout, config_name=name
        )
    }


def external_search_adapters():
    from nassav.external_search import (
        JableExternalSourceAdapter,
        MissAVExternalSourceAdapter,
        PlaceholderExternalSourceAdapter,
    )

    return {
        "jable": JableExternalSourceAdapter(),
        "missav": MissAVExternalSourceAdapter(),
        "memo": PlaceholderExternalSourceAdapter("memo"),
    }


def cover_policy_for(source_name: str):
    from nassav.recommendation.cover_cache import JableCoverPolicy, MissAVCoverPolicy

    policies = {"jable": JableCoverPolicy, "missav": MissAVCoverPolicy}
    factory = policies.get(source_name.strip().lower(), JableCoverPolicy)
    return factory()


def build_video_download_service():
    from django.conf import settings

    from nassav.download_information import ResourceDownloadInfoResolver
    from nassav.m3u8downloader import N_m3u8DL_RE
    from nassav.resource_service import resource_service
    from nassav.services import VideoDownloadService
    from nassav.source.SourceManager import source_manager

    def domain_lookup(name: str) -> str:
        source_name = name.lower()
        return settings.SOURCE_CONFIG.get(source_name, {}).get(
            "domain", source_name + ".com"
        )

    return VideoDownloadService(
        ResourceDownloadInfoResolver(
            resource_service, source_manager.get_resource_dir, domain_lookup
        ),
        N_m3u8DL_RE(proxy=settings.DOWNLOAD_PROXY_URL or None),
    )


def build_translation_workflow():
    from nassav.translation_adapters import (
        DjangoTranslationRepository,
        ManagerTextTranslator,
    )
    from nassav.translation_workflow import TitleTranslationUseCase
    from nassav.translator import translator_manager

    return TitleTranslationUseCase(
        DjangoTranslationRepository(), ManagerTextTranslator(translator_manager)
    )


def build_recommendation_manager():
    from django.conf import settings

    from nassav.recommendation.data_access import (
        DjangoCandidateInventory,
        DjangoRecommendationContext,
    )
    from nassav.recommendation.jable_page_lookup import JablePageLookupRecommender
    from nassav.recommendation.workflow import RecommenderManager
    from nassav.source import Jable

    def jable_factory(strategy):
        return JablePageLookupRecommender(
            jable=Jable(proxy=settings.PROXY_URL if settings.PROXY_ENABLED else None),
            candidate_inventory=DjangoCandidateInventory(),
            seed_provider=strategy.seed_provider_builder(),
            factors=[builder() for builder in strategy.factor_builders],
            **strategy.recommender_kwargs,
        )

    return RecommenderManager(
        DjangoRecommendationContext(), {"jable_page_lookup": jable_factory}
    )


def build_cover_locator():
    from pathlib import Path

    from django.conf import settings

    from nassav.resource_media import FileCoverLocator
    from nassav.utils import generate_etag_for_file, generate_thumbnail

    return FileCoverLocator(
        Path(settings.COVER_DIR),
        Path(
            getattr(settings, "THUMBNAIL_DIR", Path(settings.COVER_DIR) / "thumbnails")
        ),
        generate_thumbnail,
        generate_etag_for_file,
    )


def build_translation_requests():
    from nassav.translation_requests import DjangoTranslationRequests

    def dispatch(avid):
        from nassav.tasks import translate_title_task

        return translate_title_task.delay(avid)

    return DjangoTranslationRequests(dispatch)


def build_task_assets(records=None):
    from pathlib import Path

    from django.conf import settings

    from nassav.task_assets import TaskAssets
    from nassav.task_records import DjangoTaskRecords

    return TaskAssets(
        {
            "cover": Path(settings.COVER_DIR),
            "avatar": Path(settings.AVATAR_DIR),
            "video": Path(settings.VIDEO_DIR),
        },
        records if records is not None else DjangoTaskRecords(),
    )


def build_resource_service(source_manager=None, scraper_manager=None, **overrides):
    from nassav.resource_adapters import (
        CeleryTranslationSubmitter,
        DjangoResourceReader,
        FileResourceAssets,
        SignalResourceEvents,
    )
    from nassav.resource_persistence import DjangoResourcePersistence
    from nassav.resource_workflow import ResourceService

    if source_manager is None:
        from nassav.source.SourceManager import source_manager
    if scraper_manager is None:
        from nassav.scraper.ScraperManager import scraper_manager
    defaults = {
        "persistence": lambda: DjangoResourcePersistence(),
        "reader": lambda: DjangoResourceReader(),
        "assets": lambda: FileResourceAssets(scraper_manager),
        "translations": lambda: CeleryTranslationSubmitter(),
        "events": lambda: SignalResourceEvents(),
    }
    dependencies = {
        key: overrides[key] if key in overrides else factory()
        for key, factory in defaults.items()
    }
    return ResourceService(source_manager, scraper_manager, **dependencies)
