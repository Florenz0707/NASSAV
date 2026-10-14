"""Boundary, user-fenced projection and membership/disable integration."""

from uuid import uuid4
from unittest.mock import Mock

import pytest
from django.contrib.auth import get_user_model
from django.db import transaction

from nassav.account_models import UserAccount
from nassav.composition import build_account_management, build_library_membership
from nassav.library_models import UserLibraryEntry, ResourcePoolEntry
from nassav.shared_work import SharedOperations, OperationConflict
from nassav.shared_work_models import UserOperation, WorkSubscription
from nassav.shared_work_records import DjangoOperationRecords
from nassav.task_control_rules import TaskExecutionInvalid
from nassav.task_models import TaskJob, TaskAttempt
from nassav.task_records import DjangoTaskRecords

pytestmark = pytest.mark.django_db


@pytest.fixture
def scenario():
    users = [
        get_user_model().objects.create_user(username=name)
        for name in ("life-a", "life-b")
    ]
    for user in users:
        UserAccount.objects.create(user=user)
    tasks = DjangoTaskRecords(
        shared_execution=True
    )  # Explicit test executor, not production.
    records = DjangoOperationRecords(tasks)
    service = SharedOperations(records)
    operations = [
        service.submit(
            user.pk,
            {
                "avid": "LIFE-001",
                "kind": "scrape",
                "action": "add",
                "source": "jable",
                "request_id": str(uuid4()),
            },
            access_scope="public",
            credential_refs={},
            context_revision="fixture-v1",
        )
        for user in users
    ]
    return users, tasks, records, service, operations


def claim(tasks):
    job, attempt = TaskJob.objects.get(), TaskAttempt.objects.get()
    return tasks.claim(str(job.pk), str(attempt.pk), kind="scrape", role="main")


def test_legacy_dispatch_and_claim_never_execute_shared_spec(scenario):
    _, _, _, _, _ = scenario
    legacy = DjangoTaskRecords()
    old, _ = legacy.create("scrape", "OLD-001", owner_id=None, action="add")
    tickets = []
    assert legacy.dispatch_pending(tickets.append) == {"sent": 1, "failed": 0}
    assert tickets[0]["job_id"] == old["job_id"]
    shared_job = TaskJob.objects.get(options__shared_work=True)
    attempt = TaskAttempt.objects.get(job=shared_job)
    assert attempt.state == "pending"
    with pytest.raises(TaskExecutionInvalid):
        legacy.claim(str(shared_job.pk), str(attempt.pk))
    shared_job.refresh_from_db()
    assert shared_job.state == "queued"


def test_project_is_private_idempotent_and_scrubs_backend_diagnostics(scenario):
    users, tasks, records, _, operations = scenario
    token = claim(tasks)
    tasks.checkpoint(token, "source")
    running = records.project(users[0].pk, operations[0]["operation_id"])
    assert running["state"] == "running" and running["stage"] == "source"
    assert records.project(users[0].pk, running["operation_id"]) == running
    assert UserOperation.objects.get(user=users[1]).state == "queued"
    tasks.finish(token, "failed", error_code="PRIVATE_DETAIL", message="Cookie=secret")
    failed = records.project(users[0].pk, running["operation_id"])
    assert failed["state"] == failed["stage"] == "failed"
    assert failed["error_code"] == "WORK_FAILED" and "secret" not in str(failed)
    assert records.project(users[0].pk, failed["operation_id"]) == failed
    assert UserLibraryEntry.objects.filter(user=users[1]).exists()
    records.project(users[1].pk, operations[1]["operation_id"])
    assert not UserLibraryEntry.objects.exists()
    assert ResourcePoolEntry.objects.get().state == "pending_gc"


def test_success_without_scoped_version_cannot_activate_membership(scenario):
    users, tasks, records, _, operations = scenario
    token = claim(tasks)
    tasks.finish(token, "succeeded")
    with pytest.raises(OperationConflict, match="publication_not_ready"):
        records.project(users[0].pk, operations[0]["operation_id"])
    assert UserLibraryEntry.objects.filter(state="pending").count() == 2
    assert UserOperation.objects.filter(state="succeeded").count() == 0


def test_cancelled_operation_is_not_resurrected_by_late_stage_or_failure(scenario):
    users, tasks, records, service, operations = scenario
    token = claim(tasks)
    cancelled = service.cancel(
        users[0].pk,
        operations[0]["operation_id"],
        expected_version=1,
        request_id=uuid4(),
    )
    tasks.checkpoint(token, "saving")
    assert records.project(users[0].pk, cancelled["operation_id"]) == cancelled
    tasks.finish(token, "failed")
    assert records.project(users[0].pk, cancelled["operation_id"]) == cancelled
    assert not UserLibraryEntry.objects.filter(user=users[0]).exists()


