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


def build_translation_workflow(expected_generations=None):
    from nassav.translation_adapters import (
        DjangoTranslationRepository,
        ManagerTextTranslator,
    )
    from nassav.translation_workflow import TitleTranslationUseCase
    from nassav.translator import translator_manager

    return TitleTranslationUseCase(
        DjangoTranslationRepository(expected_generations),
        ManagerTextTranslator(translator_manager),
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

    def dispatch(avid, generation):
        from nassav.tasks import translate_title_task

        return translate_title_task.delay(avid, expected_generation=generation)

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


def build_task_records():
    from pathlib import Path
    from django.conf import settings
    from nassav.resource_file_locks import resource_file_lock
    from nassav.task_records import DjangoTaskRecords

    return DjangoTaskRecords(
        lambda avid: resource_file_lock(avid, Path(settings.COVER_DIR))
    )


def build_controlled_download(lease):
    from django.conf import settings
    from django.utils import timezone

    from nassav.controlled_download import ControlledDownload
    from nassav.download_information import ReadOnlyDownloadInfoResolver
    from nassav.download_resume import HLSResumeGuard
    from nassav.m3u8downloader import N_m3u8DL_RE
    from nassav.models import AVResource
    from nassav.resource_service import resource_service
    from nassav.source.SourceManager import source_manager
    from nassav.task_download_projection import DownloadTaskProjection

    def persist(resource_avid):
        path = settings.VIDEO_DIR / f"{resource_avid}.mp4"
        if not AVResource.objects.filter(avid=resource_avid).update(
            file_exists=True,
            file_size=path.stat().st_size,
            video_saved_at=timezone.now(),
        ):
            raise RuntimeError("下载资源元数据不存在，拒绝提交")

    records = build_task_records()
    resolver = ReadOnlyDownloadInfoResolver(
        resource_service.load_cached_metadata,
        source_manager.get_info_from_any_source,
        lambda name: settings.SOURCE_CONFIG.get(name.lower(), {}).get(
            "domain", f"{name.lower()}.com"
        ),
    )
    return ControlledDownload(
        records,
        build_task_assets(records),
        resolver,
        N_m3u8DL_RE(proxy=settings.DOWNLOAD_PROXY_URL or None),
        lease,
        persist,
        guard=HLSResumeGuard(proxy=settings.DOWNLOAD_PROXY_URL or None),
        project=DownloadTaskProjection(lease),
    )


def build_controlled_scrape(*, continuation=None):
    from django.conf import settings
    from nassav.controlled_scrape import ControlledScrape
    from nassav.resource_persistence import DjangoResourcePersistence
    from nassav.scrape_preparation import ScrapePreparation
    from nassav.scraper.ScraperManager import ScraperManager
    from nassav.source.SourceManager import SourceManager
    from nassav.task_network import TaskBrowserSession
    from nassav.task_resource_persistence import (
        TaskResourcePersistence,
        resource_revision,
    )

    records = build_task_records()
    assets = build_task_assets(records)

    def preparation(control):
        # No control state is installed on the application's shared singletons.
        sources = SourceManager(check=control.check)
        proxy = settings.PROXY_URL if settings.PROXY_ENABLED else None
        metadata = ScraperManager(proxy, check=control.check)
        for _, source in sources.get_sources():
            source.set_task_control(control)
            fetcher = getattr(source, "page_fetcher", None)
            if fetcher is not None:
                fetcher.timeout_ms = min(fetcher.timeout_ms, 60000)
                fetcher.set_task_control(control)
                if fetcher.browser is not None:
                    fetcher.browser.set_task_transport(TaskBrowserSession(control))
        for _, scraper in metadata.get_scrapers():
            scraper.set_task_control(control)
        return ScrapePreparation(sources, metadata, control)

    def project(snapshot):
        from nassav.consumers import send_task_update

        # A version hint carries no private checkpoint or credentials.
        send_task_update(
            "task_job_update",
            {key: snapshot[key] for key in ("job_id", "job_type", "version")},
        )

    def continue_translation(token):
        from nassav.task_dispatch import dispatch_scrapes

        snapshot = records.get(token.job_id)
        if snapshot["translation"].get("state") in {"completed", "skipped"}:
            return records.finish(token, "succeeded")
        options = records.configuration(token.job_id)
        requested = (
            snapshot["action"] == "add"
            and bool(snapshot["checkpoint"].get("prepared", {}).get("metadata"))
        ) or (snapshot["action"] == "refresh" and options.get("retranslate", False))
        if not requested:
            records.translation_transaction(token, "not_requested", lambda: None)
            return records.finish(token, "succeeded")
        snapshot = records.handoff_translation(token)
        dispatch_scrapes(records)
        return records.get(token.job_id)

    def existing(avid):
        from nassav.models import AVResource

        return AVResource.objects.select_for_update().get(avid=avid)

    return ControlledScrape(
        records,
        assets,
        preparation,
        resource_revision,
        TaskResourcePersistence(DjangoResourcePersistence()).save,
        build_task_resource_events(),
        continuation=continuation if continuation is not None else continue_translation,
        project=project,
        existing=existing,
    )


def build_controlled_translation():
    from nassav.controlled_translation import ControlledTranslation
    from nassav.owned_translation import OwnedTranslation
    from nassav.translator.TranslatorManager import TranslatorManager

    records = build_task_records()

    def project(snapshot):
        from nassav.consumers import send_task_update

        send_task_update(
            "task_job_update",
            {key: snapshot[key] for key in ("job_id", "job_type", "version")},
        )

    return ControlledTranslation(
        records,
        build_task_assets(records),
        OwnedTranslation(),
        lambda control: TranslatorManager(task_control=control),
        project,
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


def build_task_resource_events():
    from pathlib import Path
    from django.conf import settings
    from nassav.controlled_scrape import ControlledScrape
    from nassav.resource_adapters import SignalResourceEvents
    from nassav.task_resource_events import TaskResourceEvents

    def publish(event, avid, event_id):
        SignalResourceEvents().publish(
            event,
            ControlledScrape,
            avid,
            {"event_id": event_id, "resource": {"avid": avid}},
        )

    return TaskResourceEvents(
        Path(settings.COVER_DIR).parent / ".nassav-task-events", publish
    )


def build_task_recovery():
    from nassav.download_queue import get_redis_client
    from nassav.owned_translation import OwnedTranslation
    from nassav.task_dispatch import dispatch_downloads, dispatch_scrapes
    from nassav.task_recovery import TaskRecovery

    records = build_task_records()

    def dispatch(records):
        return {
            "download": dispatch_downloads(records),
            "scrape": dispatch_scrapes(records),
        }

    def interrupt(checkpoint, cancelled):
        claim = checkpoint.get("translation_claim")
        if claim:
            OwnedTranslation.interrupt(claim, cancel=cancelled)

    return TaskRecovery(
        records,
        build_task_assets(records),
        dispatch=dispatch,
        events=build_task_resource_events(),
        redis_client=get_redis_client,
        interrupt=interrupt,
    )
