"""Default adapter factories; business managers also accept injected factories.

Concrete adapters are imported inside each builder to avoid package initialization
cycles. Builders construct dependencies without performing network requests.
"""

from collections.abc import Callable
from contextlib import contextmanager
from typing import TYPE_CHECKING
from nassav.source_registry import source_provider_types


def build_library_membership():
    from nassav.library_membership import LibraryMembership

    return LibraryMembership(build_membership_records())


def build_membership_records():
    from nassav.library_records import DjangoMembershipRecords

    return DjangoMembershipRecords(
        detach_demand=build_operation_records().detach_membership
    )


def build_operation_records():
    from django.conf import settings
    from nassav.shared_work_records import DjangoOperationRecords
    from nassav.consumers import send_operation_hint
    from nassav.resource_version_publication import VersionPublications

    return DjangoOperationRecords(
        build_task_records(),
        hint=send_operation_hint,
        publication=VersionPublications if settings.SHARED_LIBRARY_ENABLED else None,
        allow_private=settings.SHARED_LIBRARY_ENABLED,
    )


def build_credential_records():
    from django.conf import settings
    from nassav.credential_crypto import CredentialKeyring
    from nassav.credential_records import DjangoCredentialRecords

    keyring = CredentialKeyring.from_file(settings.SOURCE_CREDENTIAL_KEYRING_FILE)
    return DjangoCredentialRecords(keyring, configured_source_origins())


def configured_source_origins():
    from django.conf import settings
    from nassav.source_registry import configured_source_origins as origins

    return origins(settings.SOURCE_CONFIG)


def build_playback_source_binding(avid):
    from nassav.models import AVResource
    from nassav.credential_playback import capture_source_binding

    return capture_source_binding(
        build_credential_records(), AVResource.objects.get(avid=avid).source.lower()
    )


def build_account_management():
    from nassav.account_management import AccountManagement
    from nassav.account_records import DjangoAccountCommands

    return AccountManagement(
        DjangoAccountCommands(build_membership_records(), build_task_records())
    )


if TYPE_CHECKING:
    from nassav.scoped_source_context import ScopedSourceContext
    from nassav.page_fetching.factory import BrowserFetchConfig
    from nassav.page_fetching.proxy_server import ProxyServer
    from nassav.scraper.ScraperBase import ScraperBase
    from nassav.source.SourceBase import SourceBase
    from nassav.translator.TranslatorBase import TranslatorBase


def source_factories(
    proxy: str | None,
    browser_config: "BrowserFetchConfig",
    save_cookie: Callable[[str, str], bool],
    *,
    proxy_server: "ProxyServer | None" = None,
    user_id: int | None = None,
    credential_id=None,
) -> dict[str, Callable[[], "SourceBase"]]:
    from django.conf import settings
    from nassav.page_fetching import create_page_fetch_service
    from nassav.page_fetching.factory import create_proxy_server

    providers = source_provider_types()
    Jable, Memo, MissAV = providers["jable"], providers["memo"], providers["missav"]

    server = proxy_server or create_proxy_server(browser_config)

    def scoped(source):
        if settings.SOURCE_CREDENTIALS_ENABLED:
            bind_source_credentials(
                source, server, user_id=user_id, credential_id=credential_id
            )
        return source

    return {
        "missav": lambda: scoped(
            MissAV(
                proxy,
                page_fetcher=create_page_fetch_service(
                    browser_config, proxy_url=proxy, proxy_server=server
                ),
                cookie_saver=lambda cookie: save_cookie("MissAV", cookie),
            )
        ),
        "jable": lambda: scoped(
            Jable(
                proxy,
                page_fetcher=create_page_fetch_service(
                    browser_config, proxy_url=proxy, proxy_server=server
                ),
            )
        ),
        "memo": lambda: scoped(Memo(proxy)),
    }


