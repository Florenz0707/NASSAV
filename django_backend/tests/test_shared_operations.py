"""DB request/subscription foundation; transport and publication are separate phases."""

from uuid import uuid4

import pytest
from django.contrib.auth import get_user_model

from nassav.shared_work import SharedOperations, OperationConflict, OperationNotFound
from nassav.shared_work_records import DjangoOperationRecords
from nassav.shared_work_models import SharedWork, UserOperation, WorkSubscription
from nassav.library_models import UserLibraryEntry, ResourcePoolEntry
from nassav.task_models import TaskJob, TaskAttempt
from nassav.task_records import DjangoTaskRecords

pytestmark = pytest.mark.django_db


@pytest.fixture
def operations():
    users = [
        get_user_model().objects.create_user(username=name)
        for name in ("shared-a", "shared-b")
    ]
    tasks = DjangoTaskRecords()
    records = DjangoOperationRecords(tasks)
    return users, SharedOperations(records), tasks


def payload(*, avid="ABC-001", source="jable", request_id=None):
    return {
        "avid": avid,
        "source": source,
        "kind": "scrape",
        "action": "add",
        "request_id": str(request_id or uuid4()),
    }


def submit(service, user, command=None):
    return service.submit(
        user.pk,
        command or payload(),
        access_scope="public",
        credential_refs={},
        context_revision="anonymous-fixture-v1",
    )


def test_public_same_spec_has_two_private_operations_and_one_durable_work(operations):
    (first, second), service, _ = operations
    a, b = submit(service, first), submit(service, second)
    assert a["operation_id"] != b["operation_id"]
    assert UserOperation.objects.count() == UserLibraryEntry.objects.count() == 2
    assert (
        SharedWork.objects.count()
        == TaskJob.objects.count()
        == TaskAttempt.objects.count()
        == 1
    )
    assert WorkSubscription.objects.filter(state="attached").count() == 2
    assert TaskJob.objects.get().owner_id is None
    assert a["allowed_actions"] == ["cancel"]
    assert "work_id" not in a and "credential_refs" not in a


def test_request_replay_is_idempotent_and_changed_payload_conflicts(operations):
    (first, _), service, _ = operations
    command = payload()
    original = submit(service, first, command)
    assert submit(service, first, command) == original
    with pytest.raises(OperationConflict, match="request_id_reused"):
        submit(service, first, dict(command, avid="ABC-002"))
    assert TaskJob.objects.count() == 1


def test_cancel_a_detaches_only_a_and_last_cancel_requests_writer_stop(operations):
    (first, second), service, tasks = operations
    a, b = submit(service, first), submit(service, second)
    job = TaskJob.objects.get()
    attempt = TaskAttempt.objects.get()
    token = tasks.claim(str(job.pk), str(attempt.pk), kind="scrape", role="main")
    command = uuid4()
    cancelled = service.cancel(
        first.pk, a["operation_id"], expected_version=a["version"], request_id=command
    )
    assert cancelled["state"] == "cancelled"
    assert (
        service.cancel(
            first.pk,
            a["operation_id"],
            expected_version=a["version"],
            request_id=command,
        )
        == cancelled
    )
    job.refresh_from_db()
    assert job.state == "running"
    assert UserLibraryEntry.objects.filter(user=second, state="pending").exists()
    assert not UserLibraryEntry.objects.filter(user=first).exists()
    service.cancel(
        second.pk, b["operation_id"], expected_version=b["version"], request_id=uuid4()
    )
    job.refresh_from_db()
    assert job.state == "cancelling"
    assert TaskAttempt.objects.get().state == "running"
    assert ResourcePoolEntry.objects.get().state == "pending_gc"
    stopped = tasks.acknowledge_stop(token)
    assert stopped["state"] == "cancelled"


def test_other_owner_cannot_cancel_and_source_specs_do_not_merge(operations):
    (first, second), service, _ = operations
    a = submit(service, first)
    submit(service, second, payload(source="missav"))
    assert SharedWork.objects.count() == 2
    with pytest.raises(OperationNotFound):
        service.cancel(
            second.pk, a["operation_id"], expected_version=1, request_id=uuid4()
        )
    assert WorkSubscription.objects.filter(state="attached").count() == 2


def test_cancelling_new_request_preserves_existing_active_membership(operations):
    (first, _), service, _ = operations
    a = submit(service, first)
    entry = UserLibraryEntry.objects.get(user=first)
    entry.state = "active"
    entry.save()
    service.cancel(first.pk, a["operation_id"], expected_version=1, request_id=uuid4())
    assert UserLibraryEntry.objects.get(pk=entry.pk).state == "active"


def test_private_work_waits_for_private_publication_adapter(operations):
    (first, _), service, _ = operations
    with pytest.raises(OperationConflict, match="private_publication_not_ready"):
        service.submit(
            first.pk,
            payload(),
            access_scope="private:fixture",
            credential_refs={},
            context_revision="fixture-v1",
        )
    assert not UserOperation.objects.exists() and not TaskJob.objects.exists()


def test_retry_keeps_original_binding_when_server_context_changes(operations):
    (first, _), service, _ = operations
    command = payload()
    old = submit(service, first, command)
    replay = service.submit(
        first.pk,
        command,
        access_scope="public",
        credential_refs={},
        context_revision="new-server-context",
    )
    assert replay == old
    assert SharedWork.objects.count() == 1


@pytest.mark.django_db(transaction=True)
def test_concurrent_users_create_one_work_without_duplicate_attempts(operations):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier
    from django.db import close_old_connections

    users, service, _ = operations
    barrier = Barrier(2)

    def add(user):
        close_old_connections()
        try:
            barrier.wait(timeout=10)
            return submit(service, user)
        finally:
            close_old_connections()

    with ThreadPoolExecutor(max_workers=2) as pool:
        rows = list(pool.map(add, users))
    assert rows[0]["operation_id"] != rows[1]["operation_id"]
    assert TaskAttempt.objects.count() == SharedWork.objects.count() == 1
    assert WorkSubscription.objects.count() == 2
