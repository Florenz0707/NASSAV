"""Explicit old-cookie classification and encrypted import; no automatic cutover."""

from uuid import uuid4

from django.contrib.auth import get_user_model
from django.db import transaction
from django.utils import timezone

from nassav.account_models import AccountControl, UserAccount, AuditEvent
from nassav.credential_models import SourceCredential
from nassav.models import SourceCookie
from nassav.source_credentials import (
    CredentialReference,
    credential_context,
    validate_secret,
)

from django.utils.crypto import salted_hmac
import json


def import_legacy_credentials(records, actor_id, *, apply=False):
    actor = get_user_model().objects.get(pk=actor_id, is_active=True)
    if not UserAccount.objects.filter(user=actor, role="admin").exists():
        raise PermissionError("Admin required")
    inputs = list(SourceCookie.objects.order_by("source_name"))
    plan, prepared = [], []
    for old in inputs:
        source = old.source_name.lower()
        origin = records.origins.get(source)
        if origin is None:
            raise ValueError("Legacy source origin is not configured")
        existing = SourceCredential.objects.filter(
            scope="system", source_name=source
        ).first()
        if existing:
            plan.append(
                {"source_name": source, "action": "preserve", "state": existing.state}
            )
            continue
        payload = {"cookie": old.cookie, "user_agent": old.user_agent or ""}
        kind, state = "clearance", "active"
        try:
            validate_secret(payload, kind="clearance")
        except ValueError:
            # Preserve unknown data encrypted for operator review; never activate it.
            kind, state = "account", "quarantined"
        ref = CredentialReference(uuid4(), source, "system", None, origin, 1, kind)
        encoded = (
            records.keyring.encrypt(payload, context=credential_context(ref))
            if apply
            else None
        )
        prepared.append((old, ref, state, encoded))
        plan.append({"source_name": source, "action": "import", "state": state})
    if not apply:
        return plan
    with transaction.atomic():
        control, _ = AccountControl.objects.get_or_create(pk=1)
        AccountControl.objects.select_for_update().get(pk=control.pk)
        actor = get_user_model().objects.select_for_update().get(pk=actor_id)
        if (
            not actor.is_active
            or not UserAccount.objects.filter(user=actor, role="admin").exists()
        ):
            raise PermissionError("Admin required")
        for old, ref, state, encoded in prepared:
            current = SourceCookie.objects.select_for_update().get(pk=old.pk)
            if (
                current.updated_at != old.updated_at
                or current.cookie != old.cookie
                or current.user_agent != old.user_agent
            ):
                raise ValueError("Legacy cookies changed during import")
            if SourceCredential.objects.filter(
                scope="system", source_name=ref.source_name
            ).exists():
                raise ValueError("System credential changed during import")
            SourceCredential.objects.create(
                id=ref.id,
                source_name=ref.source_name,
                scope="system",
                origin_host=ref.origin_host,
                kind=ref.kind,
                state=state,
                key_id=encoded[0],
                ciphertext=encoded[1],
                updated_at=timezone.now(),
            )
        AuditEvent.objects.create(
            actor=actor,
            request_id=uuid4(),
            action="source_credential.import",
            object_id="legacy_source_cookies",
            reason="maintenance",
            payload_hash=salted_hmac(
                "nassav-credential-import", json.dumps(plan, sort_keys=True)
            ).hexdigest(),
            result={"imported": len(prepared)},
        )
    return plan
