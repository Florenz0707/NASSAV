"""Durable release, latest intents, per-holder logical capacity and safe progress."""

from uuid import uuid4

import pytest
from django.utils import timezone

from nassav.library_models import UserLibraryEntry, UserLibraryCommand
from nassav.library_membership import LibraryMembership, LibraryConflict
from nassav.library_records import DjangoMembershipRecords
from nassav.quota_records import DjangoQuotaReservations, logical_used_bytes
from nassav.shared_work import SharedOperations
from nassav.shared_work_records import (
    DjangoOperationRecords,
    safe_progress,
    safe_timeline,
)
from nassav.resource_version_models import ResourceVersion
from nassav.account_models import UserAccount, QuotaReservation
from test_version_publication import (
    environment as environment,
    context,
    runtime,
    operation,
    claim,
    staged_cover,
    publish,
)

pytestmark = pytest.mark.django_db


def managed(environment):
    users, vault, roots = environment
    ctx = context(vault)
    tasks, publication, _, assets = runtime(ctx, roots)
    records = DjangoOperationRecords(
        tasks,
        publication=publication,
        allow_private=True,
        quotas=DjangoQuotaReservations(),
        manage_intents=True,
    )
    return users, ctx, tasks, publication, records, assets


def test_release_receipt_survives_readding_and_does_not_remove_new_membership(
    environment,
):
    users, ctx, tasks, _, records, _ = managed(environment)
    op = operation(users[0], ctx, records)
    library = LibraryMembership(
        DjangoMembershipRecords(detach_demand=records.detach_membership)
    )
    old = UserLibraryEntry.objects.get(user=users[0])
    request = uuid4()
    result = library.release(
        users[0].pk, old.pk, expected_version=old.version, request_id=request
    )
    operation(users[0], ctx, records)
    fresh = UserLibraryEntry.objects.get(user=users[0])
    assert fresh.pk != old.pk
    assert (
        library.release(
            users[0].pk, old.pk, expected_version=old.version, request_id=request
        )
        == result
    )
    assert UserLibraryEntry.objects.filter(pk=fresh.pk).exists()
    assert UserLibraryCommand.objects.count() == 1
    with pytest.raises(LibraryConflict, match="request_id_reused"):
        library.release(
            users[0].pk, fresh.pk, expected_version=fresh.version, request_id=request
        )
    assert records.get(users[0].pk, op["operation_id"])["state"] == "cancelled"


def test_new_intent_detaches_old_request_but_keeps_shared_work_and_other_user(
    environment,
):
    users, ctx, tasks, _, records, _ = managed(environment)
    first, other = [operation(user, ctx, records) for user in users]
    claim(tasks, first)
    latest = operation(users[0], ctx, records)
    assert records.get(users[0].pk, first["operation_id"])["state"] == "cancelled"
    assert records.get(users[1].pk, other["operation_id"])["state"] == "queued"
    assert records.get(users[0].pk, latest["operation_id"])["state"] == "queued"
    assert QuotaReservation.objects.filter(user=users[0], state="held").count() == 1
    assert QuotaReservation.objects.filter(user=users[0], state="released").count() == 1


def test_idempotent_submit_does_not_reserve_or_advance_intent_twice(environment):
    users, ctx, _, _, records, _ = managed(environment)
    request = uuid4()
    first = operation(users[0], ctx, records, request_id=request)
    entry = UserLibraryEntry.objects.get()
    assert operation(users[0], ctx, records, request_id=request) == first
    entry.refresh_from_db()
    assert entry.demand_generations == {"scrape": 2}
    assert QuotaReservation.objects.count() == 1


def test_final_video_quota_rejects_only_one_holder_and_releases_once(environment):
    users, ctx, tasks, publication, records, assets = managed(environment)
    initial = [operation(user, ctx, records) for user in users]
    token = claim(tasks, initial[0])
    candidate = publication.prepare(token)
    publish(assets, publication, token, candidate, staged_cover(assets, token))
    tasks.finish(token, "succeeded")
    for user, op in zip(users, initial):
        records.project(user.pk, op["operation_id"])
    UserAccount.objects.filter(user=users[0]).update(storage_quota_bytes=10)
    UserAccount.objects.filter(user=users[1]).update(storage_quota_bytes=1000)
    operations = []
    for user in users:
        operations.append(
            SharedOperations(records).submit(
                user.pk,
                {
                    "avid": "PUB-001",
                    "source": "jable",
                    "kind": "download",
                    "action": "download",
                    "request_id": str(uuid4()),
                },
                access_scope=ctx.work_binding["access_scope"],
                credential_refs=ctx.work_binding["credential_refs"],
                context_revision=ctx.work_binding["context_revision"],
            )
        )
    from nassav.shared_work_models import SharedWork
    from nassav.task_models import TaskAttempt

    work = SharedWork.objects.get(job__kind="download")
    token = tasks.claim(
        str(work.job_id), str(TaskAttempt.objects.get(job=work.job).pk), kind="download"
    )
    # This fixture isolates accounting after a ready publication. Actual MP4
    # validity and asset journaling are covered by the publication suite.
    ResourceVersion.objects.create(
        pool=work.pool,
        pool_generation=work.pool_generation,
        work=work,
        kind="video",
        source_name="jable",
        access_scope="public",
        credential_refs=work.credential_refs,
        context_revision=work.spec["context_revision"],
        state="ready",
        published_at=timezone.now(),
        file_size=100,
        media_identity="a" * 64,
    )
    tasks.finish(token, "succeeded")
    failed = records.project(users[0].pk, operations[0]["operation_id"])
    succeeded = records.project(users[1].pk, operations[1]["operation_id"])
    assert failed["error_code"] == "QUOTA_EXCEEDED" and failed["state"] == "failed"
    assert succeeded["state"] == "succeeded"
    assert (
        logical_used_bytes(users[0].pk) == 0 and logical_used_bytes(users[1].pk) == 100
    )
    assert QuotaReservation.objects.filter(state="held").count() == 0
    assert records.project(users[0].pk, failed["operation_id"]) == failed


