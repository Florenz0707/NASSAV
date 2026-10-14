from io import StringIO
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError
from rest_framework.test import APIClient

from nassav.models import (
    RecommendationSnapshot,
    RecommendationAvidBlocklist,
    RecommendationSeedProfile,
    UserResourceState,
)
from nassav.recommendation import jobs
from nassav.recommendation.avid_blocklist import DjangoAvidBlocklistRepository
from nassav.recommendation.data_access import DjangoRecommendationContext
from nassav.recommendation.entities import (
    RecommendationCandidate,
    RecommendationExecution,
    RecommendationRequest,
    RecommendationRun,
    RecommendationSeed,
)
from nassav.recommendation.feedback import (
    RecommendationFeedbackRepository,
    RecommendationFeedbackError,
)
from nassav.recommendation.repository import RecommendationSnapshotRepository
from nassav.recommendation.seed_profiles import RecommendationSeedProfileRepository
from nassav.recommendation.seeds import LocalPreferenceSeedProvider
from nassav.personal_preferences import update_preferences

pytestmark = pytest.mark.django_db


@pytest.fixture
def users(django_user_model):
    return [
        django_user_model.objects.create_user(username=name)
        for name in ("alice", "bob")
    ]


def save(user_id, avid="PRIVATE-1"):
    context = DjangoRecommendationContext(user_id=user_id)
    request = RecommendationRequest()
    context.prepare(request, "jable_page_lookup", "local_preference")
    seed = RecommendationSeed("actor", "Alice", 1, "test")
    item = RecommendationCandidate(avid, "Title", "", "", matched_seeds=[seed])
    return context.persist(
        RecommendationExecution(
            "jable_page_lookup",
            "local_preference",
            request,
            RecommendationRun([seed], [item]),
        )
    )


def test_history_feedback_and_blocklists_are_owned_including_legacy(
    users, actor_factory, genre_factory
):
    alice, bob = users
    legacy = save(None, "LEGACY-1")
    aid, bid = save(alice.pk), save(bob.pk)
    feedback = RecommendationFeedbackRepository(alice.pk)
    with pytest.raises(RecommendationFeedbackError):
        RecommendationFeedbackRepository(bob.pk).record_feedback(
            snapshot_id=aid, avid="PRIVATE-1", feedback="like"
        )
    feedback.record_feedback(snapshot_id=aid, avid="PRIVATE-1", feedback="like")
    assert feedback.build_learning_profile().seed_scores["actor:Alice"] > 0
    assert (
        RecommendationFeedbackRepository(bob.pk).build_learning_profile().seed_scores
        == {}
    )
    for user_id in (None, alice.pk, bob.pk):
        DjangoAvidBlocklistRepository(user_id).block(avid="SAME-1", reason="manual")
    assert RecommendationAvidBlocklist.objects.count() == 3
    DjangoAvidBlocklistRepository(alice.pk).unblock(avid="SAME-1")
    assert (
        DjangoAvidBlocklistRepository(bob.pk).list(page=1, page_size=10, search="")[1][
            "total"
        ]
        == 1
    )
    actor, genre = (
        actor_factory(name="Blocked Actor"),
        genre_factory(name="Blocked Genre"),
    )
    profiles = RecommendationSeedProfileRepository(alice.pk)
    profiles.block_actor(actor=actor)
    profiles.block_genre(genre=genre)
    assert profiles.has_blocked_profiles()
    assert not RecommendationSeedProfileRepository(bob.pk).has_blocked_profiles()
    RecommendationSnapshotRepository(alice.pk).reset_state(preserve_blocklist=False)
    assert RecommendationSnapshot.objects.filter(pk=bid).exists()
    assert RecommendationSnapshot.objects.filter(pk=legacy).exists()
    assert not RecommendationSnapshot.objects.filter(pk=aid).exists()
    assert (
        RecommendationSnapshotRepository(bob.pk).build_metrics()["snapshot_count"] == 1
    )


def test_user_reset_fences_only_own_worker_and_cache(users, monkeypatch):
    alice, bob = users
    monkeypatch.setattr(jobs, "dispatch", Mock())
    a_job, b_job = jobs.submit(alice, {}), jobs.submit(bob, {})
    RecommendationSnapshotRepository(alice.pk).reset_state()
    assert jobs.cancel(b_job.pk, alice) is None

    def builder(*, context, control):
        def recommend(**kwargs):
            control.check()
            request = RecommendationRequest()
            context.prepare(request, "jable_page_lookup", "local_preference")
            context.publish_cache(lambda: None)
            context.persist(
                RecommendationExecution(
                    "jable_page_lookup",
                    "local_preference",
                    request,
                    RecommendationRun([], []),
                )
            )

        return SimpleNamespace(recommend=recommend)

    jobs.execute(a_job.pk, manager_builder=builder)
    jobs.execute(b_job.pk, manager_builder=builder)
    a_job.refresh_from_db()
    b_job.refresh_from_db()
    assert a_job.state == "cancelled" and b_job.state == "succeeded"
    assert RecommendationSnapshot.objects.get().owner_id == bob.pk


