"""F1 deletion contracts use only pytest's database and tmp_path resources."""

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
from nassav.models import AVResource
from nassav.resource_deletion import ResourceDeletionRepository, ResourceDeletionService


def isolate_paths(settings, tmp_path):
    settings.COVER_DIR = tmp_path / "cover"
    settings.THUMBNAIL_DIR = tmp_path / "thumbnails"
    settings.VIDEO_DIR = tmp_path / "video"
    settings.RESOURCE_BACKUP_DIR = tmp_path / "backup"


def make_files(settings, avid):
    paths = {
        "cover": Path(settings.COVER_DIR) / f"{avid}.jpg",
        "thumbnail": Path(settings.THUMBNAIL_DIR) / "small" / f"{avid}.jpg",
        "video": Path(settings.VIDEO_DIR) / f"{avid}.mp4",
        "backup": Path(settings.RESOURCE_BACKUP_DIR) / avid / "record.json",
    }
    for path in paths.values():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"isolated-test")
    return paths


@pytest.mark.django_db
@pytest.mark.parametrize("endpoint", ["single", "batch"])
def test_full_delete_has_same_files_and_result(
    api_client, resource_factory, settings, tmp_path, endpoint
):
    isolate_paths(settings, tmp_path)
    avid = f"F1-{endpoint.upper()}"
    resource_factory(avid=avid)
    paths = make_files(settings, avid)
    if endpoint == "single":
        response = api_client.delete(f"/nassav/api/resource/{avid}")
        result = response.json()["data"]
    else:
        response = api_client.post(
            "/nassav/api/resources/batch",
            {"actions": [{"action": "delete-all", "avid": avid}]},
            format="json",
        )
        result = response.json()["data"]["results"][0]
    assert response.status_code == 200
    assert result.get("code", 200) == 200
    assert set(result["deleted_files"]) == {
        f"{avid}.jpg",
        f"thumbnail/small/{avid}.jpg",
        f"{avid}.mp4",
        "record.json",
    }
    assert not AVResource.objects.filter(avid=avid).exists()
    assert all(not path.exists() for path in paths.values())


@pytest.mark.django_db
@pytest.mark.parametrize("endpoint", ["single", "batch"])
@pytest.mark.parametrize("state", ["database", "file", "thumbnail"])
def test_partial_existing_state_can_be_deleted(
    api_client, resource_factory, settings, tmp_path, endpoint, state
):
    isolate_paths(settings, tmp_path)
    avid = f"F1-{endpoint.upper()}-{state.upper()}"
    if state == "database":
        resource_factory(avid=avid)
    else:
        path = (
            Path(settings.COVER_DIR) / f"{avid}.jpg"
            if state == "file"
            else Path(settings.THUMBNAIL_DIR) / "small" / f"{avid}.jpg"
        )
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"isolated-test")
    if endpoint == "single":
        response = api_client.delete(f"/nassav/api/resource/{avid}")
        retry = api_client.delete(f"/nassav/api/resource/{avid}")
        assert retry.status_code == 404
    else:
        payload = {"actions": [{"action": "delete", "avid": avid}]}
        response = api_client.post(
            "/nassav/api/resources/batch", payload, format="json"
        )
        retry = api_client.post("/nassav/api/resources/batch", payload, format="json")
        assert retry.json()["data"]["results"][0]["code"] == 404
    assert response.status_code == 200
    assert not AVResource.objects.filter(avid=avid).exists()
    if state != "database":
        assert not path.exists()


@pytest.mark.django_db
def test_unlink_failure_reports_partial_and_other_batch_item_succeeds(
    api_client, resource_factory, settings, tmp_path, monkeypatch
):
    isolate_paths(settings, tmp_path)
    bad, good = "F1-BAD", "F1-GOOD"
    resource_factory(avid=bad)
    resource_factory(avid=good)
    bad_cover = make_files(settings, bad)["cover"]
    good_cover = make_files(settings, good)["cover"]
    original_unlink = Path.unlink

    def fail_one(path, *args, **kwargs):
        if path == bad_cover:
            raise PermissionError("secret-path-must-not-leak")
        return original_unlink(path, *args, **kwargs)

    monkeypatch.setattr(Path, "unlink", fail_one)
    response = api_client.post(
        "/nassav/api/resources/batch",
        {
            "actions": [
                {"action": "delete-all", "avid": bad},
                {"action": "delete-all", "avid": good},
            ]
        },
        format="json",
    )
    items = response.json()["data"]["results"]
    assert response.status_code == 200
    assert [item["code"] for item in items] == [500, 200]
    assert "secret-path" not in items[0]["message"]
    assert items[0]["retryable"] is True
    assert bad_cover.exists() and AVResource.objects.filter(avid=bad).exists()
    assert not good_cover.exists() and not AVResource.objects.filter(avid=good).exists()


