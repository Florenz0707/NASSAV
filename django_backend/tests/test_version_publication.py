"""Real encrypted authority, ORM fences and journaled files; no live websites."""

from uuid import uuid4

import pytest
from django.contrib.auth import get_user_model
from PIL import Image

from nassav.account_models import UserAccount
from nassav.composition import build_account_management
from nassav.credential_crypto import CredentialKeyring, CredentialUnavailable
from nassav.credential_records import DjangoCredentialRecords
from nassav.library_models import UserLibraryEntry, ResourcePoolEntry
from nassav.models import AVResource
from nassav.page_fetching.proxy_server import ProxySessionCapabilities
from nassav.scoped_source_context import CredentialSourceContext
from nassav.shared_execution_records import (
    DjangoSharedExecutionRecords,
    SharedPublicationRejected,
)
from nassav.shared_work import SharedOperations
from nassav.shared_work_records import DjangoOperationRecords
from nassav.shared_work_models import SharedWork, UserOperation
from nassav.resource_version_publication import VersionPublications
from nassav.resource_version_models import ResourceVersion, ResourceVersionPointer
from nassav.task_assets import TaskAssets, AssetPromotion
from nassav.task_models import TaskAttempt
from nassav.task_control_rules import TaskExecutionInvalid

pytestmark = pytest.mark.django_db


@pytest.fixture
def environment(tmp_path):
    users = [
        get_user_model().objects.create_user(username=name)
        for name in ("publish-a", "publish-b")
    ]
    for index, user in enumerate(users):
        UserAccount.objects.create(user=user, role="admin" if index == 0 else "user")
    vault = DjangoCredentialRecords(
        CredentialKeyring("k1", {"k1": b"a" * 32}), {"jable": "jable.tv"}
    )
    roots = {kind: tmp_path / kind for kind in ("cover", "avatar", "video")}
    return users, vault, roots


def context(vault, user=None):
    return CredentialSourceContext(
        lambda: vault,
        "jable",
        user_id=user.pk if user else None,
        egress_profile="direct",
        browser_context="fixture-v1",
        capabilities=ProxySessionCapabilities(),
    )


def operation(user, ctx, records, *, request_id=None, action="add", kind="scrape"):
    binding = ctx.work_binding
    return SharedOperations(records).submit(
        user.pk,
        {
            "avid": "PUB-001",
            "kind": kind,
            "action": action,
            "source": "jable",
            "request_id": str(request_id or uuid4()),
        },
        access_scope=binding["access_scope"],
        credential_refs=binding["credential_refs"],
        context_revision=binding["context_revision"],
    )


def runtime(ctx, roots):
    tasks = DjangoSharedExecutionRecords(ctx)
    publication = VersionPublications(tasks)
    operations = DjangoOperationRecords(
        tasks, publication=publication, allow_private=True
    )
    return tasks, publication, operations, TaskAssets(roots, tasks)


def claim(tasks, op):
    work = SharedWork.objects.get(subscriptions__operation_id=op["operation_id"])
    attempt = TaskAttempt.objects.get(job=work.job)
    return tasks.claim(
        str(work.job_id), str(attempt.pk), kind=work.spec["kind"], role="main"
    )


def staged_cover(assets, token):
    def write(path):
        Image.new("RGB", (4, 4), "red").save(path, "JPEG")
        return True

    return assets.stage(token, "cover", "cover.jpg", "cover", write)


def publish(assets, publication, token, version, artifact, *, title="shared title"):
    target = publication.target(version, "cover.jpg")
    result = assets.commit(
        token,
        [AssetPromotion(artifact, target)],
        lambda: publication.publish(
            token, version, {"avid": "PUB-001", "source_title": title}
        ),
        resource_saved=True,
    )
    return result, target


def test_public_publication_activates_two_private_holds_once_and_keeps_canonical_neutral(
    environment,
):
    users, vault, roots = environment
    ctx = context(vault)
    tasks, publication, records, assets = runtime(ctx, roots)
    first, second = [operation(user, ctx, records) for user in users]
    token = claim(tasks, first)
    version = publication.prepare(token)
    assert publication.prepare(token) == version
    artifact = staged_cover(assets, token)
    row, target = publish(assets, publication, token, version, artifact)
    tasks.finish(token, "succeeded")
    for user, op in zip(users, (first, second)):
        result = records.project(user.pk, op["operation_id"])
        assert result["state"] == "succeeded"
        assert records.project(user.pk, op["operation_id"]) == result
    assert (
        UserLibraryEntry.objects.filter(state="active", current_version=row).count()
        == 2
    )
    assert (roots["cover"] / target).is_file()
    assert row.manifest[0]["path"] == target
    assert not AVResource.objects.get().source_title
    assert not AVResource.objects.get().m3u8
    assert ResourceVersion.objects.filter(state="ready").count() == 1


