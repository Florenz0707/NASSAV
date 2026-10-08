"""Opt-in fixed local binary integration; media and DB are isolated fixtures."""

import os
import time
from functools import partial
from threading import Thread
from types import SimpleNamespace
from urllib.parse import urlsplit

import pytest
from django.db import close_old_connections


@pytest.fixture(scope="session")
def django_db_modify_db_settings(
    django_db_modify_db_settings_parallel_suffix, tmp_path_factory
):
    # Shared in-memory SQLite fails immediately on cross-thread table locks.
    # Real CLI callbacks/watchdog use separate connections, so use a temporary file.
    from django.conf import settings

    settings.DATABASES["default"].setdefault("TEST", {})["NAME"] = str(
        tmp_path_factory.mktemp("cli-database") / "test.sqlite3"
    )


@pytest.mark.django_db(transaction=True)
@pytest.mark.skipif(
    not os.environ.get("NASSAV_LOCAL_DOWNLOAD_BINARY"),
    reason="Fixed local CLI integration opt-in",
)
@pytest.mark.parametrize("encrypted", [False, True])
@pytest.mark.parametrize("segment_count", [12, 240])
def test_real_cli_pause_resume_produces_complete_video(
    tmp_path, encrypted, segment_count
):
    from scripts.probe_task_download_control import (
        generate_media,
        media_server,
        decoded_hash,
    )
    from nassav.controlled_download import ControlledDownload
    from nassav.download_resume import HLSResumeGuard
    from nassav.m3u8downloader import N_m3u8DL_RE
    from nassav.task_assets import TaskAssets
    from nassav.task_records import DjangoTaskRecords
    from nassav.task_processes import group_writers
    from nassav.task_models import TaskAttempt
    from tests.test_controlled_download import Lease
    from uuid import uuid4
    from pathlib import Path

    media = tmp_path / "media"
    generate_media(media, segment_time=24 / segment_count)
    expected = decoded_hash(media / "index.m3u8")
    if encrypted:
        from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
        from cryptography.hazmat.primitives.padding import PKCS7

        key = b"0123456789abcdef"
        (media / "key.bin").write_bytes(key)
        playlist = (
            (media / "index.m3u8")
            .read_text()
            .replace(
                "#EXTM3U\n", '#EXTM3U\n#EXT-X-KEY:METHOD=AES-128,URI="key.bin"\n', 1
            )
        )
        (media / "index.m3u8").write_text(playlist)
        for index, file in enumerate(sorted(media.glob("*.ts"))):
            padder = PKCS7(128).padder()
            padded = padder.update(file.read_bytes()) + padder.finalize()
            encryptor = Cipher(
                algorithms.AES(key), modes.CBC(index.to_bytes(16, "big"))
            ).encryptor()
            file.write_bytes(encryptor.update(padded) + encryptor.finalize())
    records = DjangoTaskRecords()
    job, _ = records.create("download", "LOCAL-1", owner_id=None, action="download")
    assets = TaskAssets(
        {root: tmp_path / root for root in ["cover", "avatar", "video"]}, records
    )
    binary = Path(os.environ["NASSAV_LOCAL_DOWNLOAD_BINARY"])
    assert binary.is_file()
    native = N_m3u8DL_RE()
    native.tool_path = str(binary)
    downloader = SimpleNamespace(
        download=partial(native.download, thread_count=1, retry_count=0),
        ensure_mp4=native.ensure_mp4,
    )
    outcomes, failures, saved = [], [], []
    with media_server(tmp_path) as (base, counts):
        resolver = SimpleNamespace(
            resolve=lambda avid, **kwargs: SimpleNamespace(
                info=SimpleNamespace(m3u8=f"{base}/media/index.m3u8"),
                domain="localhost",
            )
        )

        def local_fetch(url, headers, check):
            check()
            assert not urlsplit(url).path.endswith(".ts"), "guard refetched a segment"
            return (tmp_path / urlsplit(url).path.lstrip("/")).read_bytes()

        guard = HLSResumeGuard(fetch=local_fetch)
        lease = Lease()
        runner = ControlledDownload(
            records, assets, resolver, downloader, lease, saved.append, guard=guard
        )

        def execute():
            try:
                outcomes.append(runner.run(job["job_id"], job["task_id"]))
            except BaseException as error:
                failures.append(error)
            finally:
                close_old_connections()

        thread = Thread(target=execute)
        thread.start()
        directory = assets.roots["video"] / ".tasks" / job["job_id"] / "download"
        pause_count = 151 if segment_count == 240 else 4
        deadline = time.monotonic() + 45
        try:
            while len(list(directory.glob("temp/LOCAL-1/*/*.ts"))) < pause_count:
                if not thread.is_alive() or time.monotonic() >= deadline:
                    pytest.fail(
                        f"CLI did not reach pause checkpoint: {failures}, {outcomes}"
                    )
                time.sleep(0.02)
            current = records.get(job["job_id"])
            records.request(
                job["job_id"],
                "pause",
                expected_version=current["version"],
                request_id=str(uuid4()),
                actor_id=None,
                allow_all=True,
            )
        finally:
            thread.join(timeout=10)
        assert not thread.is_alive() and not failures
        assert outcomes[0]["status"] == "paused"
        assert lease.closed and not lease.slot
        identity = TaskAttempt.objects.get(pk=job["task_id"]).execution_identity
        assert not group_writers(identity["pgid"])
        paused = records.get(job["job_id"])
        assert len(paused["checkpoint"]["download"]["segments"]) >= pause_count
        cached_indices = {
            int(Path(relative).stem)
            for relative in paused["checkpoint"]["download"]["segments"]
        }
        before_resume = counts.copy()
        resumed = records.request(
            job["job_id"],
            "resume",
            expected_version=paused["version"],
            request_id=str(uuid4()),
            actor_id=None,
            allow_all=True,
        )
        runner.lease = Lease()
        result = runner.run(job["job_id"], resumed["task_id"])
        assert result["status"] == "succeeded", result
        assert saved == ["LOCAL-1"]
        for index in cached_indices:
            path = f"/media/segment{index:03d}.ts"
            assert counts[path] == before_resume[path], "CLI refetched complete cache"
        assert decoded_hash(assets.roots["video"] / "LOCAL-1.mp4") == expected
        assert not (assets.roots["video"] / ".tasks" / job["job_id"]).exists()