@pytest.mark.django_db
def test_backup_failure_can_be_retried(
    api_client, resource_factory, settings, tmp_path, monkeypatch
):
    isolate_paths(settings, tmp_path)
    avid = "F1-BACKUP"
    resource_factory(avid=avid)
    paths = make_files(settings, avid)
    import nassav.resource_deletion as deletion

    original_rmtree = deletion.shutil.rmtree

    def fail_backup(path):
        if path == paths["backup"].parent:
            raise PermissionError("private-directory")
        return original_rmtree(path)

    monkeypatch.setattr(deletion.shutil, "rmtree", fail_backup)
    response = api_client.delete(f"/nassav/api/resource/{avid}")
    assert response.status_code == 500
    assert response.json()["data"]["failed_stage"] == "files"
    assert paths["backup"].exists()
    assert AVResource.objects.filter(avid=avid).exists()
    monkeypatch.setattr(deletion.shutil, "rmtree", original_rmtree)
    retry = api_client.delete(f"/nassav/api/resource/{avid}")
    assert retry.status_code == 200
    assert not paths["backup"].exists()


@pytest.mark.django_db
def test_database_failure_can_be_retried_after_files_removed(
    api_client, resource_factory, settings, tmp_path, monkeypatch
):
    isolate_paths(settings, tmp_path)
    avid = "F1-DBFAIL"
    resource_factory(avid=avid)
    paths = make_files(settings, avid)
    import nassav.resource_deletion as deletion

    original_delete = deletion.DjangoResourceDeletionRepository.delete

    def fail_delete(self, resource):
        raise RuntimeError("private-database-path")

    monkeypatch.setattr(
        deletion.DjangoResourceDeletionRepository, "delete", fail_delete
    )
    response = api_client.delete(f"/nassav/api/resource/{avid}")
    assert response.status_code == 500
    assert response.json()["data"]["failed_stage"] == "database"
    assert "private-" not in response.json()["message"]
    assert AVResource.objects.filter(avid=avid).exists()
    assert all(not path.exists() for path in paths.values())
    monkeypatch.setattr(
        deletion.DjangoResourceDeletionRepository, "delete", original_delete
    )
    assert api_client.delete(f"/nassav/api/resource/{avid}").status_code == 200
    assert not AVResource.objects.filter(avid=avid).exists()


@pytest.mark.django_db
def test_video_state_failure_can_be_retried_without_file(
    api_client, resource_factory, settings, tmp_path, monkeypatch
):
    isolate_paths(settings, tmp_path)
    avid = "F1-VIDEO"
    resource_factory(avid=avid, file_exists=True, file_size=9)
    path = Path(settings.VIDEO_DIR) / f"{avid}.mp4"
    path.parent.mkdir(parents=True)
    path.write_bytes(b"123456789")
    import nassav.resource_deletion as deletion

    original_update = deletion.DjangoResourceDeletionRepository.clear_video_state

    def fail_update(self, avid):
        raise RuntimeError("private-database-path")

    monkeypatch.setattr(
        deletion.DjangoResourceDeletionRepository, "clear_video_state", fail_update
    )
    response = api_client.post(
        "/nassav/api/resources/batch",
        {"actions": [{"action": "delete-video", "avid": avid}]},
        format="json",
    )
    assert response.json()["data"]["results"][0]["code"] == 500
    assert not path.exists()
    monkeypatch.setattr(
        deletion.DjangoResourceDeletionRepository, "clear_video_state", original_update
    )
    retry = api_client.delete(f"/nassav/api/downloads/{avid}")
    assert retry.status_code == 200
    assert retry.json()["data"]["deleted_file"] is None
    resource = AVResource.objects.get(avid=avid)
    assert resource.file_exists is False and resource.file_size is None