def bind_source_credentials(source, server, *, user_id=None, credential_id=None):
    from nassav.scoped_source_context import CredentialSourceContext
    from nassav.source.CookieRepository import proxy_route_profile

    source.bind_credential_context(
        CredentialSourceContext(
            build_credential_records,
            source.get_source_name(),
            user_id=user_id,
            credential_id=credential_id,
            egress_profile=proxy_route_profile(source.proxy) or "direct",
            browser_context=server.session_capabilities.context_revision,
            capabilities=server.session_capabilities,
            check=lambda: (
                source.task_control.check() if source.task_control is not None else None
            ),
        )
    )


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


def external_search_adapters(
    *, proxy_server: "ProxyServer | None" = None, user_id=None
):
    from nassav.external_search import (
        JableExternalSourceAdapter,
        MissAVExternalSourceAdapter,
        PlaceholderExternalSourceAdapter,
    )
    from django.conf import settings
    from nassav.source.SourceManager import source_manager
    from nassav.page_fetching.factory import create_proxy_server

    factories = source_factories(
        settings.PROXY_URL if settings.PROXY_ENABLED else None,
        settings.BROWSER_FETCH_CONFIG,
        source_manager.set_source_cookie,
        proxy_server=proxy_server or create_proxy_server(settings.BROWSER_FETCH_CONFIG),
        user_id=user_id,
    )

    templates = (
        {
            name: factory()
            for name, factory in factories.items()
            if settings.SOURCE_CONFIG.get(name, {}).get("weight", 0)
        }
        if settings.SOURCE_CREDENTIALS_ENABLED
        else None
    )

    def lookup(name):
        return (
            templates.get(name.lower())
            if templates is not None
            else source_manager.get_source(name)
        )

    def factory(name):
        source = factories[name]()
        template = lookup(name)
        if (
            templates is not None
            and template is not None
            and template.credential_context is not None
        ):
            source.bind_credential_context(
                template.credential_context.fork(
                    lambda: (
                        source.task_control.check()
                        if source.task_control is not None
                        else None
                    )
                )
            )
        return source

    def scope(name):
        return lambda check: _controlled_source_scope(lambda: factory(name), check)

    def facts_lookup(name, items):
        from nassav.provider_facts import SourceFactsLookup
        from nassav.source.SourceBase import SourceBase

        source = lookup(name)
        if not isinstance(source, SourceBase):
            return {}
        return SourceFactsLookup(build_provider_facts_cache(), source).read_facts(
            [(item["avid"], item.get("detail_url", "")) for item in items]
        )

    return {
        "jable": JableExternalSourceAdapter(
            source_scope=scope("jable"), facts_lookup=facts_lookup, source_lookup=lookup
        ),
        "missav": MissAVExternalSourceAdapter(
            source_scope=scope("missav"),
            facts_lookup=facts_lookup,
            source_lookup=lookup,
        ),
        "memo": PlaceholderExternalSourceAdapter("memo"),
    }


@contextmanager
def _controlled_source_scope(factory, check, parent_control=None):
    """Own a fresh source, session and phase budget for one concurrent operation."""
    from nassav.task_network import TaskBrowserSession, TaskNetworkControl

    check()
    control = (
        parent_control.fork(check) if parent_control else TaskNetworkControl(check)
    )
    source = factory()
    source.set_task_control(control)
    fetcher = getattr(source, "page_fetcher", None)
    try:
        if fetcher is not None:
            fetcher.set_task_control(control)
            if fetcher.browser is not None:
                fetcher.browser.set_task_transport(TaskBrowserSession(control))
        source.load_cookie_from_db()
        check()
        yield source
        check()
    finally:
        if fetcher is not None and fetcher.browser is not None:
            fetcher.browser.close()


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


def build_provider_facts_cache():
    from django.utils import timezone
    from nassav.resource_cache import ProviderFactsCache, DjangoProviderFactsStore

    return ProviderFactsCache(DjangoProviderFactsStore(), now=timezone.now)


