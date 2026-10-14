"""Short fenced credential transactions; encryption and network run outside locks."""

import json
from datetime import timedelta
from uuid import uuid4

from django.contrib.auth import get_user_model
from django.db import transaction, IntegrityError
from django.db.models import F
from django.utils import timezone
from django.utils.crypto import salted_hmac

from nassav.account_models import (
    AccountControl,
    UserAccount,
    AdminCommandReceipt,
    AuditEvent,
)
from nassav.credential_crypto import CredentialUnavailable
from nassav.credential_models import SourceCredential, SourceSessionSnapshot
from nassav.db_retry import retry_sqlite_contention
from nassav.source_credentials import (
    CredentialConflict,
    CredentialReference,
    RefreshClaim,
    credential_context,
    snapshot_context,
    reference_id,
    validate_secret,
)


def reference(row):
    return CredentialReference(
        row.pk,
        row.source_name,
        row.scope,
        row.owner_id,
        row.origin_host,
        row.version,
        row.kind,
    )


def public_credential(row):
    return {
        "id": str(row.pk),
        "source_name": row.source_name,
        "scope": row.scope,
        "kind": row.kind,
        "state": row.state,
        "origin_host": row.origin_host,
        "version": row.version,
        "created_at": row.created_at.isoformat(),
        "updated_at": row.updated_at.isoformat(),
    }


