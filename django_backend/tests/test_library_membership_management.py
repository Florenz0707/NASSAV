"""Own holds remain manageable when formal assets are unavailable."""

import pytest
from django.test import override_settings
from rest_framework.test import APIClient
from nassav.library_models import ResourcePoolEntry, UserLibraryEntry
from nassav.library_catalog import list_memberships, own_entry
from nassav.library_membership import LibraryNotFound
from nassav.models import AVResource
from test_version_publication import environment as environment

pytestmark = pytest.mark.django_db
PATH = "/nassav/api/library/memberships"


@pytest.fixture
def holdings(environment, settings):
    settings.SHARED_LIBRARY_ENABLED = True
    users, _, _ = environment
    for index in range(3):
        resource = AVResource.objects.create(
            avid=f"MANAGE-{index}", original_title="restricted-secret", source="Jable"
        )
        pool = ResourcePoolEntry.objects.create(
            canonical_avid=resource.avid,
            resource=resource,
            state="ready",
            is_available=index != 0,
        )
        UserLibraryEntry.objects.create(
            user=users[0] if index < 2 else users[1],
            pool=pool,
            state="active" if index != 1 else "pending",
        )
    return users


def test_management_lists_only_own_ids_without_bypassing_asset_authorization(holdings):
    users = holdings
    client = APIClient()
    client.force_login(users[0])
    with override_settings(NASSAV_OPERATOR_USERNAME=users[0].username):
        response = client.get(PATH)
    assert response.status_code == 200
    rows = response.data["data"]
    assert {row["avid"] for row in rows} == {"MANAGE-0", "MANAGE-1"}
    assert all(
        set(row)
        == {
            "avid",
            "entry_id",
            "entry_version",
            "membership_state",
            "is_in_my_library",
            "is_available",
            "created_at",
            "updated_at",
        }
        for row in rows
    )
    assert "restricted-secret" not in str(response.data)
    assert (
        response["Cache-Control"] == "private, no-store"
        and "Cookie" in response["Vary"]
    )
    assert (
        next(row for row in rows if row["avid"] == "MANAGE-0")["is_available"] is False
    )
    with pytest.raises(LibraryNotFound):
        own_entry(users[0].pk, avid="MANAGE-0")
    empty, pagination = list_memberships(users[0].pk, {"search": "restricted-secret"})
    assert empty == [] and pagination["total"] == 0


def test_management_filters_and_stable_pagination_do_not_use_hidden_metadata(
    holdings, django_assert_num_queries
):
    user = holdings[0]
    with django_assert_num_queries(2):
        rows, pagination = list_memberships(user.pk, {"page_size": "1"})
    assert len(rows) == 1 and pagination["total"] == 2 and pagination["pages"] == 2
    later, _ = list_memberships(user.pk, {"page_size": "1", "page": "2"})
    assert rows[0]["entry_id"] != later[0]["entry_id"]
    unavailable, _ = list_memberships(user.pk, {"availability": "unavailable"})
    assert [row["avid"] for row in unavailable] == ["MANAGE-0"]
    pending, _ = list_memberships(user.pk, {"state": "pending"})
    assert [row["avid"] for row in pending] == ["MANAGE-1"]


@pytest.mark.parametrize(
    "params",
    [
        {"user_id": "2"},
        {"page_size": "101"},
        {"page": "0"},
        {"ordering": "original_title"},
        {"state": "failed"},
        {"search": "x" * 65},
        {"availability": "all-private"},
        {"page": "bad"},
    ],
)
def test_management_rejects_unbounded_or_foreign_scope_filters(holdings, params):
    with pytest.raises(ValueError):
        list_memberships(holdings[0].pk, params)


def test_management_keeps_admission_and_mode_gates(holdings):
    client = APIClient()
    assert client.get(PATH).status_code == 401
    client.force_login(holdings[1])
    with override_settings(NASSAV_OPERATOR_USERNAME=holdings[0].username):
        assert client.get(PATH).status_code == 403
    client.force_login(holdings[0])
    with override_settings(
        NASSAV_OPERATOR_USERNAME=holdings[0].username, SHARED_LIBRARY_ENABLED=False
    ):
        assert client.get(PATH).status_code == 403


def test_unavailable_own_holding_can_be_released_but_foreign_holding_is_not_addressable(
    holdings,
):
    from uuid import uuid4
    from nassav.models import AVResource

    users = holdings
    own = UserLibraryEntry.objects.get(user=users[0], pool__canonical_avid="MANAGE-0")
    foreign = UserLibraryEntry.objects.get(user=users[1])
    client = APIClient()
    client.force_login(users[0])
    with override_settings(NASSAV_OPERATOR_USERNAME=users[0].username):
        wrong = client.delete(
            f"/nassav/api/library/entries/{foreign.pk}",
            {"expected_version": foreign.version, "request_id": str(uuid4())},
            format="json",
        )
        assert wrong.status_code == 404
        response = client.delete(
            f"/nassav/api/library/entries/{own.pk}",
            {"expected_version": own.version, "request_id": str(uuid4())},
            format="json",
        )
    assert response.status_code == 200
    assert not UserLibraryEntry.objects.filter(pk=own.pk).exists()
    assert UserLibraryEntry.objects.filter(pk=foreign.pk).exists()
    assert AVResource.objects.filter(avid="MANAGE-0").exists()
