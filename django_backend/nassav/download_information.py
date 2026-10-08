"""Download information resolution and execution capabilities."""

from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass

from loguru import logger

from nassav.resource_contracts import ResourceWorkflow
from nassav.resource_data import AVDownloadInfo


@dataclass(frozen=True)
class ResolvedDownload:
    info: AVDownloadInfo
    domain: str


class DownloadInfoResolver(ABC):
    @abstractmethod
    def resolve(
        self, avid: str, *, control=None, force=False
    ) -> ResolvedDownload | None:
        raise NotImplementedError


class ResourceDownloadInfoResolver(DownloadInfoResolver):
    def __init__(
        self,
        resources: ResourceWorkflow,
        prepare_directory: Callable[[str], object],
        domain_lookup: Callable[[str], str],
    ):
        self.resources = resources
        self.prepare_directory = prepare_directory
        self.domain_lookup = domain_lookup

    def resolve(
        self, avid: str, *, control=None, force=False
    ) -> ResolvedDownload | None:
        self.prepare_directory(avid)
        info = self.resources.load_cached_metadata(avid)
        if not info or not info.m3u8:
            logger.warning("缓存不存在，重新获取 {} 的信息", avid)
            try:
                self.resources.add_resource(avid, source="any")
                info = self.resources.load_cached_metadata(avid)
            except Exception as error:
                logger.warning("添加资源异常: {}, 尝试加载缓存", error)
                info = self.resources.load_cached_metadata(avid)
            if not info:
                logger.error("无法获取 {} 的下载信息", avid)
                return None
        return ResolvedDownload(info, self.domain_lookup(info.source))


class ReadOnlyDownloadInfoResolver(DownloadInfoResolver):
    """Resolve links without calling a save/refresh workflow or writing assets."""

    def __init__(self, cached: Callable, lookup: Callable, domain_lookup: Callable):
        self.cached, self.lookup, self.domain_lookup = cached, lookup, domain_lookup

    def resolve(
        self, avid: str, *, control=None, force=False
    ) -> ResolvedDownload | None:
        info = self.cached(avid)
        if not info or not info.m3u8:
            info, _, _, _ = self.lookup(avid)
        return ResolvedDownload(info, self.domain_lookup(info.source)) if info else None


class ProviderDownloadInfoResolver(DownloadInfoResolver):
    """Resolve fresh playback facts without scraping metadata or publishing resource assets."""

    def __init__(self, preparation, *, preferred_source=None):
        self.preparation = preparation
        self.preferred_source = preferred_source or (lambda avid: None)

    def resolve(
        self, avid: str, *, control=None, force=False
    ) -> ResolvedDownload | None:
        from nassav.task_network import TaskNetworkControl

        control = control if control is not None else TaskNetworkControl(lambda: None)
        gateway = self.preparation(control)
        preferred = self.preferred_source(avid)
        selected = (
            preferred
            if preferred and gateway.sources.get_source(preferred) is not None
            else "any"
        )
        prepared, _ = gateway.source(avid, selected, force=force)
        info = AVDownloadInfo(**prepared["info"])
        adapter = gateway.sources.get_source(prepared["source_name"])
        if adapter is None:
            return None
        return ResolvedDownload(info, adapter.domain)
