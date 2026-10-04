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
