import pytest
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.utils import timezone


@pytest.mark.django_db(transaction=True)
def test_ownership_upgrade_reverse_and_reupgrade_preserve_history_and_relations():
    previous = [("nassav", "0034_user_preferences_json")]
    target = [("nassav", "0035_recommendation_user_ownership")]
    executor = MigrationExecutor(connection)
    latest = executor.loader.graph.leaf_nodes()
    try:
        executor.migrate(previous)
        apps = executor.loader.project_state(previous).apps
        user = apps.get_model("auth", "User").objects.create(username="rec-migration")
        snapshot = apps.get_model("nassav", "RecommendationSnapshot").objects.create(
            recommender_id="r", strategy_id="s", request_fingerprint="f"
        )
        item = apps.get_model("nassav", "RecommendationItem").objects.create(
            snapshot_id=snapshot.pk, avid="MIG-1", rank=1
        )
        feedback = apps.get_model("nassav", "RecommendationFeedback").objects.create(
            item_id=item.pk, avid="MIG-1", feedback="like", feedback_value=1
        )
        block = apps.get_model("nassav", "RecommendationAvidBlocklist").objects.create(
            avid="MIG-1"
        )
        profile = apps.get_model("nassav", "RecommendationSeedProfile").objects.create(
            seed_type="actor", value="Alice", normalized_value="alice", accepted_count=1
        )
        job = apps.get_model("nassav", "RecommendationJob").objects.create(
            owner_id=user.pk, history_generation=1, deadline=timezone.now()
        )
        for _ in range(2):
            executor = MigrationExecutor(connection)
            executor.migrate(target)
            apps = executor.loader.project_state(target).apps
            assert (
                apps.get_model("nassav", "RecommendationJob")
                .objects.get(pk=job.pk)
                .state
                == "cancelled"
            )
            for name, row in [
                ("RecommendationSnapshot", snapshot),
                ("RecommendationAvidBlocklist", block),
                ("RecommendationSeedProfile", profile),
            ]:
                model = apps.get_model("nassav", name)
                assert model.objects.get(pk=row.pk).owner_id is None
                model.objects.filter(pk=row.pk).update(owner_id=user.pk)
            assert (
                apps.get_model("nassav", "RecommendationFeedback")
                .objects.get(pk=feedback.pk)
                .item_id
                == item.pk
            )
            executor = MigrationExecutor(connection)
            executor.migrate(previous)
            apps = executor.loader.project_state(previous).apps
            assert (
                apps.get_model("nassav", "RecommendationSeedProfile")
                .objects.get(pk=profile.pk)
                .accepted_count
                == 1
            )
            assert (
                apps.get_model("nassav", "RecommendationItem")
                .objects.get(pk=item.pk)
                .snapshot_id
                == snapshot.pk
            )
    finally:
        MigrationExecutor(connection).migrate(latest)


@pytest.mark.django_db(transaction=True)
def test_reverse_refuses_to_discard_duplicate_user_blocklists(django_user_model):
    from nassav.models import RecommendationAvidBlocklist

    user = django_user_model.objects.create(username="rec-reverse")
    RecommendationAvidBlocklist.objects.create(avid="DUPLICATE")
    RecommendationAvidBlocklist.objects.create(owner=user, avid="DUPLICATE")
    latest = MigrationExecutor(connection).loader.graph.leaf_nodes()
    try:
        with pytest.raises(RuntimeError, match="不能回退"):
            MigrationExecutor(connection).migrate(
                [("nassav", "0034_user_preferences_json")]
            )
        assert RecommendationAvidBlocklist.objects.count() == 2
    finally:
        # Later expansion migrations already reversed before 0035 refuses.
        # Keep the data assertion, then restore the schema for subsequent tests.
        MigrationExecutor(connection).migrate(latest)
