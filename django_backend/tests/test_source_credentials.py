"""Secrets never cross owners or survive stale refresh, manual edits or revocation."""

import base64
import json
from datetime import timedelta
from io import StringIO
from uuid import uuid4

import pytest
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from nassav.account_models import UserAccount, AuditEvent
from nassav.credential_crypto import CredentialKeyring, CredentialUnavailable
from nassav.credential_import import import_legacy_credentials
from nassav.credential_models import SourceCredential, SourceSessionSnapshot
from nassav.credential_records import DjangoCredentialRecords
from nassav.credential_rotation import rotate_credentials
from nassav.models import SourceCookie
from nassav.source_credentials import CredentialConflict

pytestmark = pytest.mark.django_db


@pytest.fixture
def setup_credentials():
    users = [
        get_user_model().objects.create_user(username=name)
        for name in ("nassav", "credential-b")
    ]
    UserAccount.objects.create(user=users[0], role="admin")
    UserAccount.objects.create(user=users[1], role="user")
    keyring = CredentialKeyring("k1", {"k1": b"a" * 32})
    return users, DjangoCredentialRecords(keyring, {"jable": "jable.tv"})


def command(cookie="account_session=private-a; cf_clearance=old", version=0):
    return {"cookie": cookie, "user_agent": "fixture-UA", "expected_version": version}


def create_reference(
    records, user, cookie="account_session=private-a; cf_clearance=old"
):
    result = records.write(user.pk, "jable", command(cookie))
    return records.resolve("jable", user_id=user.pk, credential_id=result["id"])


def claim(records, ref):
    return records.claim_refresh(
        ref, egress_profile="route", browser_context="independent-v1"
    )


def publish(
    records,
    lease,
    cookie="account_session=private-a; cf_clearance=new",
    agent="fixture-UA",
):
    return records.publish_refresh(
        lease,
        {"cookie": cookie, "user_agent": agent},
        expires_at=timezone.now() + timedelta(minutes=5),
    )


def test_crypto_context_authentication_missing_keys_and_permissions(tmp_path):
    ring = CredentialKeyring("first", {"first": b"a" * 32})
    key, cipher = ring.encrypt({"cookie": "secret"}, context="owner-a")
    assert "secret" not in cipher
    assert ring.decrypt(key, cipher, context="owner-a") == {"cookie": "secret"}
    for broken, context in ((cipher, "owner-b"), (cipher[:-4] + "AAAA", "owner-a")):
        with pytest.raises(CredentialUnavailable):
            ring.decrypt(key, broken, context=context)
    with pytest.raises(CredentialUnavailable):
        CredentialKeyring("second", {"second": b"b" * 32}).decrypt(
            key, cipher, context="owner-a"
        )
    output = tmp_path / "keys.json"
    call_command(
        "create_source_credential_keyring",
        output=str(output),
        key_id="safe-key",
        stdout=StringIO(),
    )
    assert output.stat().st_mode & 0o777 == 0o600
    assert CredentialKeyring.from_file(output).active_id == "safe-key"
    previous = output.read_bytes()
    with pytest.raises(CommandError):
        call_command(
            "create_source_credential_keyring", output=str(output), key_id="new-key"
        )
    assert output.read_bytes() == previous
    output.chmod(0o644)
    with pytest.raises(CredentialUnavailable):
        CredentialKeyring.from_file(output)


def test_private_references_owner_isolation_and_blind_output(setup_credentials):
    (first, second), records = setup_credentials
    a = create_reference(records, first)
    b = create_reference(records, second, "account_session=private-b")
    assert a.cache_scope != b.cache_scope
    assert records.secret(a)["cookie"].startswith("account_session=private-a")
    assert records.secret(b)["cookie"] == "account_session=private-b"
    assert "cookie" not in json.dumps(
        records.write(first.pk, "jable", command(version=1))
    )
    assert "private-a" not in SourceCredential.objects.get(pk=a.id).ciphertext
    with pytest.raises(PermissionError):
        records.resolve("jable", user_id=second.pk, credential_id=a.id)
    with pytest.raises(CredentialUnavailable):
        records.secret(a)


