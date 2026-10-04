"""Exercise download orchestration through replaceable contracts without DB/worker."""

import pytest

from nassav.download_contracts import DownloadExecutor
from nassav.download_contracts import DownloadPersistence
from nassav.download_contracts import DownloadRuntime, DownloadRetriesExhausted
from nassav.download_workflow import DownloadUseCase, MockDownloadUseCase


class Runtime(DownloadRuntime):
    def __init__(self, *, slot=True, broken_release=False):
        self.slot, self.broken_release, self.calls = slot, broken_release, []

    def create_lock(self, avid, task_id):
        self.calls.append("lock")

    def wait_for_slot(self, max_wait_time):
        return self.slot

    def remove_lock(self, avid):
        self.calls.append("remove_lock")

    def remove_from_queue(self, avid):
        self.calls.append("remove_queue")

    def notify(self, event, data):
        self.calls.append((event, data))

    def queue_status(self):
        return {"tasks": []}

    def set_state(self, avid, state):
        self.calls.append(state)

    def set_progress(self, avid, percent, speed, *, eta):
        self.calls.append(("progress", percent))

    def release_slot(self):
        self.calls.append("release")
        if self.broken_release:
            raise RuntimeError("release unavailable")

    def remove_progress(self, avid):
        self.calls.append("remove_progress")


class Executor(DownloadExecutor):
    def __init__(self, outcome):
        self.outcome, self.calls = outcome, 0

    def download_video(self, avid, progress_callback=None, cancelled=None):
        self.calls += 1
        if isinstance(self.outcome, Exception):
            raise self.outcome
        progress_callback(100, "1 MB/s", "0s")
        return self.outcome


class Persistence(DownloadPersistence):
    def __init__(self):
        self.calls = []

    def mark_completed(self, avid):
        self.calls.append("completed")

    def mark_failed(self, avid):
        self.calls.append("failed")


def exhausted(error):
    raise DownloadRetriesExhausted() from error


@pytest.mark.parametrize("outcome", [True, False, RuntimeError("executor error")])
def test_download_outcomes_and_cleanup_survive_release_error(outcome):
    runtime, persistence = Runtime(broken_release=True), Persistence()
    result = DownloadUseCase(Executor(outcome), persistence, runtime).run(
        "case-001", "task", retry=exhausted
    )
    assert result["status"] == ("success" if outcome is True else "failed")
    assert persistence.calls == (["completed"] if outcome is True else ["failed"])
    assert "release" in runtime.calls
    assert "remove_lock" in runtime.calls
    assert "remove_progress" in runtime.calls
    assert runtime.calls[-1] == ("queue_status", {"tasks": []})


def test_slot_timeout_does_not_invoke_executor_or_persistence():
    runtime, persistence, executor = Runtime(slot=False), Persistence(), Executor(True)
    result = DownloadUseCase(executor, persistence, runtime).run(
        "case-002", "task", retry=exhausted
    )
    assert result["status"] == "failed"
    assert executor.calls == 0 and not persistence.calls
    assert "remove_lock" in runtime.calls and "remove_queue" in runtime.calls


def test_celery_retry_signal_propagates_after_cleanup():
    class RetrySignal(Exception):
        pass

    def retry(error):
        raise RetrySignal() from error

    runtime, persistence = Runtime(), Persistence()
    with pytest.raises(RetrySignal):
        DownloadUseCase(Executor(RuntimeError("retry")), persistence, runtime).run(
            "case-003", "task", retry=retry
        )
    assert not persistence.calls
    assert "remove_progress" in runtime.calls


def test_mock_download_uses_same_progress_contract_and_task_id():
    runtime = Runtime()
    result = MockDownloadUseCase(runtime, lambda seconds: None).run(
        "case-004", "task", duration_seconds=2
    )
    assert result["status"] == "completed"
    assert ("progress", 100) in runtime.calls
    assert any(
        isinstance(call, tuple)
        and call[0] == "task_completed"
        and call[1]["task_id"] == "task"
        for call in runtime.calls
    )


@pytest.mark.parametrize("raises", [False, True])
def test_information_resolver_prepares_cache_miss_and_keeps_exception_fallback(raises):
    from nassav.download_information import ResourceDownloadInfoResolver
    from nassav.resource_contracts import ResourceWorkflow
    from nassav.scraper import AVDownloadInfo

    calls = []
    info = AVDownloadInfo(
        avid="CASE-005", source="test", m3u8="https://offline.invalid/video.m3u8"
    )

    class Resources(ResourceWorkflow):
        def load_cached_metadata(self, avid):
            calls.append("cache")
            return info if "add" in calls else None

        def add_resource(self, avid, **kwargs):
            calls.append("add")
            if raises:
                raise RuntimeError("resource preparation partially failed")
            return {"success": True}

        def refresh_resource(self, avid, **kwargs):
            raise AssertionError("unexpected refresh")

    resolver = ResourceDownloadInfoResolver(
        Resources(),
        lambda avid: calls.append("directory"),
        lambda source: "source.test",
    )
    result = resolver.resolve("CASE-005")
    assert result.info is info and result.domain == "source.test"
    assert calls == ["directory", "cache", "add", "cache"]
