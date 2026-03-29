import time

import pytest


@pytest.mark.django_db
def test_source_manager_refreshes_cookie_from_repository_after_local_ttl():
    from nassav.source.CookieRepository import source_cookie_repository
    from nassav.source.SourceManager import SourceManager

    manager = SourceManager()
    if "Jable" not in manager.sources:
        pytest.skip("Jable source is not enabled in current test settings")

    source_cookie_repository.set_cookie("Jable", "cookie-old")
    manager.refresh_source_cookie("Jable", force=True)
    assert manager.sources["Jable"].cookie == "cookie-old"

    source_cookie_repository.set_cookie("Jable", "cookie-new")
    manager._runtime_cookie_cache["jable"].expires_at = 0.0

    refreshed = manager.refresh_source_cookie("Jable")
    assert refreshed == "cookie-new"
    assert manager.sources["Jable"].cookie == "cookie-new"


@pytest.mark.django_db
def test_source_manager_refreshes_cookie_when_shared_version_changes_before_ttl():
    from nassav.source.CookieRepository import source_cookie_repository
    from nassav.source.SourceManager import SourceManager

    manager = SourceManager()
    if "Jable" not in manager.sources:
        pytest.skip("Jable source is not enabled in current test settings")

    old_record = source_cookie_repository.set_cookie("Jable", "cookie-old")
    manager.refresh_source_cookie("Jable", force=True)
    old_runtime = manager._runtime_cookie_cache["jable"]
    assert old_runtime.cookie == "cookie-old"
    assert old_runtime.updated_at == old_record.updated_at

    time.sleep(0.01)
    new_record = source_cookie_repository.set_cookie("Jable", "cookie-new")
    assert new_record.updated_at != old_record.updated_at

    refreshed = manager.refresh_source_cookie("Jable")
    new_runtime = manager._runtime_cookie_cache["jable"]
    assert refreshed == "cookie-new"
    assert manager.sources["Jable"].cookie == "cookie-new"
    assert new_runtime.updated_at == new_record.updated_at
    assert new_runtime.expires_at > old_runtime.expires_at


def test_scraper_manager_download_cover_uses_explicit_scraper_name():
    from nassav.scraper.ScraperManager import ScraperManager

    class FakeScraper:
        def __init__(self, name: str, metadata: dict | None = None):
            self.name = name
            self.metadata = metadata
            self.download_calls: list[tuple[str, str]] = []

        def get_scraper_name(self) -> str:
            return self.name

        def scrape(self, avid: str):
            _ = avid
            return self.metadata

        def download_cover(self, url: str, save_path: str) -> bool:
            self.download_calls.append((url, save_path))
            return True

    manager = ScraperManager(proxy=None)
    first = FakeScraper("Javbus", metadata={"title": "from-first"})
    second = FakeScraper("Busdmm", metadata=None)
    manager.scrapers = {
        "Javbus": first,
        "Busdmm": second,
    }

    metadata, scraper_name = manager.scrape_with_source("ABC-123")
    assert metadata == {"title": "from-first"}
    assert scraper_name == "Javbus"
    assert not hasattr(manager, "_last_successful_scraper")

    manager.download_cover(
        "https://img.example/cover.jpg",
        "/tmp/cover.jpg",
        scraper_name="Busdmm",
    )
    assert second.download_calls == [
        ("https://img.example/cover.jpg", "/tmp/cover.jpg")
    ]
    assert first.download_calls == []
