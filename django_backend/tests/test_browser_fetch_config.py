"""Configuration priority and validation for browser fetching."""

import pytest
from nassav.page_fetching.factory import (
    create_page_fetch_service,
    normalize_config,
    validate_strategy,
)


def test_old_config_maps_only_when_new_block_absent():
    config = normalize_config(
        {"FlareSolverr": {"Enable": True, "url": "http://old:8191", "timeout": 60000}}
    )
    assert (config.provider, config.url, config.enabled) == (
        "flaresolverr",
        "http://old:8191",
        True,
    )
    assert create_page_fetch_service(config).browser.provider == "flaresolverr"


def test_new_config_wins_even_when_disabled():
    config = normalize_config(
        {
            "FlareSolverr": {"Enable": True},
            "BrowserFetch": {
                "Enable": False,
                "provider": "byparr",
                "url": "http://127.0.0.1:8192",
                "timeout_ms": 60000,
            },
        }
    )
    assert not config.enabled
    assert create_page_fetch_service(config).browser is None


@pytest.mark.parametrize(
    "block",
    [
        {"Enable": True, "provider": "unknown"},
        {"Enable": True, "url": "ftp://host"},
        {"Enable": True, "url": "http://host:bad"},
        {"Enable": True, "url": "http://user:pass@host:8192"},
        {"Enable": True, "timeout_ms": 500},
        {"Enable": True, "timeout_ms": 1500},
        {"Enable": "yes"},
        "bad",
    ],
)
def test_invalid_new_config_raises(block):
    with pytest.raises(ValueError):
        normalize_config({"BrowserFetch": block})


def test_invalid_strategy_raises():
    with pytest.raises(ValueError):
        validate_strategy("retry_forever")
