"""User-fenced logical storage/operation reservations; no automatic expiry refunds."""

from uuid import UUID

from django.db import transaction
from django.db.models import Sum

from nassav.account_models import UserAccount, QuotaReservation
from nassav.account_management import AccountConflict
from nassav.db_retry import retry_sqlite_contention
from nassav.library_models import UserLibraryEntry, ResourcePoolEntry
from nassav.personal_state import lock_user


def logical_used_bytes(user_id):
    return (
        UserLibraryEntry.objects.filter(
            user_id=user_id,
            state="active",
            pool__resource__file_exists=True,
            pool__resource__file_size__gt=0,
        ).aggregate(total=Sum("pool__resource__file_size"))["total"]
        or 0
    )


class DjangoQuotaReservations:
    @retry_sqlite_contention
    def reserve(self, user_id, pool_id, request_id, amount_bytes):
        if type(user_id) is not int or user_id < 1:
            raise ValueError("Invalid user")
        if (
            type(amount_bytes) is not int
            or not 0 <= amount_bytes <= 9223372036854775807
        ):
            raise ValueError("Invalid quota amount")
        pool_id, request_id = UUID(str(pool_id)), UUID(str(request_id))
        with transaction.atomic():
            lock_user(user_id)
            account = UserAccount.objects.get(user_id=user_id)
            old = QuotaReservation.objects.filter(
                user_id=user_id, request_id=request_id
            ).first()
            if old:
                if old.pool_id != pool_id or old.amount_bytes != amount_bytes:
                    raise AccountConflict("quota_request_id_conflict")
                return {"reservation_id": str(old.pk), "state": old.state}
            pool = ResourcePoolEntry.objects.select_for_update().get(pk=pool_id)
            if not pool.is_available or pool.state in {
                "deleting",
                "cleanup_failed",
                "reclaimed",
            }:
                raise AccountConflict("resource_reclaiming")
            if not UserLibraryEntry.objects.filter(user_id=user_id, pool=pool).exists():
                raise PermissionError("Membership required for quota reservation")
            held = QuotaReservation.objects.filter(user_id=user_id, state="held")
            reserved = held.aggregate(total=Sum("amount_bytes"))["total"] or 0
            if held.count() >= account.max_active_operations or (
                account.storage_quota_bytes is not None
                and logical_used_bytes(user_id) + reserved + amount_bytes
                > account.storage_quota_bytes
            ):
                raise PermissionError("quota_exceeded")
            row = QuotaReservation.objects.create(
                user_id=user_id,
                pool=pool,
                request_id=request_id,
                amount_bytes=amount_bytes,
            )
            return {"reservation_id": str(row.pk), "state": row.state}

    @retry_sqlite_contention
    def release(self, user_id, reservation_id):
        with transaction.atomic():
            lock_user(user_id)
            row = QuotaReservation.objects.get(
                pk=UUID(str(reservation_id)), user_id=user_id
            )
            if row.state != "released":
                row.state = "released"
                row.save(update_fields=["state", "updated_at"])
            return {"reservation_id": str(row.pk), "state": row.state}
