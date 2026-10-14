"""Re-encrypt records using the active key without changing semantic versions."""

from django.contrib.auth import get_user_model
from django.db import transaction

from nassav.account_models import AccountControl, UserAccount, AuditEvent
from django.utils.crypto import salted_hmac
from uuid import uuid4
from nassav.credential_models import SourceCredential, SourceSessionSnapshot
from nassav.source_credentials import (
    CredentialConflict,
    credential_context,
    snapshot_context,
)
from nassav.credential_records import reference


def rotate_credentials(records, actor_id, *, apply=False, batch_size=100):
    if type(batch_size) is not int or not 1 <= batch_size <= 500:
        raise ValueError("Invalid rotation batch size")
    if (
        not get_user_model().objects.filter(pk=actor_id, is_active=True).exists()
        or not UserAccount.objects.filter(user_id=actor_id, role="admin").exists()
    ):
        raise PermissionError("Admin required")
    result = {}
    for model, context in (
        (SourceCredential, lambda row: credential_context(reference(row))),
        (SourceSessionSnapshot, snapshot_context),
    ):
        rows = (
            model.objects.exclude(ciphertext="")
            .exclude(key_id=records.keyring.active_id)
            .order_by("pk")
        )
        count = rows.count()
        result[model._meta.db_table] = {"remaining": count, "rewritten": 0}
        for row in list(rows[:batch_size]):
            secret = records.keyring.decrypt(
                row.key_id, row.ciphertext, context=context(row)
            )
            if not apply:
                continue
            encoded = records.keyring.encrypt(secret, context=context(row))
            with transaction.atomic():
                control, _ = AccountControl.objects.get_or_create(pk=1)
                AccountControl.objects.select_for_update().get(pk=control.pk)
                actor = get_user_model().objects.select_for_update().get(pk=actor_id)
                if (
                    not actor.is_active
                    or not UserAccount.objects.filter(user=actor, role="admin").exists()
                ):
                    raise PermissionError("Admin required")
                changed = model.objects.filter(
                    pk=row.pk,
                    version=row.version,
                    key_id=row.key_id,
                    ciphertext=row.ciphertext,
                ).update(key_id=encoded[0], ciphertext=encoded[1])
                if not changed:
                    raise CredentialConflict(
                        "Credential changed during rotation; retry"
                    )
                AuditEvent.objects.create(
                    actor=actor,
                    request_id=uuid4(),
                    action="source_credential.rotate",
                    object_id=str(row.pk),
                    reason="maintenance",
                    payload_hash=salted_hmac(
                        "nassav-credential-rotate",
                        f"{model._meta.db_table}:{row.pk}:{row.key_id}:{encoded[0]}",
                    ).hexdigest(),
                    result={"table": model._meta.db_table, "rewritten": 1},
                )
                result[model._meta.db_table]["rewritten"] += 1
        result[model._meta.db_table]["remaining"] -= result[model._meta.db_table][
            "rewritten"
        ]
    return result
