"""Explicit roles, command fencing, safe audit, revocation and quota isolation."""

from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from io import StringIO
from threading import Barrier
from uuid import uuid4

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import close_old_connections
from django.utils import timezone

from nassav.account_models import (
    UserAccount,
    AuditEvent,
    AdminCommandReceipt,
    UserLoginSession,
    QuotaReservation,
)
from nassav.account_management import AccountConflict
from nassav.account_policy import is_app_admin, can_read_resource, can_read_playback
from nassav.composition import build_account_management, build_library_membership
from nassav.library_models import ResourcePoolEntry, UserLibraryEntry
from nassav.models import AVResource
from nassav.playback import records, progress
from nassav.playback.policy import PlaybackGatewayError
from nassav.quota_records import DjangoQuotaReservations
from nassav.resource_administration import set_availability


@pytest.fixture
def admin(operator_user):
    UserAccount.objects.create(user=operator_user, role="admin")
    return operator_user


@pytest.fixture
def member(django_user_model):
    user = django_user_model.objects.create_user(
        username="managed-member", password="member-password-for-test"
    )
    UserAccount.objects.create(user=user)
    return user


def command(**changes):
    return {
        "request_id": str(uuid4()),
        "reason": "maintenance",
        "expected_version": 1,
        **changes,
    }


def owned(user, avid="ACC-001", *, scope="public", size=0):
    resource = AVResource.objects.create(
        avid=avid, source="jable", file_exists=size > 0, file_size=size
    )
    pool = ResourcePoolEntry.objects.create(
        canonical_avid=avid, resource=resource, state="ready"
    )
    entry = UserLibraryEntry.objects.create(
        user=user,
        pool=pool,
        state="active",
        access_scope=scope,
        desired_spec={"source": "jable"},
    )
    return resource, pool, entry


@pytest.mark.django_db
def test_bootstrap_preview_and_explicit_role_not_django_flags(operator_user):
    operator_user.is_staff = operator_user.is_superuser = True
    operator_user.save()
    assert not is_app_admin(operator_user)
    output = StringIO()
    call_command("bootstrap_app_admin", username=operator_user.username, stdout=output)
    assert '"applied": false' in output.getvalue() and not UserAccount.objects.exists()
    request_id = str(uuid4())
    call_command(
        "bootstrap_app_admin",
        username=operator_user.username,
        apply=True,
        request_id=request_id,
    )
    assert is_app_admin(operator_user)
    call_command(
        "bootstrap_app_admin",
        username=operator_user.username,
        apply=True,
        request_id=request_id,
    )
    assert AuditEvent.objects.count() == 1
    with pytest.raises(CommandError, match="bootstrap_not_available"):
        call_command(
            "bootstrap_app_admin",
            username=operator_user.username,
            apply=True,
            request_id=str(uuid4()),
        )


@pytest.mark.django_db
def test_last_admin_protection_and_idempotent_safe_audit(admin, member):
    manager = build_account_management()
    with pytest.raises(AccountConflict, match="last_admin"):
        manager.execute(admin.pk, "update", admin.pk, command(role="user"))
    with pytest.raises(PermissionError):
        manager.execute(member.pk, "update", member.pk, command(role="admin"))
    request = command(storage_quota_bytes=1000)
    first = manager.execute(admin.pk, "update", member.pk, request)
    assert manager.execute(admin.pk, "update", member.pk, request) == first
    with pytest.raises(AccountConflict, match="request_id_conflict"):
        manager.execute(
            admin.pk, "update", member.pk, {**request, "storage_quota_bytes": 1001}
        )
    with pytest.raises(AccountConflict, match="account_version_conflict"):
        manager.execute(admin.pk, "update", member.pk, command(role="admin"))
    assert AuditEvent.objects.count() == 1
    assert AuditEvent.objects.get().result == {"status": "succeeded", "version": 2}


