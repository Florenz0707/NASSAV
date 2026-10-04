"""R1 adapter contracts: uv run pytest tests/test_backend_contracts.py -v."""

import inspect
from concurrent.futures import ThreadPoolExecutor

import pytest

from nassav.m3u8downloader import M3u8DownloaderBase, N_m3u8DL_RE
from nassav.scraper.Javbus import Busdmm, Dmmsee, Javbus
from nassav.scraper.ScraperBase import ScraperBase
from nassav.scraper.ScraperManager import ScraperManager
from nassav.scraper import AVDownloadInfo
from nassav.source import Jable, Memo, MissAV
from nassav.source.SourceBase import SourceBase
from nassav.source.SourceManager import SourceManager
from nassav.source.capabilities import ListingSource
from nassav.translator.OllamaTranslator import OllamaTranslator
from nassav.translator.TranslatorBase import TranslatorBase
from nassav.translator.TranslatorManager import TranslatorManager


@pytest.mark.parametrize(
    "base", [SourceBase, ScraperBase, TranslatorBase, M3u8DownloaderBase]
)
def test_missing_required_abilities_prevent_instantiation(base):
    with pytest.raises(TypeError, match="abstract"):
        base()


@pytest.mark.parametrize(
    "adapter",
    [Jable, MissAV, Memo, Javbus, Busdmm, Dmmsee, OllamaTranslator, N_m3u8DL_RE],
)
def test_production_adapters_implement_required_contracts(adapter):
    assert not inspect.isabstract(adapter)


class FakeSource(SourceBase):
    def __init__(self):
        super().__init__()
        self.domain = "source.test"
        self.lookups = []

    def get_source_name(self):
        return "TestSource"

    def get_html(self, avid):
        self.lookups.append(avid)
        return "isolated page"

    def parse_html(self, html):
        return AVDownloadInfo(source="TestSource", source_title="Example", m3u8="url")

    def get_cover_url(self, html):
        return None


def test_injected_source_works_without_changing_manager_flow(monkeypatch):
    from nassav.source.CookieRepository import source_cookie_repository

    source = FakeSource()

    def disabled_factory():
        pytest.fail("disabled source must not be constructed")

    manager = SourceManager(
        factories={"testsource": lambda: source, "disabled": disabled_factory},
        config={"testsource": {"weight": 100}},
    )
    monkeypatch.setattr(
        source_cookie_repository, "get_cookie_record", lambda name: None
    )
    monkeypatch.setattr("time.sleep", lambda seconds: None)
    assert manager.get_source("testsource") is source
    assert manager.get_source("missing") is None
    snapshot = manager.get_sources()
    snapshot.clear()
    assert manager.get_sources() == [("TestSource", source)]
    info, selected, html, errors = manager.get_info_from_any_source("R1-001")
    assert selected is source and html == "isolated page" and errors == {}
    assert info.avid == "R1-001"
    assert manager.get_source("TestSource").get_home_url() == "https://source.test/"
    manager.get_info_from_any_source("R1-001")
    assert source.lookups == ["R1-001"]


def test_listing_ability_is_optional_and_unsupported_source_rejects_it():
    assert isinstance(Jable(), ListingSource)
    assert isinstance(MissAV(), ListingSource)
    memo = Memo()
    assert not isinstance(memo, ListingSource)
    with pytest.raises(NotImplementedError, match="listing search"):
        memo.search_listing("genres", "test")


class FakeScraper(ScraperBase):
    def get_scraper_name(self):
        return "TestScraper"

    def get_html(self, avid):
        return "isolated page"

    def parse_html(self, html, avid):
        return {"title": "Test Title", "avid": avid}

    def download_avatar(self, url, dest_path, max_retries=3):
        return True


def test_injected_scraper_uses_existing_template():
    scraper = FakeScraper()
    manager = ScraperManager(
        factories={"test": lambda: scraper}, config={"test": {"domain": "test"}}
    )
    assert manager.get_scrapers() == [("TestScraper", scraper)]
    assert manager.scrape_with_source("r1-002") == (
        {"title": "Test Title", "avid": "R1-002"},
        "TestScraper",
    )


class FakeTranslator(TranslatorBase):
    def __init__(self, calls, available):
        super().__init__()
        self.calls = calls
        self.available = available
        calls.append("construct")

    def get_translator_name(self):
        return "TestTranslator"

    def translate(self, text, source_lang="ja", target_lang="zh"):
        self.calls.append("translate")
        return "translated"

    def is_available(self):
        self.calls.append("probe")
        if isinstance(self.available, Exception):
            raise self.available
        return self.available


@pytest.mark.parametrize("available", [True, False, RuntimeError("offline")])
def test_translation_availability_is_lazy_and_probed_once(settings, available):
    settings.ACTIVE_TRANSLATOR = "test-config"
    settings.TRANSLATOR_CONFIG = {"test-config": {"type": "test", "timeout": 7}}
    calls = []

    def factory(timeout, config_name):
        assert (timeout, config_name) == (7, "test-config")
        return FakeTranslator(calls, available)

    manager = TranslatorManager(factories={"test": factory})
    assert calls == ["construct"]
    assert manager.translate("") is None
    assert calls == ["construct"]
    expected = available is True
    with ThreadPoolExecutor(max_workers=4) as pool:
        assert (
            list(pool.map(lambda _: manager.is_available(), range(8))) == [expected] * 8
        )
    assert calls.count("probe") == 1
    assert manager.get_available_translators() == (
        ["TestTranslator"] if expected else []
    )
    assert manager.translate("text") == ("translated" if expected else None)
    assert calls.count("probe") == 1