def test_progress_projection_excludes_links_and_untyped_values():
    assert safe_progress(
        {"percent": 25.5, "speed": "1.2MiB/s", "eta": "00:12", "m3u8": "private URL"}
    ) == {
        "percent": 25.5,
        "speed": "1.2MiB/s",
        "eta": "00:12",
    }
    assert (
        safe_progress(
            {
                "percent": True,
                "speed": "Cookie=secret",
                "eta": "https://private.invalid",
            }
        )
        == {}
    )
    assert safe_timeline(
        [{"stage": "source", "state": "running", "at": 12, "owner": "secret"}]
    ) == [
        {"stage": "source", "state": "running", "at": 12},
    ]


def test_ready_public_version_is_reused_without_a_new_attempt_or_fetch(environment):
    from nassav.task_models import TaskJob, TaskAttempt

    users, ctx, tasks, publication, records, assets = managed(environment)
    first = operation(users[0], ctx, records)
    token = claim(tasks, first)
    candidate = publication.prepare(token)
    published, _ = publish(
        assets, publication, token, candidate, staged_cover(assets, token)
    )
    tasks.finish(token, "succeeded")
    records.project(users[0].pk, first["operation_id"])
    other = operation(users[1], ctx, records)
    assert other["state"] == "succeeded"
    assert (
        UserLibraryEntry.objects.get(user=users[1]).current_version_id == published.pk
    )
    assert TaskJob.objects.count() == TaskAttempt.objects.count() == 1
    assert QuotaReservation.objects.filter(state="held").count() == 0


def test_readding_after_last_release_reuses_formal_version_but_not_old_execution(
    environment,
):
    from nassav.task_models import TaskJob

    users, ctx, tasks, publication, records, assets = managed(environment)
    first = operation(users[0], ctx, records)
    token = claim(tasks, first)
    candidate = publication.prepare(token)
    published, _ = publish(
        assets, publication, token, candidate, staged_cover(assets, token)
    )
    tasks.finish(token, "succeeded")
    records.project(users[0].pk, first["operation_id"])
    old = UserLibraryEntry.objects.get(user=users[0])
    library = LibraryMembership(
        DjangoMembershipRecords(detach_demand=records.detach_membership)
    )
    library.release(
        users[0].pk, old.pk, expected_version=old.version, request_id=uuid4()
    )
    again = operation(users[0], ctx, records)
    assert again["state"] == "succeeded"
    fresh = UserLibraryEntry.objects.get(user=users[0])
    assert fresh.pk != old.pk and fresh.current_version_id == published.pk
    assert fresh.pool.lifetime_generation == 2
    assert TaskJob.objects.count() == 1


def test_replacing_own_intent_does_not_require_a_second_operation_slot(environment):
    users, ctx, _, _, records, _ = managed(environment)
    UserAccount.objects.filter(user=users[0]).update(max_active_operations=1)
    first = operation(users[0], ctx, records)
    second = operation(users[0], ctx, records)
    assert first["operation_id"] != second["operation_id"]
    assert records.get(users[0].pk, first["operation_id"])["state"] == "cancelled"
    assert QuotaReservation.objects.filter(user=users[0], state="held").count() == 1


def test_replay_does_not_reload_revoked_source_context(environment):
    from unittest.mock import Mock
    from nassav.library_submission import LibrarySubmission

    users, ctx, _, _, records, _ = managed(environment)
    resolver = Mock(return_value=(ctx, lambda: None))
    service = LibrarySubmission(records, resolver, lambda: None)
    body = {
        "avid": "PUB-001",
        "source": "jable",
        "kind": "scrape",
        "action": "add",
        "request_id": str(uuid4()),
    }
    first = service.submit(users[0].pk, body)
    resolver.side_effect = PermissionError("source revoked after submission")
    assert service.submit(users[0].pk, body) == first
    assert resolver.call_count == 1


@pytest.mark.django_db(transaction=True)
def test_concurrent_same_user_intents_leave_only_latest_demand_and_one_reservation(
    environment,
):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier
    from django.db import close_old_connections
    from nassav.shared_work_models import WorkSubscription, UserOperation

    users, ctx, _, _, records, _ = managed(environment)
    UserAccount.objects.filter(user=users[0]).update(max_active_operations=1)
    barrier = Barrier(2)

    def run(_):
        close_old_connections()
        try:
            barrier.wait(timeout=10)
            return operation(users[0], ctx, records)
        finally:
            close_old_connections()

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(run, range(2)))
    assert results[0]["operation_id"] != results[1]["operation_id"]
    assert WorkSubscription.objects.filter(state="attached").count() == 1
    assert UserOperation.objects.filter(state="cancelled").count() == 1
    assert QuotaReservation.objects.filter(state="held").count() == 1