def test_release_detaches_only_own_demand_and_last_release_requests_stop(scenario):
    users, tasks, _, _, _ = scenario
    claim(tasks)
    library = build_library_membership()
    first = UserLibraryEntry.objects.get(user=users[0])
    library.release(users[0].pk, first.pk, expected_version=first.version)
    assert TaskJob.objects.get().state == "running"
    assert UserOperation.objects.get(user=users[0]).state == "cancelled"
    assert WorkSubscription.objects.filter(state="attached").count() == 1
    second = UserLibraryEntry.objects.get(user=users[1])
    library.release(users[1].pk, second.pk, expected_version=second.version)
    assert TaskJob.objects.get().state == "cancelling"
    assert TaskAttempt.objects.get().state == "running"
    assert ResourcePoolEntry.objects.get().state == "pending_gc"


def test_disable_is_not_shared_initiator_control(scenario):
    users, tasks, _, _, _ = scenario
    claim(tasks)
    admin = get_user_model().objects.create_user(username="life-admin")
    UserAccount.objects.create(user=admin, role="admin")
    build_account_management().execute(
        admin.pk,
        "update",
        users[0].pk,
        {
            "is_active": False,
            "expected_version": 1,
            "request_id": str(uuid4()),
            "reason": "user_request",
        },
    )
    assert TaskJob.objects.get().state == "running"
    assert WorkSubscription.objects.filter(
        state="attached", operation__user=users[1]
    ).exists()
    assert UserOperation.objects.get(user=users[0]).state == "cancelled"
    assert not UserLibraryEntry.objects.filter(user=users[0]).exists()


def test_old_pool_generation_detaches_without_stopping_other_work_demand(scenario):
    users, tasks, records, _, operations = scenario
    claim(tasks)
    pool = ResourcePoolEntry.objects.get()
    pool.lifetime_generation += 1
    pool.save()
    cancelled = records.project(users[0].pk, operations[0]["operation_id"])
    assert cancelled["state"] == "cancelled"
    assert TaskJob.objects.get().state == "running"
    records.project(users[1].pk, operations[1]["operation_id"])
    assert TaskJob.objects.get().state == "cancelling"


def test_hint_runs_only_after_commit_and_only_own_identity(scenario):
    users, tasks, _, _, operations = scenario
    token = claim(tasks)
    tasks.checkpoint(token, "source")
    hint = Mock()
    records = DjangoOperationRecords(tasks, hint=hint)
    with transaction.atomic():
        records.project(users[0].pk, operations[0]["operation_id"])
        hint.assert_not_called()
        transaction.set_rollback(True)
    hint.assert_not_called()
    assert UserOperation.objects.get(user=users[0]).version == 1


def test_bounded_projection_advances_each_user_cursor_without_version_churn(scenario):
    users, _, records, _, _ = scenario
    assert records.project_pending(limit=1) == {"projected": 1, "skipped": 0}
    assert UserOperation.objects.filter(projected_work_version=1).count() == 1
    assert records.project_pending(limit=1) == {"projected": 1, "skipped": 0}
    assert records.project_pending(limit=1) == {"projected": 0, "skipped": 0}
    assert UserOperation.objects.filter(version=1).count() == len(users)


def test_project_hint_is_private_and_emitted_after_committed_update(
    scenario, django_capture_on_commit_callbacks
):
    users, tasks, _, _, operations = scenario
    claim(tasks)
    hint = Mock()
    records = DjangoOperationRecords(tasks, hint=hint)
    with django_capture_on_commit_callbacks(execute=True) as callbacks:
        snapshot = records.project(users[0].pk, operations[0]["operation_id"])
        hint.assert_not_called()
    assert len(callbacks) == 1
    hint.assert_called_once_with(
        users[0].pk,
        {
            "operation_id": snapshot["operation_id"],
            "version": snapshot["version"],
        },
    )


@pytest.mark.django_db(transaction=True)
def test_other_user_projection_and_membership_release_can_run_concurrently(scenario):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier
    from django.db import close_old_connections

    users, tasks, records, _, operations = scenario
    token = claim(tasks)
    tasks.finish(token, "failed")
    entry = UserLibraryEntry.objects.get(user=users[0])
    barrier = Barrier(2)

    def run(action):
        close_old_connections()
        try:
            barrier.wait(timeout=10)
            return action()
        finally:
            close_old_connections()

    actions = [
        lambda: build_library_membership().release(
            users[0].pk, entry.pk, expected_version=1
        ),
        lambda: records.project(users[1].pk, operations[1]["operation_id"]),
    ]
    with ThreadPoolExecutor(max_workers=2) as executor:
        list(executor.map(run, actions))
    assert UserOperation.objects.get(user=users[0]).state == "cancelled"
    assert UserOperation.objects.get(user=users[1]).state == "failed"
    assert not UserLibraryEntry.objects.exists()
    assert ResourcePoolEntry.objects.get().state == "pending_gc"
