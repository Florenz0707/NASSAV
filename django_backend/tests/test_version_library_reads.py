"""Real ORM, encrypted scopes, journaled JPEGs and authenticated private HTTP."""

import hashlib
from uuid import uuid4

import pytest
from django.test import override_settings
from rest_framework.test import APIClient

from nassav.library_catalog import list_entries, own_entry, project
from nassav.library_models import UserLibraryEntry
from nassav.library_membership import LibraryNotFound
from nassav.personal_state import update_state
from nassav.resource_version_models import ResourceReadLease, ResourceVersion
from nassav.task_models import TaskAssetTarget
from nassav.version_image_files import asset_identity
from test_version_publication import (
    environment as environment,
    context,
    runtime,
    operation,
    claim,
    publish,
    staged_cover,
)

pytestmark = pytest.mark.django_db(transaction=True)


@pytest.fixture
def published(environment, settings):
    users, vault, roots = environment
    for kind, root in roots.items():
        setattr(settings, f"{kind.upper()}_DIR", root)
    settings.SHARED_LIBRARY_ENABLED = True
    vault.write(
        users[0].pk,
        "jable",
        {
            "expected_version": 0,
            "cookie": "account_session=fixture-a",
            "user_agent": "private-UA",
        },
    )
    entries = []
    for user, ctx, title in (
        (users[0], context(vault, users[0]), "private A title"),
        (users[1], context(vault), "public B title"),
    ):
        tasks, publication, records, assets = runtime(ctx, roots)
        op = operation(user, ctx, records)
        token = claim(tasks, op)
        version = publication.prepare(token)
        publish(
            assets,
            publication,
            token,
            version,
            staged_cover(assets, token),
            title=title,
        )
        tasks.finish(token, "succeeded")
        records.project(user.pk, op["operation_id"])
        entries.append(
            UserLibraryEntry.objects.select_related(
                "pool__resource", "current_version"
            ).get(user=user)
        )
    return users, entries, roots


def client_for(user):
    client = APIClient()
    client.force_login(user)
    return client


def test_library_is_projected_from_own_version_with_batch_personal_flags(
    published, django_assert_num_queries
):
    users, entries, _ = published
    update_state(
        entries[0].pool.resource,
        users[0].pk,
        {"is_favorite": True, "notes": "personal A note"},
    )
    update_state(entries[1].pool.resource, users[1].pk, {"watched": True})
    for user, expected in zip(users, ("private A title", "public B title")):
        with django_assert_num_queries(4):
            data, pagination = list_entries(user.pk, {})
        assert pagination["total"] == 1 and data[0]["source_title"] == expected
        assert data[0]["is_favorite"] == (user == users[0])
        assert data[0]["watched"] == (user == users[1])
        assert (
            "notes" not in data[0]
            and "credential_refs" not in data[0]
            and "m3u8" not in data[0]
        )
        detail = project(
            own_entry(user.pk, entry_id=entries[users.index(user)].pk), detail=True
        )
        assert detail["notes"] == ("personal A note" if user == users[0] else "")
    assert not entries[0].pool.resource.source_title
    assert list_entries(users[1].pk, {"search": "private A"})[1]["total"] == 0
    assert list_entries(users[0].pk, {"search": "private A"})[1]["total"] == 1


def test_http_list_detail_and_preview_use_version_not_canonical_anchor(published):
    users, entries, _ = published
    for user, entry in zip(users, entries):
        client = client_for(user)
        with override_settings(NASSAV_OPERATOR_USERNAME=user.username):
            for path in ("/nassav/api/library/entries", "/nassav/api/resources"):
                response = client.get(path)
                assert response.status_code == 200
                assert (
                    response.data["data"][0]["source_title"]
                    == entry.current_version.metadata["source_title"]
                )
                assert response["Cache-Control"] == "private, no-store"
            detail = client.get(f"/nassav/api/library/entries/{entry.pk}")
            assert detail.status_code == 200 and detail.data["data"]["image_assets"]
            preview = client.get("/nassav/api/resource/PUB-001/preview")
            assert (
                preview.status_code == 200
                and preview.data["data"]["metadata"]["source_title"]
                == entry.current_version.metadata["source_title"]
            )
            metadata = client.get("/nassav/api/resource/metadata?avid=PUB-001")
            assert (
                metadata.status_code == 200
                and metadata.data["data"]["source_title"]
                == entry.current_version.metadata["source_title"]
            )
            other = entries[1 if user == users[0] else 0]
            assert (
                client.get(f"/nassav/api/library/entries/{other.pk}").status_code == 404
            )
            assert (
                client.get("/nassav/api/library/entries?page_size=101").status_code
                == 400
            )
            assert (
                client.get("/nassav/api/resources?ordering=credential_refs").status_code
                == 400
            )


