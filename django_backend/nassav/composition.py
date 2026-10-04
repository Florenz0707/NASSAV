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
    from nassav.services import VideoDownloadService
    from nassav.download_information import ResourceDownloadInfoResolver
    from nassav.resource_service import resource_service
    from nassav.source.SourceManager import source_manager
    from nassav.m3u8downloader import N_m3u8DL_RE

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
    from nassav.translation_workflow import TitleTranslationUseCase
    from nassav.translation_adapters import (
        DjangoTranslationRepository,
        ManagerTextTranslator,
    )
    from nassav.translator import translator_manager

    return TitleTranslationUseCase(
        DjangoTranslationRepository(), ManagerTextTranslator(translator_manager)
    )
