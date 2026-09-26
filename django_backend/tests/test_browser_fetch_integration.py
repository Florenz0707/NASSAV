"""Explicit opt-in online browser probes; no database writes.

Run with BROWSER_FETCH_EXTERNAL=1 and set BROWSER_FETCH_URL plus positive detail URLs.
"""

import os

import pytest
from nassav.page_fetching.browser import ByparrPageClient
from nassav.source.Jable import Jable
from nassav.source.MissAV import MissAV

pytestmark = pytest.mark.external


@pytest.fixture(autouse=True)
def require_external_opt_in():
    if os.environ.get("BROWSER_FETCH_EXTERNAL") != "1":
        pytest.skip("Set BROWSER_FETCH_EXTERNAL=1 to run online browser probes")


@pytest.mark.parametrize(
    ("env_name", "source_class", "avid_env"),
    [
        ("BROWSER_FETCH_MISSAV_URL", MissAV, "BROWSER_FETCH_MISSAV_AVID"),
        ("BROWSER_FETCH_JABLE_URL", Jable, "BROWSER_FETCH_JABLE_AVID"),
    ],
)
def test_online_detail_has_business_structure(env_name, source_class, avid_env):
    url = os.environ[env_name]
    avid = os.environ[avid_env]
    client = ByparrPageClient(
        os.environ.get("BROWSER_FETCH_URL", "http://127.0.0.1:8192")
    )
    result = client.fetch(url, timeout_ms=60000)
    assert result.ok, result.failure
    source = source_class()
    if isinstance(source, MissAV):
        assert source._is_detail_page_html(result.html, avid)
    else:
        assert source._is_detail_page_html(result.html)