def test_image_stream_has_owned_lease_and_cannot_be_reused_after_release(published):
    users, entries, roots = published
    user, entry = users[0], entries[0]
    client = client_for(user)
    with override_settings(NASSAV_OPERATOR_USERNAME=user.username):
        response = client.get("/nassav/api/resource/cover?avid=PUB-001&size=small")
        assert (
            response.status_code == 200
            and response["Cache-Control"] == "private, no-cache"
        )
        assert "Cookie" in response["Vary"].split(", ")
        assert ResourceReadLease.objects.get().state == "active"
        body = b"".join(response.streaming_content)
        asset = entry.current_version.manifest[0]
        assert hashlib.sha256(body).hexdigest() == asset["sha256"]
        response.close()
        assert ResourceReadLease.objects.get().state == "released"
        UserLibraryEntry.objects.filter(pk=entry.pk).delete()
        assert client.get("/nassav/api/resource/cover?avid=PUB-001").status_code == 404
        assert (roots["cover"] / asset["path"]).is_file()


def test_guessed_asset_id_cross_owner_and_wrong_version_never_leak_bytes(published):
    users, entries, _ = published
    private_asset = asset_identity(entries[0].current_version.manifest[0])
    client = client_for(users[1])
    with override_settings(NASSAV_OPERATOR_USERNAME=users[1].username):
        assert (
            client.get(
                f"/nassav/api/library/entries/{entries[0].pk}/images/{private_asset}"
            ).status_code
            == 404
        )
        assert (
            client.get(
                f"/nassav/api/library/entries/{entries[1].pk}/images/{private_asset}"
            ).status_code
            == 404
        )
        response = client.get(
            f"/nassav/api/library/entries/{entries[1].pk}/images/{asset_identity(entries[1].current_version.manifest[0])}"
        )
        assert response.status_code == 200 and b"".join(response.streaming_content)
        response.close()
    # Even a corrupt cross-owner pointer does not become read authority.
    UserLibraryEntry.objects.filter(pk=entries[1].pk).update(
        current_version=entries[0].current_version
    )
    with pytest.raises(LibraryNotFound):
        own_entry(users[1].pk, entry_id=entries[1].pk)
    assert list_entries(users[1].pk, {})[1]["total"] == 0


@pytest.mark.parametrize(
    "damage", ["marker", "content", "symlink", "parent_symlink", "wrong_namespace"]
)
def test_image_evidence_and_nofollow_paths_reject_replacements(
    published, tmp_path, damage
):
    users, entries, roots = published
    entry, client = entries[0], client_for(users[0])
    version = entry.current_version
    asset = version.manifest[0]
    path = roots["cover"] / asset["path"]
    if damage == "marker":
        TaskAssetTarget.objects.filter(
            root="cover", relative_path=asset["path"]
        ).update(marker=uuid4())
    elif damage == "content":
        data = path.read_bytes()
        path.write_bytes(b"x" + data[1:])
    elif damage == "symlink":
        external = tmp_path / "external.jpg"
        external.write_bytes(path.read_bytes())
        path.unlink()
        path.symlink_to(external)
    elif damage == "parent_symlink":
        directory = path.parent
        moved = directory.with_name("moved")
        directory.rename(moved)
        directory.symlink_to(moved, target_is_directory=True)
    else:
        asset["path"] = f"versions/{uuid4()}/cover.jpg"
        ResourceVersion.objects.filter(pk=version.pk).update(manifest=[asset])
    with override_settings(NASSAV_OPERATOR_USERNAME=users[0].username):
        assert client.get("/nassav/api/resource/cover?avid=PUB-001").status_code == 404
    assert not ResourceReadLease.objects.filter(state="active").exists()