class DjangoCredentialRecords:
    def __init__(self, keyring, origins):
        self.keyring = keyring
        self.origins = dict(origins)

    def resolve(self, source_name, *, user_id=None, credential_id=None):
        """No fallback from a revoked/quarantined personal credential to system."""
        source_name = source_name.lower()
        rows = SourceCredential.objects.filter(source_name=source_name)
        if (
            user_id is not None
            and not get_user_model().objects.filter(pk=user_id, is_active=True).exists()
        ):
            raise PermissionError("Account unavailable")
        if credential_id is not None:
            row = rows.filter(pk=reference_id(credential_id)).first()
            if row is None or (row.scope == "personal" and row.owner_id != user_id):
                raise PermissionError("Credential unavailable")
        else:
            row = (
                rows.filter(scope="personal", owner_id=user_id).first()
                if user_id
                else None
            )
            if row is None:
                row = rows.filter(scope="system").first()
        if row is None:
            return None
        if row.state != "active" or row.origin_host != self.origins.get(source_name):
            raise CredentialUnavailable(
                "Credential is revoked, quarantined or has a different origin"
            )
        # Missing historical keys must fail even when a metadata cache might hit.
        self.keyring.decrypt(
            row.key_id, row.ciphertext, context=credential_context(reference(row))
        )
        return reference(row)

    def secret(self, ref):
        row = SourceCredential.objects.filter(
            pk=ref.id, version=ref.version, state="active", origin_host=ref.origin_host
        ).first()
        if row is None or reference(row) != ref:
            raise CredentialUnavailable("Credential changed")
        if (
            ref.owner_id
            and not get_user_model()
            .objects.filter(pk=ref.owner_id, is_active=True)
            .exists()
        ):
            raise CredentialUnavailable("Credential owner is disabled")
        return self.keyring.decrypt(
            row.key_id, row.ciphertext, context=credential_context(ref)
        )

    def write(
        self,
        actor_id,
        source_name,
        payload,
        *,
        scope="personal",
        credential_id=None,
        revoke=False,
    ):
        if scope not in {"personal", "system"} or not isinstance(payload, dict):
            raise ValueError("Invalid credential command")
        allowed = (
            {"expected_version", "request_id", "reason"}
            if scope == "system"
            else {"expected_version"}
        )
        if not revoke:
            allowed |= {"cookie", "user_agent", "kind"}
        if (
            set(payload) - allowed
            or type(payload.get("expected_version")) is not int
            or not 0 <= payload["expected_version"] < 9223372036854775807
        ):
            raise ValueError("Invalid credential command/version")
        source_name = source_name.lower()
        if source_name not in self.origins:
            raise ValueError("Unknown credential source")
        if scope == "system":
            request_id = reference_id(payload.get("request_id"))
            if not isinstance(payload.get("reason"), str) or payload.get(
                "reason"
            ) not in {"security", "maintenance", "user_request"}:
                raise ValueError("Choose a non-sensitive reason code")
        else:
            request_id = None
        old = SourceCredential.objects.filter(
            source_name=source_name,
            scope=scope,
            owner_id=actor_id if scope == "personal" else None,
        ).first()
        identity = old.pk if old else uuid4()
        if credential_id is not None and (
            old is None or reference_id(credential_id) != old.pk
        ):
            raise LookupError("Credential not found")
        kind = payload.get("kind", "account" if scope == "personal" else "clearance")
        if scope == "system" and kind != "clearance" and not revoke:
            raise ValueError("System credentials require classified clearance cookies")
        ref = CredentialReference(
            identity,
            source_name,
            scope,
            actor_id if scope == "personal" else None,
            self.origins[source_name],
            payload["expected_version"] + 1,
            kind,
        )
        encoded = (
            self.keyring.encrypt(
                validate_secret(
                    {
                        "cookie": payload.get("cookie"),
                        "user_agent": payload.get("user_agent"),
                    },
                    kind=kind,
                ),
                context=credential_context(ref),
            )
            if not revoke
            else ("", "")
        )
        digest = salted_hmac(
            "nassav-source-credential-command",
            json.dumps(
                [source_name, scope, str(credential_id), revoke, payload],
                sort_keys=True,
            ),
        ).hexdigest()
        try:
            return self._write(
                actor_id, ref, payload, revoke, encoded, request_id, digest
            )
        except IntegrityError:
            raise CredentialConflict("Credential was created concurrently") from None

    @retry_sqlite_contention
    def _write(self, actor_id, ref, payload, revoke, encoded, request_id, digest):
        with transaction.atomic():
            if request_id is not None:
                control, _ = AccountControl.objects.get_or_create(pk=1)
                AccountControl.objects.select_for_update().get(pk=control.pk)
            actor = get_user_model().objects.select_for_update().get(pk=actor_id)
            if not actor.is_active:
                raise PermissionError("Account unavailable")
            if ref.scope == "system":
                if not UserAccount.objects.filter(user=actor, role="admin").exists():
                    raise PermissionError("Admin required")
                receipt = AdminCommandReceipt.objects.filter(
                    actor=actor, request_id=request_id
                ).first()
                if receipt:
                    if receipt.payload_hash != digest:
                        raise CredentialConflict("Request ID reused")
                    return receipt.result
            row = (
                SourceCredential.objects.select_for_update()
                .filter(
                    source_name=ref.source_name, scope=ref.scope, owner_id=ref.owner_id
                )
                .first()
            )
            if (row.version if row else 0) != payload["expected_version"] or (
                row is not None and row.pk != ref.id
            ):
                raise CredentialConflict("Credential version conflict")
            if revoke and row is None:
                raise LookupError("Credential not found")
            row = row or SourceCredential(
                id=ref.id,
                source_name=ref.source_name,
                scope=ref.scope,
                owner_id=ref.owner_id,
            )
            row.origin_host, row.kind, row.version = (
                ref.origin_host,
                ref.kind,
                ref.version,
            )
            row.state = "revoked" if revoke else "active"
            row.key_id, row.ciphertext = encoded
            row.revoked_at = timezone.now() if revoke else None
            row.updated_at = timezone.now()
            row.save()
            SourceSessionSnapshot.objects.filter(credential=row).update(
                refresh_owner=None,
                lease_until=None,
                generation=F("generation") + 1,
                ciphertext="",
                key_id="",
                updated_at=timezone.now(),
            )
            result = public_credential(row)
            if request_id is not None:
                AdminCommandReceipt.objects.create(
                    actor=actor,
                    request_id=request_id,
                    payload_hash=digest,
                    result=result,
                )
                AuditEvent.objects.create(
                    actor=actor,
                    request_id=request_id,
                    action="source_credential.revoke"
                    if revoke
                    else "source_credential.write",
                    object_id=str(row.pk),
                    reason=payload["reason"],
                    payload_hash=digest,
                    result=result,
                )
            return result

    def _lock_ref(self, ref):
        if ref.owner_id is not None:
            user = get_user_model().objects.select_for_update().get(pk=ref.owner_id)
            if not user.is_active:
                raise CredentialUnavailable("Credential owner is disabled")
        row = SourceCredential.objects.select_for_update().get(pk=ref.id)
        if row.state != "active" or reference(row) != ref:
            raise CredentialUnavailable("Credential changed")
        return row

    @retry_sqlite_contention
    def claim_refresh(self, ref, *, egress_profile, browser_context, ttl_seconds=60):
        if (
            not isinstance(egress_profile, str)
            or not 1 <= len(egress_profile) <= 64
            or not isinstance(browser_context, str)
            or not 1 <= len(browser_context) <= 64
            or type(ttl_seconds) is not int
            or not 1 <= ttl_seconds <= 120
        ):
            raise ValueError("Invalid refresh context")
        with transaction.atomic():
            credential = self._lock_ref(ref)
            row, _ = SourceSessionSnapshot.objects.get_or_create(
                credential=credential,
                credential_version=ref.version,
                origin_host=ref.origin_host,
                egress_profile=egress_profile,
                browser_context=browser_context,
            )
            row = SourceSessionSnapshot.objects.select_for_update().get(pk=row.pk)
            if row.lease_until and row.lease_until > timezone.now():
                return None
            row.generation += 1
            row.refresh_owner = uuid4()
            row.lease_until = timezone.now() + timedelta(seconds=ttl_seconds)
            row.updated_at = timezone.now()
            row.save()
            return RefreshClaim(
                row.pk, ref, row.generation, row.refresh_owner, snapshot_context(row)
            )

    def publish_refresh(self, claim, secret, *, expires_at, check=lambda: None):
        base = self.secret(claim.credential)
        secret = validate_secret(secret, kind="account")
        # A challenge refresh is not an account-login mutation.
        from nassav.source_credentials import cookie_values, CHALLENGE_COOKIE_NAMES

        original, proposed = (
            cookie_values(base["cookie"]),
            cookie_values(secret["cookie"]),
        )
        if {
            key: value
            for key, value in original.items()
            if key not in CHALLENGE_COOKIE_NAMES
        } != {
            key: value
            for key, value in proposed.items()
            if key not in CHALLENGE_COOKIE_NAMES
        }:
            raise ValueError("Refresh cannot replace account cookies")
        if (
            claim.credential.kind == "account"
            and secret["user_agent"] != base["user_agent"]
        ):
            raise ValueError("Refresh cannot change account User-Agent")
        row = SourceSessionSnapshot.objects.get(pk=claim.snapshot_id)
        encoded = self.keyring.encrypt(
            secret, context=snapshot_context(replace_snapshot_version(row))
        )
        return self._publish_refresh(claim, encoded, expires_at, check)

    @retry_sqlite_contention
    def _publish_refresh(self, claim, encoded, expires_at, check):
        if (
            expires_at is None
            or expires_at <= timezone.now()
            or expires_at > timezone.now() + timedelta(days=1)
        ):
            raise ValueError("Invalid session expiry")
        with transaction.atomic():
            self._lock_ref(claim.credential)
            check()
            row = SourceSessionSnapshot.objects.select_for_update().get(
                pk=claim.snapshot_id
            )
            if (
                row.generation != claim.generation
                or row.refresh_owner != claim.owner
                or not row.lease_until
                or row.lease_until <= timezone.now()
                or snapshot_context(row) != claim.context
            ):
                return False
            row.key_id, row.ciphertext = encoded
            row.version += 1
            row.expires_at, row.verified_at, row.updated_at = (
                expires_at,
                timezone.now(),
                timezone.now(),
            )
            row.refresh_owner, row.lease_until = None, None
            row.save()
            return True

    @retry_sqlite_contention
    def release_refresh(self, claim):
        return SourceSessionSnapshot.objects.filter(
            pk=claim.snapshot_id, generation=claim.generation, refresh_owner=claim.owner
        ).update(refresh_owner=None, lease_until=None)

    def session(self, ref, *, egress_profile, browser_context):
        secret = self.secret(ref)
        row = (
            SourceSessionSnapshot.objects.filter(
                credential_id=ref.id,
                credential_version=ref.version,
                origin_host=ref.origin_host,
                egress_profile=egress_profile,
                browser_context=browser_context,
                expires_at__gt=timezone.now(),
            )
            .exclude(ciphertext="")
            .first()
        )
        if row is None:
            return secret, str(ref.version)
        payload = self.keyring.decrypt(
            row.key_id, row.ciphertext, context=snapshot_context(row)
        )
        # The read must not return an old snapshot after a concurrent manual edit.
        self.secret(ref)
        return payload, f"{ref.version}:{row.version}"


def replace_snapshot_version(row):
    """Copy only for encryption AAD, without mutating the caller's ORM instance."""
    from copy import copy

    target = copy(row)
    target.version += 1
    return target