def test_personal_seed_interactions_do_not_use_configured_operator(
    users, actor_factory, resource_factory
):
    alice, bob = users
    actor = actor_factory(name="Alice")
    resource = resource_factory()
    resource.actors.add(actor)
    UserResourceState.objects.create(user=alice, resource=resource, is_favorite=True)
    provider = LocalPreferenceSeedProvider(only_interacted=True, fallback_to_all=False)
    assert provider.get_seeds(
        RecommendationRequest(user_id=alice.pk, seed_types=["actor"])
    )
    assert (
        provider.get_seeds(RecommendationRequest(user_id=bob.pk, seed_types=["actor"]))
        == []
    )


def test_http_projects_current_owner_and_saved_defaults(
    users, settings, monkeypatch, actor_factory, resource_factory
):
    alice, bob = users
    monkeypatch.setattr(jobs, "dispatch", Mock())
    aid = save(alice.pk)
    actor = actor_factory(name="Alice")
    resource_factory().actors.add(actor)
    RecommendationSeedProfileRepository(alice.pk).block_actor(actor=actor)
    DjangoAvidBlocklistRepository(alice.pk).block(avid="PRIVATE-1", reason="manual")
    update_preferences(
        bob.pk,
        {"recommendation_type_preference": "genre_heavy", "recommendation_limit": 24},
    )
    client = APIClient()
    client.force_login(bob)
    # Admission is changed only in this isolated test; production operator gate remains.
    settings.NASSAV_OPERATOR_USERNAME = bob.username
    assert (
        client.get("/nassav/api/recommendations/metrics").json()["data"][
            "snapshot_count"
        ]
        == 0
    )
    assert client.get("/nassav/api/recommendations/avid-blocklist").json()["data"] == []
    assert not client.get("/nassav/api/actors/").json()["data"][0]["is_blocked"]
    assert (
        client.post(
            "/nassav/api/recommendations/feedback",
            {"snapshot_id": aid, "avid": "PRIVATE-1", "feedback": "like"},
            format="json",
        ).status_code
        == 400
    )
    job = client.post("/nassav/api/recommendations/jobs", {}, format="json").json()[
        "data"
    ]
    row = jobs.RecommendationJob.objects.get(pk=job["job_id"])
    assert (
        row.parameters["type_preference"] == "genre_heavy"
        and row.parameters["limit"] == 24
    )
    settings.NASSAV_OPERATOR_USERNAME = alice.username
    client.force_login(alice)
    assert (
        client.get(f"/nassav/api/recommendations/jobs/{job['job_id']}").status_code
        == 404
    )
    assert (
        client.post(
            f"/nassav/api/recommendations/jobs/{job['job_id']}/cancel",
            {},
            format="json",
        ).status_code
        == 404
    )


def test_legacy_import_dry_run_preserves_relations_and_refuses_merge(operator_user):
    legacy_id = save(None)
    RecommendationSeedProfile.objects.create(
        seed_type="genre", value="Blocked", normalized_value="blocked", is_blocked=True
    )
    RecommendationAvidBlocklist.objects.create(avid="LEGACY-1")
    command = {"username": operator_user.username, "stdout": StringIO()}
    call_command("import_recommendation_data", **command)
    assert RecommendationSnapshot.objects.get(pk=legacy_id).owner_id is None
    call_command("import_recommendation_data", apply=True, **command)
    assert RecommendationSnapshot.objects.get(pk=legacy_id).owner_id == operator_user.pk
    call_command("import_recommendation_data", apply=True, **command)
    assert (
        RecommendationSnapshotRepository(operator_user.pk).build_metrics()[
            "snapshot_count"
        ]
        == 1
    )
    RecommendationAvidBlocklist.objects.create(avid="NEW-LEGACY")
    with pytest.raises(CommandError):
        call_command("import_recommendation_data", apply=True, **command)
    assert RecommendationAvidBlocklist.objects.get(avid="NEW-LEGACY").owner_id is None