def test_in_flight_image_rechecks_removal_and_closes_lease(published):
    from nassav.resource_reads import ReadLeaseNotFound

    users, entries, _ = published
    client = client_for(users[0])
    with override_settings(NASSAV_OPERATOR_USERNAME=users[0].username):
        response = client.get("/nassav/api/resource/cover?avid=PUB-001")
        UserLibraryEntry.objects.filter(pk=entries[0].pk).delete()
        with pytest.raises(ReadLeaseNotFound):
            b"".join(response.streaming_content)
        response.close()
    assert not ResourceReadLease.objects.filter(state="active").exists()


def test_personal_mutation_rechecks_membership_inside_user_fence(published):
    users, entries, _ = published
    resource = entries[0].pool.resource
    UserLibraryEntry.objects.filter(pk=entries[0].pk).delete()
    with pytest.raises(LibraryNotFound):
        update_state(resource, users[0].pk, {"notes": "cannot write after release"})


def test_pending_entry_does_not_inherit_another_holders_title_or_video(published):
    users, entries, _ = published
    UserLibraryEntry.objects.filter(pk=entries[0].pk).update(
        state="pending", current_version=None
    )
    data, _ = list_entries(users[0].pk, {}, include_pending=True)
    assert data[0]["source_title"] == "" and not data[0]["has_video"]
    assert data[0]["version_id"] is None
    assert (
        list_entries(users[0].pk, {"search": "public B"}, include_pending=True)[1][
            "total"
        ]
        == 0
    )


def test_version_relation_filters_and_video_status_use_exact_own_versions(published):
    users, entries, _ = published
    version = entries[0].current_version
    metadata = {
        **version.metadata,
        "actors": ["Only private actor"],
        "genres": ["Only private genre"],
    }
    ResourceVersion.objects.filter(pk=version.pk).update(metadata=metadata)
    assert list_entries(users[0].pk, {"actor": "private actor"})[1]["total"] == 1
    assert list_entries(users[1].pk, {"actor": "private actor"})[1]["total"] == 0
    assert list_entries(users[0].pk, {"genre": "private genre"})[1]["total"] == 1
    assert list_entries(users[0].pk, {"status": "downloaded"})[1]["total"] == 0
    video = ResourceVersion.objects.create(
        pool=version.pool,
        pool_generation=1,
        kind="video",
        source_name="jable",
        access_scope=version.access_scope,
        owner=users[0],
        context_revision="fixture",
        state="ready",
        published_at=version.published_at,
        file_size=42,
    )
    UserLibraryEntry.objects.filter(pk=entries[0].pk).update(video_version=video)
    assert list_entries(users[0].pk, {"status": "downloaded"})[0][0]["file_size"] == 42
    # Metadata may later change scope; only the owner of the fixed video may read it.
    UserLibraryEntry.objects.filter(pk=entries[1].pk).update(video_version=video)
    assert list_entries(users[1].pk, {"status": "downloaded"})[1]["total"] == 0
    assert not list_entries(users[1].pk, {})[0][0]["has_video"]


@pytest.mark.parametrize("route", ["generic", "version"])
def test_image_revalidation_checks_ownership_before_304_and_releases_lease(
    published, route
):
    users, entries, _ = published
    user, entry = users[0], entries[0]
    asset_id = asset_identity(entry.current_version.manifest[0])
    path = (
        "/nassav/api/resource/cover?avid=PUB-001"
        if route == "generic"
        else f"/nassav/api/library/entries/{entry.pk}/images/{asset_id}"
    )
    client = client_for(user)
    with override_settings(NASSAV_OPERATOR_USERNAME=user.username):
        first = client.get(path)
        etag = first["ETag"]
        assert first["Cache-Control"] == "private, no-cache"
        assert b"".join(first.streaming_content)
        first.close()
        for validator in [etag, etag[2:], f'"other", {etag}', "*"]:
            response = client.get(path, HTTP_IF_NONE_MATCH=validator)
            assert response.status_code == 304
            assert response["ETag"] == etag
            assert response["Cache-Control"] == "private, no-cache"
            assert not response.content
            response.close()
            assert not ResourceReadLease.objects.filter(state="active").exists()
        UserLibraryEntry.objects.filter(pk=entry.pk).delete()
        response = client.get(path, HTTP_IF_NONE_MATCH=etag)
        assert response.status_code == 404
        assert "no-store" in response["Cache-Control"]