def test_cancelled_user_is_not_rejoined_by_completed_shared_publication(environment):
    users, vault, roots = environment
    ctx = context(vault)
    tasks, publication, records, assets = runtime(ctx, roots)
    first, second = [operation(user, ctx, records) for user in users]
    token = claim(tasks, first)
    version = publication.prepare(token)
    SharedOperations(records).cancel(
        users[0].pk, first["operation_id"], expected_version=1, request_id=uuid4()
    )
    publish(assets, publication, token, version, staged_cover(assets, token))
    tasks.finish(token, "succeeded")
    assert records.project(users[0].pk, first["operation_id"])["state"] == "cancelled"
    assert records.project(users[1].pk, second["operation_id"])["state"] == "succeeded"
    assert not UserLibraryEntry.objects.filter(user=users[0]).exists()


def test_private_version_stays_out_of_canonical_data_and_other_users_cannot_join(
    environment,
):
    users, vault, roots = environment
    vault.write(
        users[0].pk,
        "jable",
        {
            "expected_version": 0,
            "cookie": "account_session=fixture-a",
            "user_agent": "fixture-UA",
        },
    )
    ctx = context(vault, users[0])
    tasks, publication, records, assets = runtime(ctx, roots)
    first = operation(users[0], ctx, records)
    with pytest.raises(PermissionError):
        operation(users[1], ctx, records)
    token = claim(tasks, first)
    version = publication.prepare(token)
    row, _ = publish(
        assets,
        publication,
        token,
        version,
        staged_cover(assets, token),
        title="private display title",
    )
    tasks.finish(token, "succeeded")
    assert records.project(users[0].pk, first["operation_id"])["state"] == "succeeded"
    assert row.owner_id == users[0].pk
    assert row.metadata["source_title"] == "private display title"
    canonical = AVResource.objects.get()
    assert not canonical.source_title and not canonical.source and not canonical.m3u8
    assert not canonical.metadata
    assert not canonical.actors.exists() and not canonical.genres.exists()
    assert UserOperation.objects.count() == 1


def test_manual_credential_change_prevents_late_file_and_db_publication(environment):
    users, vault, roots = environment
    vault.write(
        users[0].pk,
        "jable",
        {
            "expected_version": 0,
            "cookie": "account_session=fixture-a",
            "user_agent": "fixture-UA",
        },
    )
    ctx = context(vault, users[0])
    tasks, publication, records, assets = runtime(ctx, roots)
    first = operation(users[0], ctx, records)
    token = claim(tasks, first)
    version = publication.prepare(token)
    artifact = staged_cover(assets, token)
    vault.write(
        users[0].pk,
        "jable",
        {
            "expected_version": 1,
            "cookie": "account_session=fixture-new",
            "user_agent": "fixture-UA",
        },
    )
    with pytest.raises(CredentialUnavailable):
        publish(assets, publication, token, version, artifact)
    assert ResourceVersion.objects.get().state == "staging"
    assert ResourceVersionPointer.objects.get().current_id is None
    assert not (roots["cover"] / publication.target(version, "cover.jpg")).exists()
    assert not AVResource.objects.exists()


def test_public_work_does_not_depend_on_original_user_remaining_active(environment):
    users, vault, roots = environment
    ctx = context(vault)
    tasks, publication, records, assets = runtime(ctx, roots)
    first, second = [operation(user, ctx, records) for user in users]
    token = claim(tasks, first)
    version = publication.prepare(token)
    UserAccount.objects.filter(user=users[1]).update(role="admin")
    build_account_management().execute(
        users[1].pk,
        "update",
        users[0].pk,
        {
            "expected_version": 1,
            "request_id": str(uuid4()),
            "reason": "user_request",
            "is_active": False,
        },
    )
    publish(assets, publication, token, version, staged_cover(assets, token))
    tasks.finish(token, "succeeded")
    assert records.project(users[1].pk, second["operation_id"])["state"] == "succeeded"
    assert UserOperation.objects.get(user=users[0]).state == "cancelled"


