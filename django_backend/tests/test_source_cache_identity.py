"""Credential namespaces change without discarding unrelated personal form state."""

from uuid import uuid4
import pytest
from rest_framework.test import APIClient
from test_source_credentials import setup_credentials as setup_credentials, command

pytestmark = pytest.mark.django_db


def test_own_and_system_credentials_invalidate_sources_but_other_private_credentials_do_not(
    setup_credentials, settings, monkeypatch
):
    (first, second), records = setup_credentials
    settings.SOURCE_CREDENTIALS_ENABLED = True
    settings.NASSAV_OPERATOR_USERNAME = first.username
    monkeypatch.setattr("nassav.composition.build_credential_records", lambda: records)
    client = APIClient()
    client.force_login(first)

    def snapshot():
        return client.get("/nassav/api/auth/session").json()["data"]

    records.write(second.pk, "jable", command("other_private=initial"))
    initial = snapshot()
    records.write(second.pk, "jable", command("other_private=value", version=1))
    assert snapshot() == initial
    response = client.post(
        "/nassav/api/me/source-credentials",
        dict(command("own_private=value"), source_name="jable"),
        format="json",
    )
    assert response.status_code == 200
    own = snapshot()
    assert own["cache_identity"] == initial["cache_identity"]
    assert own["source_cache_identity"] != initial["source_cache_identity"]
    assert (
        response.data["data"]["source_cache_identity"] == own["source_cache_identity"]
    )
    assert "own_private" not in str(response.data)
    credential = response.data["data"]
    revoked = client.delete(
        f"/nassav/api/me/source-credentials/{credential['id']}",
        {"expected_version": credential["version"]},
        format="json",
    )
    assert revoked.status_code == 200
    assert (
        snapshot()["source_cache_identity"]
        == revoked.data["data"]["source_cache_identity"]
    )
    assert snapshot()["source_cache_identity"] != own["source_cache_identity"]
    before_public = snapshot()
    records.write(
        first.pk,
        "jable",
        {
            **command("cf_clearance=system-only"),
            "kind": "clearance",
            "request_id": str(uuid4()),
            "reason": "maintenance",
        },
        scope="system",
    )
    after_public = snapshot()
    assert (
        after_public["source_cache_identity"] != before_public["source_cache_identity"]
    )
    assert after_public["cache_identity"] == initial["cache_identity"]