@pytest.mark.django_db
def test_password_command_does_not_store_secret_and_audit_prune_keeps_receipt(
    admin, member
):
    password = "a-private-new-password-test"
    payload = command(password=password)
    manager = build_account_management()
    result = manager.execute(admin.pk, "reset_password", member.pk, payload)
    member.refresh_from_db()
    assert member.check_password(password)
    assert password not in str(AuditEvent.objects.values().get())
    assert password not in str(AdminCommandReceipt.objects.values().get())
    AuditEvent.objects.update(created_at=timezone.now() - timedelta(days=200))
    call_command("prune_audit_events", apply=True, days=180, limit=1)
    assert not AuditEvent.objects.exists() and AdminCommandReceipt.objects.count() == 1
    assert manager.execute(admin.pk, "reset_password", member.pk, payload) == result
    assert UserAccount.objects.get(user=member).version == 2


@pytest.mark.django_db
def test_disable_revokes_logins_playback_membership_quota_and_own_jobs_only(
    admin, member, client
):
    from django.contrib.sessions.models import Session
    from nassav.composition import build_task_records

    resource, pool, entry = owned(member)
    owned(admin, "ACC-OTHER")
    client.force_login(member)
    key = client.session.session_key
    UserLoginSession.objects.create(user=member, session_id=key)
    session = records.submit(
        member.pk,
        key,
        resource.avid,
        uuid4(),
        mode="local",
        descriptor={"test": "identity"},
    )
    task_records = build_task_records()
    mine, _ = task_records.create(
        "download", resource.avid, action="download", owner_id=member.pk
    )
    other, _ = task_records.create(
        "download", "ACC-OTHER", action="download", owner_id=admin.pk
    )
    quota = DjangoQuotaReservations().reserve(member.pk, pool.pk, uuid4(), 100)
    build_account_management().execute(
        admin.pk, "update", member.pk, command(is_active=False)
    )
    member.refresh_from_db()
    session.refresh_from_db()
    assert not member.is_active and session.state == "closed"
    assert not Session.objects.filter(session_key=key).exists()
    assert not UserLibraryEntry.objects.filter(user=member).exists()
    assert UserLibraryEntry.objects.filter(user=admin).exists()
    assert QuotaReservation.objects.get(pk=quota["reservation_id"]).state == "released"
    assert task_records.get(mine["job_id"])["state"] == "cancelled"
    assert task_records.get(other["job_id"])["state"] == "queued"
    assert AVResource.objects.filter(pk=resource.pk).exists()
    from nassav.task_control_rules import TaskForbidden

    with pytest.raises(TaskForbidden, match="账号不可用"):
        task_records.create("scrape", "LATE-ADD", action="add", owner_id=member.pk)


@pytest.mark.django_db
def test_private_scope_is_not_granted_to_admin_and_normal_release_can_drain(
    admin, member
):
    resource, pool, entry = owned(member)
    private, _, _ = owned(member, "PRIVATE-001", scope="personal:unknown-credential")
    assert not can_read_resource(admin, private.avid, administrative=True)
    session = records.submit(
        member.pk,
        "login-key",
        resource.avid,
        uuid4(),
        mode="local",
        descriptor={"test": "identity"},
    )
    build_library_membership().release(member.pk, entry.pk, expected_version=1)
    assert not can_read_resource(member, resource.avid)
    assert can_read_playback(member, session)
    with pytest.raises(PlaybackGatewayError, match="resource_not_available"):
        progress.claim(
            session.pk, member.pk, "login-key", session.generation, uuid4(), 0
        )
    pool.refresh_from_db()
    set_availability(
        admin.pk, pool.pk, command(expected_version=pool.version, available=False)
    )
    session.refresh_from_db()
    assert session.state == "closed" and not can_read_playback(member, session)
    assert AVResource.objects.filter(pk=resource.pk).exists()


