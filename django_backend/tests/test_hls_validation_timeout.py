"""Transient resume validation failures retain safe cache and a retryable job."""

import pytest
from curl_cffi.requests.exceptions import Timeout

from nassav.download_resume import HLSResumeGuard


def test_partial_timeout_retries_without_concatenating_response(monkeypatch):
    calls = []

    class Session:
        def __init__(self, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def get(self, url, **kwargs):
            calls.append(kwargs["timeout"])
            if len(calls) == 1:
                kwargs["content_callback"](b"partial")
                raise Timeout("curl timeout with partial body")
            kwargs["content_callback"](b"complete")
            return type("Response", (), {"raise_for_status": lambda self: None})()

    monkeypatch.setattr("nassav.download_resume.requests.Session", Session)
    assert (
        HLSResumeGuard()._fetch("http://fixture/segment.ts", {}, lambda: None)
        == b"complete"
    )
    assert calls == [(5, 55), (5, 55)]


def test_timeout_retry_is_bounded_and_preserves_stop_priority(monkeypatch):
    from nassav.download_resume import DownloadValidationTimeout
    from nassav.task_control_rules import TaskPauseRequested

    calls = []

    class Session:
        def __init__(self, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def get(self, *args, **kwargs):
            calls.append(True)
            raise Timeout("temporary")

    monkeypatch.setattr("nassav.download_resume.requests.Session", Session)
    monkeypatch.setattr("nassav.download_resume.time.sleep", lambda _: None)
    with pytest.raises(DownloadValidationTimeout):
        HLSResumeGuard()._fetch("http://fixture/segment.ts", {}, lambda: None)
    assert len(calls) == 2
    calls.clear()

    def stop():
        if calls:
            raise TaskPauseRequested("pause")

    with pytest.raises(TaskPauseRequested):
        HLSResumeGuard()._fetch("http://fixture/segment.ts", {}, stop)
    assert len(calls) == 1
