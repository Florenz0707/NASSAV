"""Serialized admin writes, last-admin protection, audit and revocation fences."""

import json
from uuid import uuid5, UUID

from django.contrib.auth import get_user_model
from django.contrib.auth.hashers import make_password
from django.contrib.auth.password_validation import validate_password
from django.contrib.sessions.models import Session
from django.core.exceptions import ValidationError
from django.db import transaction, IntegrityError
from django.db.models import F
from django.utils import timezone
from django.utils.crypto import salted_hmac

from nassav.account_management import AccountConflict
from nassav.account_models import (
    AccountControl,
    AuditEvent,
    UserAccount,
    AdminCommandReceipt,
    QuotaReservation,
)
from nassav.db_retry import retry_sqlite_contention
from nassav.library_models import UserLibraryEntry
from nassav.task_models import TaskJob
from nassav.task_control_rules import allowed_actions
from nassav.playback.models import PlaybackSession


def account_snapshot(row):
    return {
        "user_id": row.user.pk,
        "username": row.user.get_username(),
        "is_active": row.user.is_active,
        "role": row.role,
        "version": row.version,
        "storage_quota_bytes": row.storage_quota_bytes,
        "max_active_operations": row.max_active_operations,
    }


def existing_login_keys(user_id):
    # One-time legacy compatibility scan outside the short admin write transaction.
    # New logins also have indexed user bindings; removed in a coordinated cutover.
    return [
        row.session_key
        for row in Session.objects.filter(expire_date__gt=timezone.now()).iterator(
            chunk_size=200
        )
        if str(row.get_decoded().get("_auth_user_id")) == str(user_id)
    ]


def revoke_logins(user_id, legacy_keys):
    from nassav.account_models import UserLoginSession

    keys = list(
        UserLoginSession.objects.filter(user_id=user_id).values_list(
            "session_id", flat=True
        )
    )
    Session.objects.filter(session_key__in=set(keys) | set(legacy_keys)).delete()
    PlaybackSession.objects.filter(user_id=user_id).exclude(state="closed").update(
        state="closed",
        descriptor={},
        lease_until=None,
        generation=F("generation") + 1,
        version=F("version") + 1,
        updated_at=timezone.now(),
    )