@pytest.mark.django_db
def test_quota_counts_full_logical_bytes_per_user_and_never_refunds_twice(
    admin, member
):
    _, pool, _ = owned(member, size=80)
    account = UserAccount.objects.get(user=member)
    account.storage_quota_bytes = 100
    account.save()
    quota = DjangoQuotaReservations()
    request_id = uuid4()
    reservation = quota.reserve(member.pk, pool.pk, request_id, 20)
    assert quota.reserve(member.pk, pool.pk, request_id, 20) == reservation
    with pytest.raises(PermissionError, match="quota_exceeded"):
        quota.reserve(member.pk, pool.pk, uuid4(), 1)
    assert quota.release(member.pk, reservation["reservation_id"]) == quota.release(
        member.pk, reservation["reservation_id"]
    )
    assert quota.reserve(member.pk, pool.pk, request_id, 20)["state"] == "released"
    with pytest.raises(QuotaReservation.DoesNotExist):
        quota.release(admin.pk, reservation["reservation_id"])
    with pytest.raises(AccountConflict):
        quota.reserve(member.pk, pool.pk, request_id, 19)


def parallel(actions):
    barrier = Barrier(len(actions))

    def run(action):
        close_old_connections()
        try:
            barrier.wait(timeout=10)
            try:
                return action()
            except (AccountConflict, PermissionError) as error:
                return error
        finally:
            close_old_connections()

    with ThreadPoolExecutor(max_workers=len(actions)) as executor:
        futures = [executor.submit(run, action) for action in actions]
        return [future.result(timeout=20) for future in futures]


@pytest.mark.django_db(transaction=True)
def test_competing_admin_demotions_leave_an_active_admin(admin, member):
    UserAccount.objects.filter(user=member).update(role="admin")
    manager = build_account_management()
    results = parallel(
        [
            lambda: manager.execute(admin.pk, "update", admin.pk, command(role="user")),
            lambda: manager.execute(
                member.pk, "update", member.pk, command(role="user")
            ),
        ]
    )
    assert sum(isinstance(item, AccountConflict) for item in results) == 1
    assert UserAccount.objects.filter(role="admin", user__is_active=True).count() == 1


@pytest.mark.django_db(transaction=True)
def test_concurrent_quota_reservations_cannot_overbook(member):
    _, pool, _ = owned(member)
    UserAccount.objects.filter(user=member).update(storage_quota_bytes=100)
    quota = DjangoQuotaReservations()
    results = parallel(
        [
            lambda: quota.reserve(member.pk, pool.pk, uuid4(), 60),
            lambda: quota.reserve(member.pk, pool.pk, uuid4(), 60),
        ]
    )
    assert sum(isinstance(item, PermissionError) for item in results) == 1
    assert QuotaReservation.objects.filter(state="held").count() == 1


@pytest.mark.django_db
def test_managed_admin_task_controls_require_safe_reason_and_audit_once(admin):
    from rest_framework.test import APIClient
    from nassav.composition import build_task_records
    from nassav.task_models import TaskCommand

    records_adapter = build_task_records()
    job, _ = records_adapter.create(
        "download", "ADMIN-WORK", action="download", owner_id=admin.pk
    )
    api = APIClient()
    api.force_authenticate(admin)
    url = f"/nassav/api/tasks/jobs/{job['job_id']}/pause"
    payload = {"request_id": str(uuid4()), "expected_version": 1}
    assert api.post(url, payload, format="json").status_code == 400
    payload["reason"] = "maintenance"
    assert api.post(url, payload, format="json").status_code == 202
    assert api.post(url, payload, format="json").status_code == 202
    assert TaskCommand.objects.count() == 1 and AuditEvent.objects.count() == 1
    assert (
        api.post(url.replace("/pause", "/cancel"), payload, format="json").status_code
        == 409
    )
    assert records_adapter.get(job["job_id"])["state"] == "paused"


@pytest.mark.django_db
def test_invalid_json_types_and_owner_injection_are_rejected_by_admin_api(
    admin, member
):
    from rest_framework.test import APIClient

    api = APIClient()
    api.force_authenticate(admin)
    url = f"/nassav/api/admin/users/{member.pk}"
    for payload in [
        command(role=["admin"]),
        command(reason={"secret": "not-logged"}, role="admin"),
        command(role="admin", owner=admin.pk),
    ]:
        assert api.patch(url, payload, format="json").status_code == 400
    assert UserAccount.objects.get(user=member).role == "user"
    assert not AuditEvent.objects.exists()
    assert api.patch(url, "null", content_type="application/json").status_code == 400
    assert api.post("/nassav/api/admin/users", [], format="json").status_code == 400
