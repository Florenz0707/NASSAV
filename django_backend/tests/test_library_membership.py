"""Ownership, stale writes, import safety and competing independent transactions."""

from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from io import StringIO
from threading import Barrier, local

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import IntegrityError, close_old_connections, transaction
from django.db.models.deletion import ProtectedError
from django.utils import timezone

from nassav.composition import build_library_membership
from nassav.library_import import LibraryImportConflict, import_legacy_library
from nassav.library_membership import LibraryConflict, LibraryNotFound
from nassav.library_models import ResourcePoolEntry, UserLibraryEntry
from nassav.models import AVResource, UserResourceState


@pytest.fixture
def users(django_user_model):
    return [
        django_user_model.objects.create_user(username=f"pool-user-{i}")
        for i in range(2)
    ]


@pytest.mark.django_db
def test_distinct_users_and_duplicate_add_share_identity_but_not_membership(users):
    library = build_library_membership()
    a = library.attach(users[0].pk, " pool-001 ", source="Jable", access_scope="public")
    repeat = library.attach(
        users[0].pk, "POOL-001", source="jable", access_scope="public"
    )
    b = library.attach(users[1].pk, "POOL-001", source="jable", access_scope="public")
    assert a == repeat
    assert a["pool_id"] == b["pool_id"] and a["entry_id"] != b["entry_id"]
    assert a["membership_state"] == b["membership_state"] == "pending"
    assert ResourcePoolEntry.objects.count() == 1
    assert UserLibraryEntry.objects.count() == 2
    with pytest.raises(LibraryConflict, match="membership_spec_conflict"):
        library.attach(
            users[0].pk, "POOL-001", source="missav", access_scope="personal:1"
        )
    with pytest.raises(LibraryNotFound):
        library.release(users[1].pk, a["entry_id"], expected_version=1)


@pytest.mark.django_db
def test_last_release_only_marks_gc_and_reattach_fences_previous_lifetime(
    users, tmp_path
):
    sentinel = tmp_path / "POOL-002.mp4"
    sentinel.write_bytes(b"existing media")
    library = build_library_membership()
    a = library.attach(users[0].pk, "POOL-002", source="jable", access_scope="public")
    b = library.attach(users[1].pk, "POOL-002", source="jable", access_scope="public")
    assert not library.release(users[0].pk, a["entry_id"], expected_version=1)[
        "gc_scheduled"
    ]
    assert library.release(users[1].pk, b["entry_id"], expected_version=1)[
        "gc_scheduled"
    ]
    pool = ResourcePoolEntry.objects.get()
    assert pool.gc_after >= timezone.now() + timedelta(hours=23)
    c = library.attach(users[0].pk, "POOL-002", source="jable", access_scope="public")
    assert c["entry_id"] != a["entry_id"] and c["pool_generation"] == 2
    pool.refresh_from_db()
    assert pool.state == "preparing" and pool.gc_after is None
    with pytest.raises(LibraryNotFound):
        library.release(users[0].pk, a["entry_id"], expected_version=1)
    assert sentinel.read_bytes() == b"existing media"


@pytest.mark.django_db
def test_failed_or_deleting_pool_cannot_be_resurrected(users):
    library = build_library_membership()
    for state in ["deleting", "cleanup_failed"]:
        pool = ResourcePoolEntry.objects.create(
            canonical_avid=f"BLOCK-{state.upper()}", state=state
        )
        with pytest.raises(LibraryConflict, match="resource_reclaiming"):
            library.attach(
                users[0].pk, pool.canonical_avid, source="jable", access_scope="public"
            )
        pool.refresh_from_db()
        assert pool.state == state and not pool.memberships.exists()


@pytest.mark.django_db
def test_release_uses_version_and_only_clears_own_watch_later(users):
    resource = AVResource.objects.create(avid="POOL-003", source="jable")
    pool = ResourcePoolEntry.objects.create(
        canonical_avid=resource.avid, resource=resource, state="ready"
    )
    library = build_library_membership()
    a = library.attach(
        users[0].pk, resource.avid, source="jable", access_scope="public"
    )
    for user in users:
        UserResourceState.objects.create(
            user=user,
            resource=resource,
            watch_later=True,
            watched=True,
            notes="保留个人备注",
        )
    with pytest.raises(LibraryConflict, match="version_conflict"):
        library.release(users[0].pk, a["entry_id"], expected_version=2)
    assert UserLibraryEntry.objects.filter(pool=pool).exists()
    library.release(users[0].pk, a["entry_id"], expected_version=1)
    own = UserResourceState.objects.get(user=users[0])
    other = UserResourceState.objects.get(user=users[1])
    assert not own.watch_later and own.version == 2 and own.watched and own.notes
    assert other.watch_later and other.version == 1
    assert AVResource.objects.filter(pk=resource.pk).exists()


