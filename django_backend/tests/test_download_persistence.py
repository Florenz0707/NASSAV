"""The download task's ORM boundary preserves its existing file-state semantics."""

import pytest

from nassav.download_persistence import DjangoDownloadPersistence


@pytest.mark.django_db
def test_completed_download_records_file_size_and_time(
    resource_factory, settings, tmp_path
):
    settings.VIDEO_DIR = tmp_path
    resource = resource_factory(avid="DL-001")
    (tmp_path / "DL-001.mp4").write_bytes(b"video")

    DjangoDownloadPersistence().mark_completed("DL-001")

    resource.refresh_from_db()
    assert resource.file_exists is True
    assert resource.file_size == 5
    assert resource.video_saved_at is not None


@pytest.mark.django_db
def test_missing_file_clears_completed_metadata(resource_factory, settings, tmp_path):
    settings.VIDEO_DIR = tmp_path
    resource = resource_factory(avid="DL-002", file_exists=True, file_size=99)

    DjangoDownloadPersistence().mark_completed("DL-002")

    resource.refresh_from_db()
    assert resource.file_exists is False
    assert resource.file_size is None
    assert resource.video_saved_at is None


@pytest.mark.django_db
def test_failed_download_keeps_existing_size_for_retry(resource_factory):
    resource = resource_factory(avid="DL-003", file_exists=True, file_size=99)

    DjangoDownloadPersistence().mark_failed("DL-003")

    resource.refresh_from_db()
    assert resource.file_exists is False
    assert resource.file_size == 99


@pytest.mark.django_db
def test_download_task_keeps_progress_event_and_task_name(
    monkeypatch, resource_factory, settings, tmp_path
):
    from nassav import tasks
    from nassav.services import video_download_service

    settings.VIDEO_DIR = tmp_path
    resource = resource_factory(avid="DL-004")
    events = []
    progress = []
    monkeypatch.setattr(tasks, "create_task_lock", lambda *args: None)
    monkeypatch.setattr(tasks, "wait_for_global_download_lock", lambda **kwargs: True)
    monkeypatch.setattr(tasks, "update_task_state_in_queue", lambda *args: None)
    monkeypatch.setattr(tasks, "remove_task_from_queue", lambda *args: None)
    monkeypatch.setattr(tasks, "remove_task_lock", lambda *args: None)
    monkeypatch.setattr(tasks, "release_global_download_lock", lambda: None)
    monkeypatch.setattr(tasks, "remove_task_progress", lambda *args: None)
    monkeypatch.setattr(tasks, "get_full_task_queue", lambda: [])
    monkeypatch.setattr(
        tasks, "notify_task_update", lambda name, data: events.append((name, data))
    )
    monkeypatch.setattr(
        tasks, "set_task_progress", lambda *args, **kwargs: progress.append(args)
    )

    def download(avid, progress_callback):
        (tmp_path / f"{avid}.mp4").write_bytes(b"video")
        progress_callback(100, "1 MB/s", "0s")
        return True

    monkeypatch.setattr(video_download_service, "download_video", download)

    assert tasks.download_video_task.name == "nassav.tasks.download_video_task"
    result = tasks.download_video_task.apply(
        args=("dl-004",), task_id="test-download"
    ).get()

    resource.refresh_from_db()
    assert result == {"status": "success", "avid": "DL-004", "message": "下载完成"}
    assert progress[0][0:2] == ("DL-004", 100)
    assert any(
        name == "progress_update" and data["percent"] == 100 for name, data in events
    )
    assert any(name == "task_completed" for name, _ in events)
    assert resource.file_exists is True
