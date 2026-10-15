"""Current-user inventory checks never reveal other holdings or global existence."""

import pytest
from rest_framework.test import APIClient
from django.test import override_settings
from django.db import connection
from django.test.utils import CaptureQueriesContext
from nassav.library_models import ResourcePoolEntry, UserLibraryEntry
from nassav.library_catalog import membership_statuses
from test_version_publication import environment as environment

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def shared_mode(settings):
    settings.SHARED_LIBRARY_ENABLED = True


PATH = "/nassav/api/library/entries/status"


def test_bulk_status_separates_users_pending_and_unavailable_without_resource_metadata(
    environment,
):
    users, _, _ = environment
    pools = [
        ResourcePoolEntry.objects.create(canonical_avid=f"STATUS-{n}", state="ready")
        for n in range(3)
    ]
    first = UserLibraryEntry.objects.create(
        user=users[0], pool=pools[0], state="pending"
    )
    UserLibraryEntry.objects.create(user=users[1], pool=pools[1], state="active")
    UserLibraryEntry.objects.create(user=users[0], pool=pools[2], state="active")
    pools[2].is_available = False
    pools[2].save()
    client = APIClient()
    client.force_login(users[0])
    with override_settings(NASSAV_OPERATOR_USERNAME=users[0].username):
        response = client.post(
            PATH,
            {"avids": [" status-0 ", "STATUS-1", "STATUS-2", "ABSENT-0", "STATUS-0"]},
            format="json",
        )
    assert response.status_code == 200
    assert (
        response["Cache-Control"] == "private, no-store"
        and "Cookie" in response["Vary"]
    )
    rows = response.data["data"]
    assert [row["avid"] for row in rows] == [
        "STATUS-0",
        "STATUS-1",
        "STATUS-2",
        "ABSENT-0",
    ]
    assert (
        rows[0]["entry_id"] == str(first.pk)
        and rows[0]["membership_state"] == "pending"
    )
    assert rows[0]["is_in_my_library"] is True
    assert {key: value for key, value in rows[1].items() if key != "avid"} == {
        key: value for key, value in rows[3].items() if key != "avid"
    }
    assert rows[2]["is_in_my_library"] is True and rows[2]["is_available"] is False
    assert set(rows[0]) == {
        "avid",
        "entry_id",
        "entry_version",
        "membership_state",
        "is_in_my_library",
        "is_available",
    }


def test_large_candidate_check_uses_one_owner_query(environment):
    users, _, _ = environment
    avids = [f"STATUS-{number}" for number in range(100)]
    with CaptureQueriesContext(connection) as captured:
        result = membership_statuses(users[0].pk, avids)
    assert len(captured) == 1 and len(result) == 100
    assert not any(row["is_in_my_library"] for row in result)


@pytest.mark.parametrize(
    "payload",
    [
        [],
        {"avids": "STATUS-1"},
        {"avids": [True]},
        {"avids": ["../bad"]},
        {"avids": ["A-1"] * 101},
        {"avids": [], "user_id": 1},
    ],
)
def test_status_rejects_unbounded_or_owner_injected_payloads(environment, payload):
    users, _, _ = environment
    client = APIClient()
    client.force_login(users[0])
    with override_settings(NASSAV_OPERATOR_USERNAME=users[0].username):
        assert client.post(PATH, payload, format="json").status_code == 400


def test_status_requires_shared_mode_and_keeps_current_admission_closed(environment):
    users, _, _ = environment
    client = APIClient()
    assert client.post(PATH, {"avids": []}, format="json").status_code == 401
    client.force_login(users[1])
    with override_settings(NASSAV_OPERATOR_USERNAME=users[0].username):
        assert (
            client.post(PATH, {"avids": ["PUB-001"]}, format="json").status_code == 403
        )
    client.force_login(users[0])
    with override_settings(
        NASSAV_OPERATOR_USERNAME=users[0].username, SHARED_LIBRARY_ENABLED=False
    ):
        assert client.post(PATH, {"avids": []}, format="json").status_code == 403