def test_stale_refresh_and_owner_release_cannot_overwrite_manual_update(
    setup_credentials,
):
    (first, _), records = setup_credentials
    ref = create_reference(records, first)
    lease = claim(records, ref)
    assert claim(records, ref) is None
    records.write(first.pk, "jable", command("account_session=manual", version=1))
    with pytest.raises(CredentialUnavailable):
        publish(records, lease)
    assert records.release_refresh(lease) == 0
    latest = records.resolve("jable", user_id=first.pk)
    assert records.secret(latest)["cookie"] == "account_session=manual"
    snapshot = SourceSessionSnapshot.objects.get(pk=lease.snapshot_id)
    assert not snapshot.ciphertext and snapshot.refresh_owner is None


def test_refresh_account_cookie_preservation_ua_and_context_isolation(
    setup_credentials,
):
    (first, _), records = setup_credentials
    ref = create_reference(records, first)
    lease = claim(records, ref)
    with pytest.raises(ValueError):
        publish(records, lease, cookie="account_session=anonymous; cf_clearance=new")
    with pytest.raises(ValueError):
        publish(records, lease, agent="other-UA")
    assert publish(records, lease)
    assert not publish(records, lease)
    assert records.session(
        ref, egress_profile="route", browser_context="independent-v1"
    )[0]["cookie"].endswith("cf_clearance=new")
    assert records.session(
        ref, egress_profile="different-route", browser_context="independent-v1"
    )[0]["cookie"].endswith("cf_clearance=old")
    next_lease = claim(records, ref)
    assert records.release_refresh(lease) == 0
    assert (
        SourceSessionSnapshot.objects.get(pk=lease.snapshot_id).refresh_owner
        == next_lease.owner
    )


def test_expired_refresh_cannot_publish(setup_credentials):
    (first, _), records = setup_credentials
    ref = create_reference(records, first)
    lease = claim(records, ref)
    SourceSessionSnapshot.objects.filter(pk=lease.snapshot_id).update(
        lease_until=timezone.now() - timedelta(seconds=1)
    )
    assert not publish(records, lease)


@pytest.mark.django_db(transaction=True)
def test_concurrent_refresh_claims_have_one_owner(setup_credentials):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier
    from django.db import close_old_connections

    (first, _), records = setup_credentials
    ref = create_reference(records, first)
    barrier = Barrier(2)

    def acquire():
        close_old_connections()
        try:
            barrier.wait(timeout=10)
            return claim(records, ref)
        finally:
            close_old_connections()

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: acquire(), range(2)))
    owners = [result for result in results if result is not None]
    assert len(owners) == 1
    assert SourceSessionSnapshot.objects.get().refresh_owner == owners[0].owner


def test_revoked_personal_reference_does_not_fall_back_to_system(setup_credentials):
    (first, _), records = setup_credentials
    system = dict(
        command("cf_clearance=system"), request_id=str(uuid4()), reason="maintenance"
    )
    records.write(first.pk, "jable", system, scope="system")
    ref = create_reference(records, first)
    records.write(
        first.pk, "jable", {"expected_version": 1}, credential_id=ref.id, revoke=True
    )
    with pytest.raises(CredentialUnavailable):
        records.resolve("jable", user_id=first.pk)
    assert records.resolve("jable").scope == "system"
    with pytest.raises(CredentialConflict):
        records.write(first.pk, "jable", command(version=1))


def test_disable_owner_rejects_refresh_and_resolution(setup_credentials):
    (first, _), records = setup_credentials
    ref = create_reference(records, first)
    lease = claim(records, ref)
    first.is_active = False
    first.save(update_fields=["is_active"])
    with pytest.raises(CredentialUnavailable):
        publish(records, lease)
    with pytest.raises(PermissionError):
        records.resolve("jable", user_id=first.pk)


@pytest.mark.parametrize(
    "patch",
    [
        {"cookie": "x=bad\r\nAuthorization: leak"},
        {"cookie": "x=1; x=2"},
        {"user_agent": "bad\nUA"},
        {"expected_version": True},
        {"owner_id": 100},
        {"cookie": None},
        {"kind": []},
        {"expected_version": 9223372036854775807},
    ],
)
def test_invalid_secret_and_identity_fields_are_rejected(setup_credentials, patch):
    (first, _), records = setup_credentials
    with pytest.raises(ValueError):
        records.write(first.pk, "jable", command() | patch)
    assert not SourceCredential.objects.exists()


