"""Authenticated private command surface; ordinary production admission stays closed."""

from uuid import uuid4
from unittest.mock import Mock

import pytest
from django.test import override_settings
from rest_framework.test import APIClient

from nassav import composition
from nassav.library_submission import LibrarySubmission
from nassav.library_models import UserLibraryEntry
from nassav.shared_work_records import DjangoOperationRecords
from nassav.quota_records import DjangoQuotaReservations
from test_version_publication import environment as environment, context, runtime

pytestmark = pytest.mark.django_db


@pytest.fixture
def surface(environment, monkeypatch):
    users, vault, roots = environment
    ctx = context(vault)
    tasks, publication, _, _ = runtime(ctx, roots)
    records = DjangoOperationRecords(
        tasks,
        publication=publication,
        allow_private=True,
        quotas=DjangoQuotaReservations(),
        manage_intents=True,
    )
    sender = Mock()
    submission = LibrarySubmission(
        records, lambda user, source, mode: (ctx, lambda: None), sender
    )
    monkeypatch.setattr(composition, "build_library_submission", lambda: submission)
    monkeypatch.setattr(composition, "build_operation_records", lambda: records)
    return users, records, sender


def command():
    return {
        "avid": "PUB-001",
        "source": "jable",
        "credential_mode": "public",
        "request_id": str(uuid4()),
    }


def test_add_returns_owned_operation_and_other_account_cannot_read_or_cancel(surface):
    users, _, _ = surface
    client = APIClient()
    client.force_login(users[0])
    with override_settings(
        SHARED_LIBRARY_ENABLED=True, NASSAV_OPERATOR_USERNAME=users[0].username
    ):
        response = client.post("/nassav/api/library/entries", command(), format="json")
        assert response.status_code == 202
        data = response.data["data"]
        operation = data["operation"]["operation_id"]
        assert data["membership_state"] == "pending"
        assert response["Cache-Control"] == "private, no-store"
    client.force_login(users[1])
    with override_settings(
        SHARED_LIBRARY_ENABLED=True, NASSAV_OPERATOR_USERNAME=users[1].username
    ):
        assert client.get(f"/nassav/api/my-operations/{operation}").status_code == 404
        assert (
            client.post(
                f"/nassav/api/my-operations/{operation}/cancel",
                {"expected_version": 1, "request_id": str(uuid4())},
                format="json",
            ).status_code
            == 404
        )
        assert (
            client.delete(
                f"/nassav/api/library/entries/{data['entry_id']}",
                {"expected_version": data["entry_version"], "request_id": str(uuid4())},
                format="json",
            ).status_code
            == 404
        )


def test_endpoint_flag_and_operator_admission_still_block_other_users(surface):
    users, _, _ = surface
    client = APIClient()
    client.force_login(users[0])
    with override_settings(
        SHARED_LIBRARY_ENABLED=False, NASSAV_OPERATOR_USERNAME=users[0].username
    ):
        assert (
            client.post(
                "/nassav/api/library/entries", command(), format="json"
            ).status_code
            == 403
        )
    with override_settings(
        SHARED_LIBRARY_ENABLED=True, NASSAV_OPERATOR_USERNAME="another-operator"
    ):
        assert (
            client.post(
                "/nassav/api/library/entries", command(), format="json"
            ).status_code
            == 403
        )


def test_owner_and_unknown_fields_are_rejected_and_replay_preserves_receipt(surface):
    users, _, sender = surface
    client = APIClient()
    client.force_login(users[0])
    body = command()
    with override_settings(
        SHARED_LIBRARY_ENABLED=True, NASSAV_OPERATOR_USERNAME=users[0].username
    ):
        assert (
            client.post(
                "/nassav/api/library/entries",
                {**body, "owner_id": users[1].pk},
                format="json",
            ).status_code
            == 400
        )
        first = client.post("/nassav/api/library/entries", body, format="json")
        second = client.post("/nassav/api/library/entries", body, format="json")
        assert first.data["data"]["operation"] == second.data["data"]["operation"]
        entry = UserLibraryEntry.objects.get()
        release = {"expected_version": entry.version, "request_id": str(uuid4())}
        a = client.delete(
            f"/nassav/api/library/entries/{entry.pk}", release, format="json"
        )
        b = client.delete(
            f"/nassav/api/library/entries/{entry.pk}", release, format="json"
        )
        assert a.status_code == b.status_code == 200 and a.data == b.data
        assert sender.call_count == 2


def test_operation_collection_is_owner_bound_and_bounded(surface):
    users, _, _ = surface
    client = APIClient()
    for user in users:
        client.force_login(user)
        with override_settings(
            SHARED_LIBRARY_ENABLED=True, NASSAV_OPERATOR_USERNAME=user.username
        ):
            assert (
                client.post(
                    "/nassav/api/library/entries", command(), format="json"
                ).status_code
                == 202
            )
    client.force_login(users[0])
    with override_settings(
        SHARED_LIBRARY_ENABLED=True, NASSAV_OPERATOR_USERNAME=users[0].username
    ):
        response = client.get(
            "/nassav/api/my-operations?ordering=-created_at&page_size=1"
        )
        assert response.status_code == 200 and response.data["pagination"]["total"] == 1
        assert len(response.data["data"]) == 1
        assert client.get("/nassav/api/my-operations?page_size=101").status_code == 400
        assert (
            client.get("/nassav/api/my-operations?ordering=created_at").status_code
            == 400
        )


def test_quota_rejection_is_structured_and_does_not_create_ghost_request(surface):
    from nassav.account_models import UserAccount
    from nassav.shared_work_models import UserOperation

    users, _, _ = surface
    UserAccount.objects.filter(user=users[0]).update(max_active_operations=1)
    client = APIClient()
    client.force_login(users[0])
    with override_settings(
        SHARED_LIBRARY_ENABLED=True, NASSAV_OPERATOR_USERNAME=users[0].username
    ):
        assert (
            client.post(
                "/nassav/api/library/entries", command(), format="json"
            ).status_code
            == 202
        )
        response = client.post(
            "/nassav/api/library/entries",
            {**command(), "avid": "PUB-002"},
            format="json",
        )
        assert response.status_code == 403
        assert response.data["data"]["error_code"] == "quota_exceeded"
        assert response.data["data"]["max_active_operations"] == 1
        assert UserOperation.objects.filter(user=users[0]).count() == 1
        assert UserLibraryEntry.objects.filter(user=users[0]).count() == 1


def test_existing_entry_operation_route_rejects_add_action(surface):
    users, _, _ = surface
    client = APIClient()
    client.force_login(users[0])
    with override_settings(
        SHARED_LIBRARY_ENABLED=True, NASSAV_OPERATOR_USERNAME=users[0].username
    ):
        created = client.post(
            "/nassav/api/library/entries", command(), format="json"
        ).data["data"]
        payload = command()
        payload.pop("avid")
        payload.update(
            kind="scrape", action="add", expected_entry_version=created["entry_version"]
        )
        response = client.post(
            f"/nassav/api/library/entries/{created['entry_id']}/operations",
            payload,
            format="json",
        )
        assert response.status_code == 400