@pytest.mark.django_db
def test_invalid_identifier_does_not_escape_resource_dir(
    api_client, settings, tmp_path
):
    isolate_paths(settings, tmp_path)
    response = api_client.post(
        "/nassav/api/resources/batch",
        {"actions": [{"action": "delete-all", "avid": "../OTHER"}]},
        format="json",
    )
    assert response.json()["data"]["results"][0]["code"] == 400
    assert not (tmp_path / "OTHER").exists()


class EmptyRepository(ResourceDeletionRepository):
    def get(self, avid):
        return None

    def delete(self, resource):
        raise AssertionError("no resource")

    def clear_video_state(self, avid):
        raise AssertionError("no resource")


def test_concurrent_same_avid_removes_file_once(settings, tmp_path):
    isolate_paths(settings, tmp_path)
    path = Path(settings.COVER_DIR) / "F1-CONCURRENT.jpg"
    path.parent.mkdir(parents=True)
    path.write_bytes(b"isolated-test")
    service = ResourceDeletionService(EmptyRepository())
    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(service.delete_resource, ["F1-CONCURRENT"] * 2))
    assert sorted(outcome.found for outcome in outcomes) == [False, True]
    assert not path.exists()


@pytest.mark.django_db
def test_legacy_batch_add_and_refresh_keep_sync_contract(
    api_client, resource_factory, monkeypatch
):
    from nassav.legacy_batch import resource_service

    existing = resource_factory(avid="F1-EXISTING")
    calls = []

    def add(avid, source):
        calls.append(("add", avid, source))
        return {"resource": {"avid": avid}}

    def refresh(avid, *, scrape, download_cover):
        calls.append(("refresh", avid, scrape, download_cover))
        return {"cover_saved": False, "metadata_saved": True, "scraped": True}

    monkeypatch.setattr(resource_service, "add_resource", add)
    monkeypatch.setattr(resource_service, "refresh_resource", refresh)
    response = api_client.post(
        "/nassav/api/resources/batch",
        {
            "actions": [
                {"action": "add", "avid": existing.avid},
                {"action": "add", "avid": "F1-NEW", "source": "test"},
                {"action": "refresh", "avid": existing.avid},
                {"action": "refresh", "avid": "F1-MISSING"},
            ]
        },
        format="json",
    )
    assert response.status_code == 200
    items = response.json()["data"]["results"]
    assert [item["code"] for item in items] == [200, 201, 200, 404]
    assert items[1]["resource"] == {"avid": "F1-NEW"}
    assert items[2]["metadata_refreshed"] is True
    assert calls == [
        ("add", "F1-NEW", "test"),
        ("refresh", "F1-EXISTING", True, True),
    ]


@pytest.mark.django_db
def test_batch_rejects_malformed_items_without_stopping_following_item(
    api_client, settings, tmp_path
):
    isolate_paths(settings, tmp_path)
    path = Path(settings.COVER_DIR) / "F1-VALID.jpg"
    path.parent.mkdir(parents=True)
    path.write_bytes(b"isolated-test")
    response = api_client.post(
        "/nassav/api/resources/batch",
        {
            "actions": [
                None,
                {"action": "delete-all", "avid": ["bad"]},
                {"action": "delete-all", "avid": "F1-VALID"},
            ]
        },
        format="json",
    )
    assert [item["code"] for item in response.json()["data"]["results"]] == [
        400,
        400,
        200,
    ]
    assert not path.exists()


@pytest.mark.django_db
def test_delete_uses_default_thumbnail_directory_when_setting_absent(
    api_client, resource_factory, settings, tmp_path, monkeypatch
):
    avid = "F1-NO-THUMBNAIL-SETTING"
    settings.COVER_DIR = tmp_path / "cover"
    settings.VIDEO_DIR = tmp_path / "video"
    settings.RESOURCE_BACKUP_DIR = tmp_path / "backup"
    monkeypatch.delattr(settings, "THUMBNAIL_DIR", raising=False)
    thumbnail = settings.COVER_DIR / "thumbnails" / "medium" / f"{avid}.jpg"
    thumbnail.parent.mkdir(parents=True)
    thumbnail.write_bytes(b"isolated-test")
    resource_factory(avid=avid)

    response = api_client.delete(f"/nassav/api/resource/{avid}")

    assert response.status_code == 200
    assert not thumbnail.exists()
    assert not AVResource.objects.filter(avid=avid).exists()