@pytest.mark.django_db
def test_schema_guards_and_protected_memberships(users):
    pool = ResourcePoolEntry.objects.create(canonical_avid="POOL-004")
    UserLibraryEntry.objects.create(user=users[0], pool=pool, access_scope="public")
    for values in [dict(state="unknown"), dict(version=0), dict(state="pending_gc")]:
        with pytest.raises(IntegrityError), transaction.atomic():
            ResourcePoolEntry.objects.create(canonical_avid="BAD-004", **values)
    with pytest.raises(IntegrityError), transaction.atomic():
        UserLibraryEntry.objects.create(user=users[0], pool=pool, access_scope="public")
    with pytest.raises(ProtectedError):
        pool.delete()
    with pytest.raises(ProtectedError):
        users[0].delete()


@pytest.mark.django_db
def test_disabled_user_and_invalid_input_cannot_create_demand(users):
    library = build_library_membership()
    users[0].is_active = False
    users[0].save(update_fields=["is_active"])
    with pytest.raises(PermissionError):
        library.attach(users[0].pk, "POOL-005", source="jable", access_scope="public")
    for avid in ["../POOL-005", "X" * 51, None]:
        with pytest.raises(ValueError):
            library.attach(users[1].pk, avid, source="jable", access_scope="public")
    assert not ResourcePoolEntry.objects.exists()


@pytest.mark.django_db
def test_import_is_preview_explicit_and_preserves_edited_memberships(
    operator_user, settings
):
    resource = AVResource.objects.create(
        avid="IMPORT-001", source="Jable", watched=True
    )
    before = resource.metadata_updated_at
    output = StringIO()
    call_command(
        "import_resource_library", username=operator_user.username, stdout=output
    )
    assert '"applied": false' in output.getvalue()
    assert not ResourcePoolEntry.objects.exists()
    result = import_legacy_library(operator_user.username, apply=True)
    assert result["new_pools"] == result["new_memberships"] == 1
    entry = UserLibraryEntry.objects.get()
    assert (
        entry.state == "active"
        and entry.access_scope == f"legacy:operator:{operator_user.pk}"
    )
    entry.desired_spec = {"source": "edited"}
    entry.version = 5
    entry.save()
    result = import_legacy_library(operator_user.username, apply=True)
    entry.refresh_from_db()
    assert (
        result["new_memberships"] == 0
        and entry.version == 5
        and entry.desired_spec == {"source": "edited"}
    )
    resource.refresh_from_db()
    assert resource.watched and resource.metadata_updated_at == before
    assert not UserResourceState.objects.exists()
    with pytest.raises(CommandError, match="原操作者"):
        call_command("import_resource_library", username="unconfirmed", apply=True)


@pytest.mark.django_db
def test_import_conflict_rolls_back_all_new_rows(users):
    AVResource.objects.create(avid="IMPORT-AAA")
    bad = AVResource.objects.create(avid="IMPORT-ZZZ")
    ResourcePoolEntry.objects.create(canonical_avid=bad.avid, state="deleting")
    with pytest.raises(LibraryImportConflict):
        import_legacy_library(users[0].username, apply=True)
    assert (
        ResourcePoolEntry.objects.count() == 1 and not UserLibraryEntry.objects.exists()
    )
    AVResource.objects.create(avid="import-aaa")
    with pytest.raises(LibraryImportConflict, match="规范身份冲突"):
        import_legacy_library(users[0].username)


def _race(monkeypatch, actions):
    import nassav.library_records as records

    barrier = Barrier(len(actions))
    context = local()
    original = records.lock_user

    def lock_user(user_id):
        # Both independent transactions reach their first write before either
        # proceeds. Retries must not wait for an already completed participant.
        if not getattr(context, "started", False):
            context.started = True
            barrier.wait(timeout=10)
        return original(user_id)

    monkeypatch.setattr(records, "lock_user", lock_user)

    def execute(action):
        close_old_connections()
        try:
            return action(build_library_membership())
        finally:
            close_old_connections()

    with ThreadPoolExecutor(max_workers=len(actions)) as executor:
        futures = [executor.submit(execute, action) for action in actions]
        return [future.result(timeout=20) for future in futures]


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize("same_user", [False, True])
def test_concurrent_add_uses_unique_pool_and_membership(users, monkeypatch, same_user):
    ids = [users[0].pk, users[0].pk if same_user else users[1].pk]
    results = _race(
        monkeypatch,
        [
            lambda library, uid=uid: library.attach(
                uid, "RACE-001", source="jable", access_scope="public"
            )
            for uid in ids
        ],
    )
    assert ResourcePoolEntry.objects.count() == 1
    assert UserLibraryEntry.objects.count() == (1 if same_user else 2)
    assert results[0]["pool_id"] == results[1]["pool_id"]


@pytest.mark.django_db(transaction=True)
def test_competing_last_release_and_add_keep_pending_protection(users, monkeypatch):
    library = build_library_membership()
    first = library.attach(
        users[0].pk, "RACE-002", source="jable", access_scope="public"
    )
    _race(
        monkeypatch,
        [
            lambda lib: lib.release(users[0].pk, first["entry_id"], expected_version=1),
            lambda lib: lib.attach(
                users[1].pk, "RACE-002", source="jable", access_scope="public"
            ),
        ],
    )
    pool = ResourcePoolEntry.objects.get()
    assert pool.state == "preparing" and pool.gc_after is None
    assert list(pool.memberships.values_list("user_id", flat=True)) == [users[1].pk]
