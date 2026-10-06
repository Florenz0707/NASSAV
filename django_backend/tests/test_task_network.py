"""Task-scoped requests enforce total budgets, callback stops and retry boundaries."""

from pathlib import Path

import pytest
from curl_cffi.curl import CURL_WRITEFUNC_ERROR

from nassav.task_control_rules import TaskCancelRequested
from nassav.task_network import (
    TaskBrowserSession,
    TaskNetworkControl,
    TaskNetworkTimeout,
)


def test_nested_budgets_restore_and_do_not_extend_parent():
    clock = [0.0]
    control = TaskNetworkControl(lambda: None, clock=lambda: clock[0])
    with control.phase(10):
        assert control.timeout(15) == 10
        with control.phase(20):
            clock[0] = 11
            with pytest.raises(TaskNetworkTimeout):
                control.check()
        assert control.deadline == 10
    assert control.deadline is None


def test_response_callback_reraises_control_exception(monkeypatch):
    from curl_cffi.requests.exceptions import RequestException

    stopped = [False]

    def check():
        if stopped[0]:
            raise TaskCancelRequested("stop")

    class Session:
        def __init__(self, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def request(self, method, url, **kwargs):
            callback = kwargs["content_callback"]
            assert callback(b"part") == 4
            stopped[0] = True
            assert callback(b"late data") == CURL_WRITEFUNC_ERROR
            raise RequestException("curl callback stopped")

    monkeypatch.setattr("curl_cffi.requests.Session", Session)
    with pytest.raises(TaskCancelRequested):
        TaskNetworkControl(check).request("GET", "http://fixture", timeout=15)


def test_browser_timeout_is_total_and_retains_provider_json():
    captured = {}

    class Control:
        def request(self, method, url, **kwargs):
            captured.update(method=method, **kwargs)
            return "response"

    assert (
        TaskBrowserSession(Control()).post(
            "http://fixture/v1", timeout=(5, 90), json={"maxTimeout": 60000}
        )
        == "response"
    )
    assert captured["timeout"] == 75
    assert captured["json"] == {"maxTimeout": 60000}


def test_source_retry_cannot_start_new_io_after_stop():
    from nassav.source.Memo import Memo

    source = Memo()
    source.set_task_control(
        TaskNetworkControl(lambda: (_ for _ in ()).throw(TaskCancelRequested()))
    )
    with pytest.raises(TaskCancelRequested):
        source.get_html("FIXTURE-1")


def test_scraper_does_not_swallow_stop_and_write_late_file(tmp_path):
    from nassav.scraper.Javbus import Javbus

    scraper = Javbus()
    scraper.set_task_control(
        TaskNetworkControl(lambda: (_ for _ in ()).throw(TaskCancelRequested()))
    )
    with pytest.raises(TaskCancelRequested):
        scraper.download_avatar("http://fixture", str(tmp_path / "avatar.jpg"))
    assert not (tmp_path / "avatar.jpg").exists()


def test_write_after_stop_creates_no_file(tmp_path):
    control = TaskNetworkControl(lambda: (_ for _ in ()).throw(TaskCancelRequested()))
    target: Path = tmp_path / "late.jpg"
    with pytest.raises(TaskCancelRequested):
        control.write(target, b"late")
    assert not target.exists()