def test_system_mutations_are_admin_audited_idempotent_and_classified(
    setup_credentials,
):
    (first, second), records = setup_credentials
    payload = dict(
        command("cf_clearance=system"), request_id=str(uuid4()), reason="maintenance"
    )
    with pytest.raises(PermissionError):
        records.write(second.pk, "jable", payload, scope="system")
    result = records.write(first.pk, "jable", payload, scope="system")
    assert records.write(first.pk, "jable", payload, scope="system") == result
    assert AuditEvent.objects.count() == 1
    assert "system" not in json.dumps(AuditEvent.objects.first().result.get("cookie"))
    with pytest.raises(CredentialConflict):
        records.write(
            first.pk,
            "jable",
            dict(payload, cookie="cf_clearance=changed"),
            scope="system",
        )
    with pytest.raises(ValueError):
        records.write(
            first.pk,
            "jable",
            dict(payload, request_id=str(uuid4()), cookie="account_session=private"),
            scope="system",
        )


def test_import_preview_quarantines_unknown_and_never_mutates_legacy(setup_credentials):
    (first, _), records = setup_credentials
    SourceCookie.objects.create(
        source_name="Jable",
        cookie="account_session=old-private",
        user_agent="fixture-UA",
    )
    plan = import_legacy_credentials(records, first.pk)
    assert plan[0]["state"] == "quarantined"
    assert not SourceCredential.objects.exists()
    import_legacy_credentials(records, first.pk, apply=True)
    assert SourceCredential.objects.get().state == "quarantined"
    assert SourceCookie.objects.get().cookie == "account_session=old-private"
    assert (
        import_legacy_credentials(records, first.pk, apply=True)[0]["action"]
        == "preserve"
    )
    with pytest.raises(CredentialUnavailable):
        records.resolve("jable")


def test_rotation_preserves_versions_and_old_key_needed_until_batch_finishes(
    setup_credentials,
):
    (first, second), records = setup_credentials
    a = create_reference(records, first)
    create_reference(records, second, "account_session=private-b")
    assert publish(records, claim(records, a))
    updated = DjangoCredentialRecords(
        CredentialKeyring("k2", {"k1": b"a" * 32, "k2": b"b" * 32}), records.origins
    )
    preview = rotate_credentials(updated, first.pk)
    assert preview["nassav_source_credential"]["remaining"] == 2
    assert SourceCredential.objects.filter(key_id="k1").count() == 2
    rotate_credentials(updated, first.pk, apply=True, batch_size=1)
    assert SourceCredential.objects.filter(key_id="k1").count() == 1
    rotate_credentials(updated, first.pk, apply=True)
    assert not SourceCredential.objects.exclude(key_id="k2").exists()
    assert not SourceSessionSnapshot.objects.exclude(key_id="k2").exists()
    final = DjangoCredentialRecords(
        CredentialKeyring("k2", {"k2": b"b" * 32}), records.origins
    )
    assert final.secret(a)["cookie"].startswith("account_session=private-a")
    assert final.session(a, egress_profile="route", browser_context="independent-v1")[
        0
    ]["cookie"].endswith("cf_clearance=new")


def test_http_blind_writes_owner_uuid_and_missing_key_fail_closed(
    setup_credentials, tmp_path
):
    (first, second), records = setup_credentials
    other = create_reference(records, second)
    client = APIClient()
    client.force_authenticate(first)
    keyfile = tmp_path / "key.json"
    keyfile.write_text(
        json.dumps(
            {
                "active_key_id": "k1",
                "keys": {"k1": base64.b64encode(b"a" * 32).decode()},
            }
        )
    )
    keyfile.chmod(0o600)
    base = "/nassav/api/me/source-credentials"
    with override_settings(SOURCE_CREDENTIAL_KEYRING_FILE=str(keyfile)):
        response = client.post(
            base, dict(command(), source_name="jable"), format="json"
        )
        assert response.status_code == 200
        assert response["Cache-Control"] == "no-store"
        assert "private-a" not in response.content.decode()
        assert client.get(f"{base}/{other.id}").status_code == 404
        assert (
            client.delete(
                f"{base}/{other.id}", {"expected_version": 1}, format="json"
            ).status_code
            == 404
        )
        assert client.post(base, [], format="json").status_code == 400
    with override_settings(SOURCE_CREDENTIAL_KEYRING_FILE=str(tmp_path / "missing")):
        assert (
            client.post(
                base, dict(command(version=1), source_name="jable"), format="json"
            ).status_code
            == 503
        )
    client.force_authenticate(second)
    assert client.get(base).status_code == 403
