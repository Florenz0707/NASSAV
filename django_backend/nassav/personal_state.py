"""User-owned resource projection and short, restartable state writes."""

from django.contrib.auth import get_user_model
from django.db import transaction
from django.db.models import (
    BooleanField,
    CharField,
    IntegerField,
    OuterRef,
    Subquery,
    Value,
    F,
)
from django.db.models.functions import Coalesce

from nassav.db_retry import retry_sqlite_contention
from nassav.personal_models import UserResourceState


class PersonalStateConflict(Exception):
    def __init__(self, snapshot):
        self.snapshot = snapshot
        super().__init__("个人状态已更新，请重新确认")


def lock_user(user_id):
    # First write serializes absent-row creation and partial patches on SQLite too.
    if (
        not get_user_model()
        .objects.filter(pk=user_id, is_active=True)
        .update(last_login=F("last_login"))
    ):
        raise PermissionError("用户不可用")


def project_personal_state(queryset, user_id):
    states = UserResourceState.objects.filter(
        user_id=user_id, resource_id=OuterRef("pk")
    )
    return queryset.annotate(
        personal_watched=Coalesce(
            Subquery(states.values("watched")[:1]),
            Value(False),
            output_field=BooleanField(),
        ),
        personal_is_favorite=Coalesce(
            Subquery(states.values("is_favorite")[:1]),
            Value(False),
            output_field=BooleanField(),
        ),
        personal_notes=Coalesce(
            Subquery(states.values("notes")[:1]), Value(""), output_field=CharField()
        ),
        personal_state_version=Coalesce(
            Subquery(states.values("version")[:1]),
            Value(0),
            output_field=IntegerField(),
        ),
    )


def state_snapshot(resource, user_id):
    row = UserResourceState.objects.filter(user_id=user_id, resource=resource).first()
    return _snapshot(resource.avid, row)


def _snapshot(avid, row):
    return {
        "avid": avid,
        "watched": row.watched if row else False,
        "is_favorite": row.is_favorite if row else False,
        "notes": row.notes if row else "",
        "state_version": row.version if row else 0,
    }


@retry_sqlite_contention
def update_state(resource, user_id, changes, *, expected_version=None):
    if not changes or set(changes) - {"watched", "is_favorite", "notes"}:
        raise ValueError("未知或空个人状态字段")
    for field in {"watched", "is_favorite"} & set(changes):
        if not isinstance(changes[field], bool):
            raise ValueError("状态必须是布尔值")
    if "notes" in changes and (
        not isinstance(changes["notes"], str) or len(changes["notes"]) > 5000
    ):
        raise ValueError("备注必须是最多5000字符的文本")
    with transaction.atomic():
        lock_user(user_id)
        row = UserResourceState.objects.filter(
            user_id=user_id, resource=resource
        ).first()
        if expected_version is not None and expected_version != (
            row.version if row else 0
        ):
            raise PersonalStateConflict(_snapshot(resource.avid, row))
        if row is None:
            row = UserResourceState(user_id=user_id, resource=resource)
        else:
            row.version += 1
        for field, value in changes.items():
            if field not in {"watched", "is_favorite", "notes"}:
                raise ValueError("未知个人状态字段")
            setattr(row, field, value)
        row.save()
        return _snapshot(resource.avid, row)