def test_failed_commit_rolls_back_files_pointer_and_never_activates_hold(environment):
    users, vault, roots = environment
    ctx = context(vault)
    tasks, publication, records, assets = runtime(ctx, roots)
    first = operation(users[0], ctx, records)
    token = claim(tasks, first)
    version = publication.prepare(token)
    artifact = staged_cover(assets, token)
    target = publication.target(version, "cover.jpg")

    def fail():
        publication.publish(
            token, version, {"avid": "PUB-001", "source_title": "not committed"}
        )
        raise RuntimeError("Injected short commit failure")

    with pytest.raises(RuntimeError):
        assets.commit(token, [AssetPromotion(artifact, target)], fail)
    assert not (roots["cover"] / target).exists()
    assert ResourceVersion.objects.get().state == "staging"
    assert ResourceVersionPointer.objects.get().current_id is None
    assert UserLibraryEntry.objects.get().state == "pending"


def test_published_metadata_rejects_source_urls_and_pending_translation(environment):
    users, vault, roots = environment
    ctx = context(vault)
    tasks, publication, records, assets = runtime(ctx, roots)
    first = operation(users[0], ctx, records)
    token = claim(tasks, first)
    version = publication.prepare(token)
    for payload in (
        {"avid": "PUB-001", "m3u8": "https://secret.invalid/stream"},
        {"avid": "PUB-001", "translation_status": "translating"},
    ):
        with pytest.raises(ValueError):
            assets.commit(
                token, [], lambda: publication.publish(token, version, payload)
            )
    assert ResourceVersion.objects.get().state == "staging"


def test_wrong_source_actor_or_pool_generation_cannot_claim_or_publish(environment):
    users, vault, roots = environment
    ctx = context(
        vault, users[0]
    )  # Anonymous user-bound context is not a system work identity.
    tasks, _, records, _ = runtime(ctx, roots)
    first = operation(users[0], ctx, records)
    with pytest.raises(TaskExecutionInvalid):
        claim(tasks, first)
    system_ctx = context(vault)
    tasks, publication, records, assets = runtime(system_ctx, roots)
    token = claim(tasks, first)
    version = publication.prepare(token)
    artifact = staged_cover(assets, token)
    ResourcePoolEntry.objects.update(lifetime_generation=2)
    with pytest.raises(SharedPublicationRejected):
        publish(assets, publication, token, version, artifact)
    assert ResourceVersion.objects.get().state == "staging"


def test_shared_assets_cannot_overwrite_a_legacy_or_other_version_target(environment):
    users, vault, roots = environment
    ctx = context(vault)
    tasks, publication, records, assets = runtime(ctx, roots)
    first = operation(users[0], ctx, records)
    token = claim(tasks, first)
    publication.prepare(token)
    artifact = staged_cover(assets, token)
    for target in ("PUB-001.jpg", f"versions/{uuid4()}/cover.jpg"):
        with pytest.raises(SharedPublicationRejected):
            assets.commit(token, [AssetPromotion(artifact, target)], lambda: None)
        assert not (roots["cover"] / target).exists()
    assert ResourceVersion.objects.get().state == "staging"


def test_newer_pointer_rejects_late_refresh_and_retains_old_held_version(environment):
    users, vault, roots = environment
    ctx = context(vault)
    tasks, publication, records, assets = runtime(ctx, roots)
    initial = [operation(user, ctx, records) for user in users]
    token = claim(tasks, initial[0])
    old = publication.prepare(token)
    old_row, old_target = publish(
        assets, publication, token, old, staged_cover(assets, token)
    )
    tasks.finish(token, "succeeded")
    for user, op in zip(users, initial):
        records.project(user.pk, op["operation_id"])
    older_op = operation(users[0], ctx, records, action="refresh")
    older_token = claim(tasks, older_op)
    older = publication.prepare(older_token)
    older_artifact = staged_cover(assets, older_token)
    new_ctx = context(vault)
    new_ctx.egress_profile = "new-route-fixture"
    new_tasks, new_publication, new_records, new_assets = runtime(new_ctx, roots)
    newer_op = operation(users[1], new_ctx, new_records, action="refresh")
    newer_token = claim(new_tasks, newer_op)
    newer = new_publication.prepare(newer_token)
    newer_row, newer_target = publish(
        new_assets,
        new_publication,
        newer_token,
        newer,
        staged_cover(new_assets, newer_token),
        title="newer title",
    )
    new_tasks.finish(newer_token, "succeeded")
    new_records.project(users[1].pk, newer_op["operation_id"])
    with pytest.raises(SharedPublicationRejected):
        publish(
            assets,
            publication,
            older_token,
            older,
            older_artifact,
            title="late older title",
        )
    tasks.finish(older_token, "failed")
    records.project(users[0].pk, older_op["operation_id"])
    assert ResourceVersionPointer.objects.get().current_id == newer_row.pk
    assert UserLibraryEntry.objects.get(user=users[0]).current_version_id == old_row.pk
    assert (roots["cover"] / old_target).exists() and (
        roots["cover"] / newer_target
    ).exists()
    assert not (roots["cover"] / publication.target(older, "cover.jpg")).exists()


