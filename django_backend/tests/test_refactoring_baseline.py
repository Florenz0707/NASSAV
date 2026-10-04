"""R0 failure timing contracts; uv run pytest tests/test_refactoring_baseline.py -v."""

from unittest.mock import Mock

import pytest

from nassav import services, tasks
from nassav.download_persistence import download_persistence
from nassav.resource_service import ResourceService
from nassav.scraper import AVDownloadInfo
from nassav.signals import resource_added


@pytest.fixture
def download_runtime(monkeypatch):
    trace = []
    for name in (
        "create_task_lock",
        "update_task_state_in_queue",
        "remove_task_from_queue",
        "remove_task_lock",
        "release_global_download_lock",
        "remove_task_progress",
    ):
        monkeypatch.setattr(
            tasks, name, lambda *args, _name=name, **kwargs: trace.append(_name)
        )
    monkeypatch.setattr(tasks, "wait_for_global_download_lock", lambda **kwargs: True)
    monkeypatch.setattr(tasks, "get_full_task_queue", lambda: {})
    monkeypatch.setattr(
        tasks, "notify_task_update", lambda name, data: trace.append(name)
    )
    monkeypatch.setattr(
        services.video_download_service, "download_video", lambda *a, **k: True
    )
    return trace


@pytest.mark.parametrize("persistence_fails", [False, True])
def test_download_success_precedes_persistence_and_failure_remains_success(
    monkeypatch, download_runtime, persistence_fails
):
    """Freeze existing semantics; correcting them requires a separate change."""

    def persist(avid):
        download_runtime.append("persist")
        if persistence_fails:
            raise RuntimeError("isolated write failure")

    monkeypatch.setattr(download_persistence, "mark_completed", persist)
    result = tasks.download_video_task.apply(
        args=("r0-001",), task_id="r0-download"
    ).get()
    assert result == {"status": "success", "avid": "R0-001", "message": "下载完成"}
    assert download_runtime.index("task_completed") < download_runtime.index("persist")
    assert "task_failed" not in download_runtime
    assert download_runtime[-4:] == [
        "release_global_download_lock",
        "remove_task_lock",
        "remove_task_progress",
        "queue_status",
    ]


@pytest.mark.django_db
def test_resource_persistence_failure_leaves_html_without_added_event(
    settings, tmp_path
):
    settings.COVER_DIR = tmp_path
    source = Mock()
    source.get_info_from_any_source.return_value = (
        AVDownloadInfo(avid="R0-002", source_title="Example", m3u8="https://test/a"),
        None,
        "<html>isolated page</html>",
        {},
    )
    persistence = Mock()
    persistence.save.side_effect = RuntimeError("isolated write failure")
    service = ResourceService(source, Mock(), Mock(), persistence=persistence)
    receiver = Mock()
    resource_added.connect(receiver, weak=False)
    try:
        with pytest.raises(RuntimeError, match="isolated write failure"):
            service.add_resource(
                "r0-002", scrape=False, download_cover=False, submit_translate=False
            )
    finally:
        resource_added.disconnect(receiver)
    assert (tmp_path / "R0-002.html").read_text() == "<html>isolated page</html>"
    persistence.save.assert_called_once()
    receiver.assert_not_called()