def build_recommendation_manager(*, context=None, control=None, user_id=None):
    from django.conf import settings

    from nassav.recommendation.data_access import (
        DjangoCandidateInventory,
        DjangoRecommendationContext,
    )
    from nassav.recommendation.jable_page_lookup import JablePageLookupRecommender
    from nassav.recommendation.workflow import RecommenderManager
    from nassav.source import Jable
    from nassav.page_fetching.factory import (
        create_proxy_server,
        create_page_fetch_service,
    )

    proxy_server = create_proxy_server(settings.BROWSER_FETCH_CONFIG)
    credential_context: list["ScopedSourceContext | None"] = [None]

    def source_factory():
        source = Jable(
            proxy=settings.PROXY_URL if settings.PROXY_ENABLED else None,
            strict_failures=True,
            facts_cache=build_provider_facts_cache(),
            page_fetcher=create_page_fetch_service(
                settings.BROWSER_FETCH_CONFIG,
                proxy_url=settings.PROXY_URL if settings.PROXY_ENABLED else None,
                proxy_server=proxy_server,
            ),
        )
        if settings.SOURCE_CREDENTIALS_ENABLED:
            bound = credential_context[0]
            if bound is None:
                bind_source_credentials(source, proxy_server, user_id=user_id)
                credential_context[0] = source.credential_context
            else:
                source.bind_credential_context(
                    bound.fork(
                        lambda: (
                            source.task_control.check()
                            if source.task_control is not None
                            else None
                        )
                    )
                )
        return source

    def jable_factory(strategy):
        from nassav.source.search_contracts import SourceSearchUnavailable

        if not settings.SOURCE_CONFIG.get("jable", {}).get("weight", 0):
            raise SourceSearchUnavailable("jable_disabled")
        source = source_factory()
        if control is not None:
            from nassav.task_network import TaskBrowserSession

            source.set_task_control(control)
            source.page_fetcher.set_task_control(control)
            if source.page_fetcher.browser is not None:
                source.page_fetcher.browser.set_task_transport(
                    TaskBrowserSession(control)
                )
        return JablePageLookupRecommender(
            jable=source,
            candidate_inventory=DjangoCandidateInventory(user_id=user_id),
            seed_provider=strategy.seed_provider_builder(),
            factors=[builder() for builder in strategy.factor_builders],
            proxy_server=proxy_server,
            source_scope=lambda check: _controlled_source_scope(
                source_factory, check, control
            ),
            check=control.check if control is not None else None,
            execution_budget=getattr(context, "execution_budget", None),
            **strategy.recommender_kwargs,
        )

    def persist_scoped(persist):
        bound = credential_context[0]
        return bound.publish(persist) if bound is not None else persist()

    return RecommenderManager(
        context
        if context is not None
        else DjangoRecommendationContext(user_id=user_id),
        {"jable_page_lookup": jable_factory},
        publication_fence=persist_scoped,
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
    from nassav.download_information import ProviderDownloadInfoResolver
    from nassav.download_resume import HLSResumeGuard
    from nassav.m3u8downloader import N_m3u8DL_RE
    from nassav.models import AVResource
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
    resolver = ProviderDownloadInfoResolver(
        build_scrape_preparation,
        preferred_source=lambda avid: (
            AVResource.objects.filter(avid=avid)
            .values_list("source", flat=True)
            .first()
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


def build_scrape_preparation(control):
    from django.conf import settings
    from nassav.scrape_preparation import ScrapePreparation
    from nassav.scraper.ScraperManager import ScraperManager
    from nassav.source.SourceManager import SourceManager
    from nassav.task_network import TaskBrowserSession

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
    return ScrapePreparation(
        sources, metadata, control, facts_cache=build_provider_facts_cache()
    )


def build_controlled_scrape(*, continuation=None):
    from nassav.controlled_scrape import ControlledScrape
    from nassav.resource_persistence import DjangoResourcePersistence
    from nassav.task_resource_persistence import (
        TaskResourcePersistence,
        resource_revision,
    )

    records = build_task_records()
    assets = build_task_assets(records)

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
        build_scrape_preparation,
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
        from nassav.shared_work_dispatch import dispatch_shared

        return {
            "download": dispatch_downloads(records),
            "scrape": dispatch_scrapes(records),
            "shared": dispatch_shared(),
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
        reconcile=build_operation_records().project_pending,
    )


def build_playback_resolver():
    from django.conf import settings
    from nassav.playback.preparation import SourcePlaybackResolver
    from nassav.source.SourceManager import source_manager

    factories = source_factories(
        settings.PROXY_URL if settings.PROXY_ENABLED else None,
        settings.BROWSER_FETCH_CONFIG,
        source_manager.set_source_cookie,
    )

    @contextmanager
    def scope(name, control):
        if name not in factories or source_manager.get_source(name) is None:
            raise ValueError("Playback source unavailable")
        with _controlled_source_scope(
            factories[name], control.check, control
        ) as source:
            yield source

    return SourcePlaybackResolver(
        scope,
        build_provider_facts_cache(),
        settings.RESOURCE_CACHE_POLICY["PlaybackTTLSeconds"],
    )


def build_playback_registry():
    import redis
    from django.conf import settings
    from nassav.playback.redis_state import RedisAssetRegistry

    return RedisAssetRegistry(
        redis.from_url(
            settings.CELERY_BROKER_URL, socket_timeout=2, socket_connect_timeout=2
        )
    )


def build_playback_gateway():
    from django.conf import settings
    from nassav.playback.policy import TargetPolicy
    from nassav.playback.curl_transport import CurlPlaybackTransport
    from nassav.playback.redis_state import RedisPlaybackCapacity
    from nassav.playback.gateway import PlaybackGateway

    registry = build_playback_registry()
    policy = TargetPolicy(settings.PLAYBACK_ALLOWED_HOSTS)
    return PlaybackGateway(
        CurlPlaybackTransport(
            policy,
            settings.PROXY_URL if settings.PROXY_ENABLED else None,
            proxy_targets_trusted=settings.PLAYBACK_PROXY_TARGETS_TRUSTED,
        ),
        policy,
        registry,
        RedisPlaybackCapacity(registry.client, settings.PLAYBACK_MAX_MEDIA_REQUESTS),
    )


def build_playback_validator():
    from nassav.playback.identity import PlaybackIdentityValidator

    class Validator:
        def validate(self, session_id, descriptor, baseline, control):
            gateway = build_playback_gateway()
            try:
                return PlaybackIdentityValidator(
                    gateway.transport, gateway.policy, gateway.capacity
                ).validate(session_id, descriptor, baseline, control)
            finally:
                gateway.registry.client.close()

    return Validator()


def build_local_video_locator():
    from django.conf import settings
    from nassav.playback.local_files import DjangoLocalVideoLocator

    return DjangoLocalVideoLocator(settings.VIDEO_DIR, settings.COVER_DIR)


def build_local_playback_gateway():
    from django.conf import settings
    from nassav.playback.local_gateway import LocalPlaybackGateway
    from nassav.playback.redis_state import RedisPlaybackCapacity

    registry = build_playback_registry()
    return LocalPlaybackGateway(
        RedisPlaybackCapacity(registry.client, settings.PLAYBACK_MAX_MEDIA_REQUESTS)
    )


def build_shared_workflow(job_id):
    """Frozen source selection; each network operation owns a source/transport."""
    from django.conf import settings
    from nassav.shared_work_models import SharedWork
    from nassav.credential_models import SourceCredential
    from nassav.shared_execution_records import DjangoSharedExecutionRecords
    from nassav.resource_version_publication import VersionPublications
    from nassav.versioned_task_publication import (
        VersionedScrapePublication,
        VersionedDownloadPublication,
    )
    from nassav.shared_worker_resources import WorkflowResources
    from nassav.source.SourceManager import SourceManager, source_manager
    from nassav.scraper.ScraperManager import ScraperManager
    from nassav.scrape_preparation import ScrapePreparation
    from nassav.controlled_scrape import ControlledScrape
    from nassav.controlled_download import ControlledDownload
    from nassav.translator.TranslatorManager import TranslatorManager
    from nassav.download_information import ProviderDownloadInfoResolver
    from nassav.download_resume import HLSResumeGuard
    from nassav.download_leases import DownloadLease
    from nassav.download_queue import get_redis_client
    from nassav.m3u8downloader import N_m3u8DL_RE
    from nassav.resource_version_models import ResourceVersionPointer
    from nassav.task_network import TaskBrowserSession

    if not settings.SHARED_LIBRARY_ENABLED or not settings.SOURCE_CREDENTIALS_ENABLED:
        raise ValueError("Shared execution is not enabled")
    work = SharedWork.objects.get(job_id=job_id)
    source_name = work.spec["source"]
    ref_id = work.credential_refs.get("credential_id")
    ref = SourceCredential.objects.get(pk=ref_id) if ref_id is not None else None
    owner_id = ref.owner_id if ref is not None else None
    proxy = settings.PROXY_URL if settings.PROXY_ENABLED else None
    factories = source_factories(
        proxy,
        settings.BROWSER_FETCH_CONFIG,
        source_manager.set_source_cookie,
        user_id=owner_id,
        credential_id=ref_id,
    )
    if source_name not in factories or not settings.SOURCE_CONFIG.get(
        source_name, {}
    ).get("weight"):
        raise ValueError("Source is not configured")
    template = factories[source_name]()
    parent = template.credential_context
    if parent is None:
        raise ValueError("Scoped source context required")
    cleanups = []

    def close_source(source):
        fetcher = getattr(source, "page_fetcher", None)
        if fetcher is not None and fetcher.browser is not None:
            fetcher.browser.close()

    cleanups.append(lambda: close_source(template))
    try:
        records = DjangoSharedExecutionRecords(parent)
        publications = VersionPublications(records)
        assets = build_task_assets(records)

        def preparation(control):
            def fresh():
                source = factories[source_name]()
                source.bind_credential_context(parent.fork(control.check))
                source.set_task_control(control)
                fetcher = getattr(source, "page_fetcher", None)
                if fetcher is not None:
                    fetcher.timeout_ms = min(fetcher.timeout_ms, 60000)
                    fetcher.set_task_control(control)
                    if fetcher.browser is not None:
                        fetcher.browser.set_task_transport(TaskBrowserSession(control))
                cleanups.append(lambda: close_source(source))
                return source

            sources = SourceManager(factories={source_name: fresh}, check=control.check)
            metadata = ScraperManager(proxy, check=control.check)
            for _, scraper in metadata.get_scrapers():
                scraper.set_task_control(control)
            return ScrapePreparation(
                sources, metadata, control, facts_cache=build_provider_facts_cache()
            )

        class NoResourceEvents:
            def flush(self, job_id):
                return None  # User projection follows ready publication, no legacy broadcast.

        if work.spec["kind"] == "scrape":
            policy = VersionedScrapePublication(
                records,
                publications,
                lambda control: TranslatorManager(task_control=control),
            )
            workflow = ControlledScrape(
                records,
                assets,
                preparation,
                lambda avid: None,
                policy.persist,
                NoResourceEvents(),
                publication=policy,
            )
        else:
            pointer = (
                ResourceVersionPointer.objects.filter(
                    pool=work.pool,
                    kind="metadata",
                    source_name=source_name,
                    access_scope=work.access_scope,
                    quality="best",
                )
                .select_related("current")
                .first()
            )
            snapshot = (
                pointer.current.metadata
                if pointer is not None and pointer.current is not None
                else {
                    "avid": work.pool.canonical_avid,
                    "source_title": work.pool.canonical_avid,
                }
            )
            policy = VersionedDownloadPublication(publications, snapshot)
            # Preserve the existing one-download slot and AVID writer exclusion.
            lease = DownloadLease(
                work.pool.canonical_avid, get_redis_client, job_id=str(work.job_id)
            )
            cleanups.append(lease.close)
            workflow = ControlledDownload(
                records,
                assets,
                ProviderDownloadInfoResolver(
                    preparation, preferred_source=lambda avid: source_name
                ),
                N_m3u8DL_RE(proxy=settings.DOWNLOAD_PROXY_URL or None),
                lease,
                lambda avid: None,
                guard=HLSResumeGuard(proxy=settings.DOWNLOAD_PROXY_URL or None),
                publication=policy,
            )
        return WorkflowResources(workflow, cleanups)
    except BaseException:
        WorkflowResources(None, cleanups).close()
        raise