@pytest.mark.django_db(transaction=True)
def test_concurrent_publishers_have_one_pointer_winner_and_no_partial_loser(
    environment,
):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier
    from django.db import close_old_connections

    users, vault, roots = environment
    runners = []
    for index, user in enumerate(users):
        ctx = context(vault)
        ctx.egress_profile = f"route-{index}"
        tasks, publication, records, assets = runtime(ctx, roots)
        op = operation(user, ctx, records)
        token = claim(tasks, op)
        candidate = publication.prepare(token)
        artifact = staged_cover(assets, token)
        runners.append((tasks, publication, assets, token, candidate, artifact))
    barrier = Barrier(2)

    def run(args):
        tasks, publication, assets, token, candidate, artifact = args
        close_old_connections()
        try:
            barrier.wait(timeout=10)
            try:
                publish(assets, publication, token, candidate, artifact)
            except SharedPublicationRejected:
                tasks.finish(token, "failed")
                return "failed", candidate
            else:
                tasks.finish(token, "succeeded")
                return "succeeded", candidate
        finally:
            close_old_connections()

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(run, runners))
    assert sorted(state for state, _ in results) == ["failed", "succeeded"]
    assert ResourceVersion.objects.filter(state="ready").count() == 1
    winner = ResourceVersion.objects.get(state="ready")
    assert ResourceVersionPointer.objects.get().current_id == winner.pk
    for state, candidate in results:
        target = roots["cover"] / VersionPublications.target(candidate, "cover.jpg")
        assert target.exists() == (state == "succeeded")


def test_decoded_mp4_publication_keeps_metadata_and_video_pointers_separate(
    environment,
):
    import subprocess
    from nassav.controlled_download import validate_video

    users, vault, roots = environment
    ctx = context(vault)
    tasks, publication, records, assets = runtime(ctx, roots)
    metadata_ops = [operation(user, ctx, records) for user in users]
    token = claim(tasks, metadata_ops[0])
    metadata = publication.prepare(token)
    metadata_row, _ = publish(
        assets, publication, token, metadata, staged_cover(assets, token)
    )
    tasks.finish(token, "succeeded")
    for user, op in zip(users, metadata_ops):
        records.project(user.pk, op["operation_id"])
    video_ops = [
        operation(user, ctx, records, action="download", kind="download")
        for user in users
    ]
    video_token = claim(tasks, video_ops[0])
    video = publication.prepare(video_token)

    def create(path):
        subprocess.run(
            [
                "ffmpeg",
                "-nostdin",
                "-v",
                "error",
                "-y",
                "-f",
                "lavfi",
                "-i",
                "color=c=red:s=160x90:r=25:d=0.2",
                "-c:v",
                "libx264",
                "-pix_fmt",
                "yuv420p",
                "-an",
                "-movflags",
                "+faststart",
                str(path),
            ],
            check=True,
            capture_output=True,
            timeout=10,
        )
        return True

    artifact = assets.stage(
        video_token,
        "video",
        "download/clip.mp4",
        "video",
        create,
        validate=lambda path: validate_video(
            path, 0.2, lambda: tasks.check(video_token), lambda _: None
        ),
    )
    target = publication.target(video, "video.mp4")
    video_row = assets.commit(
        video_token,
        [AssetPromotion(artifact, target)],
        lambda: publication.publish(
            video_token, video, {"avid": "PUB-001", "source_title": "video snapshot"}
        ),
    )
    tasks.finish(video_token, "succeeded")
    for user, op in zip(users, video_ops):
        records.project(user.pk, op["operation_id"])
        entry = UserLibraryEntry.objects.get(user=user)
        assert (
            entry.current_version_id == metadata_row.pk
            and entry.video_version_id == video_row.pk
        )
    assert video_row.file_size == (roots["video"] / target).stat().st_size > 0
    assert len(video_row.media_identity) == 64
