"""Opt-in fill of empty history/seeds with existing private AVID blocks."""

from datetime import timedelta
from io import StringIO

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import transaction
from django.utils import timezone

from nassav.models import (
    RecommendationSnapshot,
    RecommendationSeedProfile,
    RecommendationAvidBlocklist,
    RecommendationFeedback,
)
from nassav.recommendation.jobs import fence_history, RecommendationStopped
from nassav.recommendation_models import RecommendationJob, RecommendationState
from test_recommendation_user_isolation import save

pytestmark = pytest.mark.django_db


def setup_import(user):
    snapshot = RecommendationSnapshot.objects.get(pk=save(None))
    item = snapshot.items.get()
    feedback = RecommendationFeedback.objects.create(
        item=item, avid=item.avid, feedback="like", feedback_value=1
    )
    RecommendationSeedProfile.objects.create(
        seed_type="genre", value="Legacy", normalized_value="legacy"
    )
    block = RecommendationAvidBlocklist.objects.create(owner=user, avid="KEEP-001")
    RecommendationState.objects.filter(owner__isnull=True).update(generation=3)
    RecommendationState.objects.create(owner=user, generation=20)
    return snapshot, feedback, block


def command(user, **kw):
    return call_command(
        "import_recommendation_data", username=user.username, stdout=StringIO(), **kw
    )


def test_opt_in_preserves_blocks_relations_and_revokes_both_old_writers(operator_user):
    snapshot, feedback, block = setup_import(operator_user)
    original_block = RecommendationAvidBlocklist.objects.values().get(pk=block.pk)
    command(operator_user, preserve_personal_blocklist=True)
    snapshot.refresh_from_db()
    assert snapshot.owner_id is None
    assert RecommendationState.objects.get(owner=operator_user).generation == 20
    with pytest.raises(CommandError):
        command(operator_user, apply=True)
    command(operator_user, apply=True, preserve_personal_blocklist=True)
    snapshot.refresh_from_db()
    feedback.refresh_from_db()
    assert snapshot.owner_id == operator_user.pk
    assert feedback.item.snapshot_id == snapshot.pk
    assert (
        RecommendationAvidBlocklist.objects.values().get(pk=block.pk) == original_block
    )
    assert not RecommendationSeedProfile.objects.filter(owner__isnull=True).exists()
    assert RecommendationState.objects.get(owner=operator_user).generation == 21
    assert RecommendationState.objects.get(owner__isnull=True).generation == 4
    for owner, generation in [(None, 3), (operator_user.pk, 20)]:
        with pytest.raises(RecommendationStopped), transaction.atomic():
            fence_history(generation, owner)
    command(operator_user, apply=True, preserve_personal_blocklist=True)
    assert RecommendationState.objects.get(owner=operator_user).generation == 21
    assert RecommendationState.objects.get(owner__isnull=True).generation == 4
    assert RecommendationSnapshot.objects.count() == 1
    assert (
        RecommendationAvidBlocklist.objects.values().get(pk=block.pk) == original_block
    )


@pytest.mark.parametrize(
    "conflict", ["history", "seeds", "legacy_blocks", "queued", "running"]
)
def test_opt_in_refuses_other_merges_and_active_jobs_atomically(
    operator_user, conflict
):
    snapshot, _, block = setup_import(operator_user)
    if conflict == "history":
        RecommendationSnapshot.objects.create(
            owner=operator_user, recommender_id="fixture", strategy_id="fixture"
        )
    elif conflict == "seeds":
        RecommendationSeedProfile.objects.create(
            owner=operator_user, seed_type="actor", value="Own", normalized_value="own"
        )
    elif conflict == "legacy_blocks":
        RecommendationAvidBlocklist.objects.create(avid="KEEP-001")
    else:
        RecommendationJob.objects.create(
            owner=operator_user,
            state=conflict,
            history_generation=20,
            deadline=timezone.now() + timedelta(minutes=5),
        )
    with pytest.raises(CommandError):
        command(operator_user, apply=True, preserve_personal_blocklist=True)
    snapshot.refresh_from_db()
    assert snapshot.owner_id is None
    assert (
        RecommendationAvidBlocklist.objects.get(pk=block.pk).owner_id
        == operator_user.pk
    )
    assert RecommendationState.objects.get(owner=operator_user).generation == 20
    assert RecommendationState.objects.get(owner__isnull=True).generation == 3