class DjangoAccountCommands:
    def __init__(self, memberships, task_records):
        self.memberships = memberships
        self.task_records = task_records

    def execute(self, actor_id, action, target_id, command):
        password = command.get("password")
        encoded = None
        if password:
            try:
                validate_password(password)
            except ValidationError as error:
                raise ValueError("Password does not meet account policy") from error
            encoded = make_password(password)  # Costly hash stays outside DB locks.
        keys = (
            existing_login_keys(target_id)
            if action in {"bootstrap", "update", "reset_password", "revoke_sessions"}
            else []
        )
        return self._write(actor_id, action, target_id, command, encoded, keys)

    @retry_sqlite_contention
    def _write(self, actor_id, action, target_id, command, encoded, keys):
        digest = salted_hmac(
            "nassav-admin-command",
            json.dumps([action, target_id, command], sort_keys=True),
        ).hexdigest()
        User = get_user_model()
        with transaction.atomic():
            AccountControl.objects.get_or_create(pk=1)
            AccountControl.objects.filter(pk=1).update(version=F("version"))
            for user_id in sorted({actor_id, target_id} - {None}):
                if not User.objects.filter(pk=user_id).update(
                    last_login=F("last_login")
                ):
                    raise LookupError("Account not found")
            actor = User.objects.get(pk=actor_id)
            actor_role = UserAccount.objects.filter(user_id=actor_id).first()
            if not actor.is_active or (
                action != "bootstrap" and (not actor_role or actor_role.role != "admin")
            ):
                raise PermissionError("Application admin required")
            prior = AdminCommandReceipt.objects.filter(
                actor_id=actor_id, request_id=command["request_id"]
            ).first()
            if prior:
                if prior.payload_hash != digest:
                    raise AccountConflict("request_id_conflict")
                return prior.result
            if action == "bootstrap":
                if (
                    actor_id != target_id
                    or UserAccount.objects.filter(
                        role="admin", user__is_active=True
                    ).exists()
                ):
                    raise AccountConflict("bootstrap_not_available")
                row, created = UserAccount.objects.get_or_create(user=actor)
                row.role = "admin"
                if not created:
                    row.version += 1
                row.save(update_fields=["role", "version", "updated_at"])
                revoke_logins(row.user.pk, keys)
            elif action == "create":
                username = command["username"]
                try:
                    user = User(
                        **{getattr(User, "USERNAME_FIELD", "username"): username},
                        password=encoded,
                        is_active=command.get("is_active", True),
                    )
                    user.full_clean()
                    user.save()
                except (IntegrityError, ValidationError) as error:
                    raise AccountConflict("username_conflict_or_invalid") from error
                row = UserAccount.objects.create(
                    user=user, role=command.get("role", "user")
                )
            else:
                row = (
                    UserAccount.objects.select_related("user")
                    .filter(user_id=target_id)
                    .first()
                )
                if row is None:
                    raise LookupError("Managed account not found")
                if row.version != command["expected_version"]:
                    raise AccountConflict("account_version_conflict")
                role = command.get("role", row.role)
                active = command.get("is_active", row.user.is_active)
                if (
                    row.role == "admin"
                    and row.user.is_active
                    and (role != "admin" or not active)
                ):
                    if (
                        UserAccount.objects.filter(role="admin", user__is_active=True)
                        .exclude(pk=row.pk)
                        .count()
                        == 0
                    ):
                        raise AccountConflict("last_admin_protected")
                if action == "update":
                    # Removing ownership happens before disabling the user fence.
                    if row.user.is_active and not active:
                        from nassav.credential_records import revoke_owned_credentials

                        revoke_owned_credentials(row.user.pk)
                        self._detach_owned_work(
                            row.user.pk, actor_id, command["request_id"]
                        )
                    row.role = role
                    row.storage_quota_bytes = command.get(
                        "storage_quota_bytes", row.storage_quota_bytes
                    )
                    row.max_active_operations = command.get(
                        "max_active_operations", row.max_active_operations
                    )
                    row.user.is_active = active
                    row.user.save(update_fields=["is_active"])
                if action == "reset_password":
                    row.user.password = encoded
                    row.user.save(update_fields=["password"])
                if (
                    action in {"reset_password", "revoke_sessions"}
                    or not active
                    or (action == "update" and "role" in command)
                ):
                    revoke_logins(row.user.pk, keys)
                row.version += 1
                row.save()
            result = account_snapshot(row)
            AdminCommandReceipt.objects.create(
                actor_id=actor_id,
                request_id=command["request_id"],
                payload_hash=digest,
                result=result,
            )
            AuditEvent.objects.create(
                actor_id=actor_id,
                request_id=command["request_id"],
                action=f"account.{action}",
                object_id=str(row.user.pk),
                reason=command["reason"],
                payload_hash=digest,
                result={"status": "succeeded", "version": row.version},
            )
            return result

    def _detach_owned_work(self, user_id, actor_id, request_id):
        from datetime import timedelta

        entries = list(
            UserLibraryEntry.objects.filter(user_id=user_id)
            .select_related("pool")
            .order_by("pool__canonical_avid")
        )
        for entry in entries:
            self.memberships.release(
                user_id, entry.pk, entry.version, timedelta(hours=24)
            )
        QuotaReservation.objects.filter(user_id=user_id, state="held").update(
            state="released", updated_at=timezone.now()
        )
        # Membership release detached only this user's shared demand. Single-owner
        # legacy work still needs its original control protocol independently.
        jobs = (
            TaskJob.objects.filter(owner_id=user_id)
            .exclude(state__in=["succeeded", "failed", "cancelled"])
            .order_by("pk")
        )
        for job in jobs.select_for_update():
            if "cancel" in allowed_actions(job.state, job.cleanup_state):
                self.task_records.request(
                    str(job.pk),
                    "cancel",
                    expected_version=job.version,
                    request_id=str(uuid5(UUID(request_id), str(job.pk))),
                    actor_id=actor_id,
                    allow_all=True,
                )
        from nassav.recommendation_models import RecommendationJob

        RecommendationJob.objects.filter(
            owner_id=user_id, state__in=["queued", "running"]
        ).update(
            state="cancelled",
            result=None,
            version=F("version") + 1,
            updated_at=timezone.now(),
            message="账号已停用",
        )
