"""Table renames retain business rows, relationship rows and migration reversibility."""

import re
from datetime import timedelta
from uuid import uuid4

import pytest
from django.apps import apps as runtime_apps
from django.db import IntegrityError, connection, models, transaction
from django.db.migrations.executor import MigrationExecutor
from django.utils import timezone

OLD = ("nassav", "0027_resource_provider_cache")
NEW = ("nassav", "0028_normalize_table_names")
TABLES = {
    "AVResource": "nassav_av_resource",
    "RecommendationJob": "nassav_recommendation_job",
    "RecommendationState": "nassav_recommendation_state",
    "ResourceMetadataCache": "nassav_resource_metadata_cache",
    "ResourcePlaybackCache": "nassav_resource_playback_cache",
    "TaskArtifact": "nassav_task_artifact",
    "TaskAssetTarget": "nassav_task_asset_target",
    "TaskAttempt": "nassav_task_attempt",
    "TaskCommand": "nassav_task_command",
    "TaskEvent": "nassav_task_event",
    "TaskEventReceipt": "nassav_task_event_receipt",
    "TaskJob": "nassav_task_job",
}


def seed(history):
    def model(name):
        return history.get_model("nassav", name)

    resource = model("AVResource").objects.create(avid="MIG-001", is_favorite=True)
    actor = model("Actor").objects.create(name="migration actor")
    genre = model("Genre").objects.create(name="migration genre")
    resource.actors.add(actor)
    resource.genres.add(genre)
    job = model("TaskJob").objects.create(
        kind="scrape",
        avid=resource.avid,
        action="add",
        state="paused",
        generation=3,
        version=7,
        checkpoint={"source": "fixture"},
        resource_saved=True,
    )
    model("TaskAttempt").objects.create(job=job, generation=3, state="stopped")
    model("TaskArtifact").objects.create(
        job=job, root="cover", relative_path="fixture.html", kind="html"
    )
    model("TaskCommand").objects.create(
        job=job, request_id=uuid4(), action="pause", version=7
    )
    model("TaskAssetTarget").objects.create(root="cover", relative_path="fixture.jpg")
    event = model("TaskEvent").objects.create(job=job, event="resource_saved")
    model("TaskEventReceipt").objects.create(event=event, consumer="fixture")
    user = history.get_model("auth", "User").objects.create(username="migration-user")
    model("RecommendationState").objects.create(generation=5)
    model("RecommendationJob").objects.create(
        owner=user,
        history_generation=5,
        deadline=timezone.now() + timedelta(minutes=5),
        parameters={"limit": 12},
        result={"items": []},
    )
    for name in ("ResourceMetadataCache", "ResourcePlaybackCache"):
        model(name).objects.create(
            avid=resource.avid,
            provider_kind="source",
            provider_name="fixture",
            scope_key="scope",
            variant_key="default",
            generation=2,
            payload={"fixture": True},
        )
    return job.pk


def snapshot(history):
    rows = {}
    for name in TABLES:
        model = history.get_model("nassav", name)
        rows[name] = list(model.objects.order_by("pk").values())
    resource = history.get_model("nassav", "AVResource")
    for field in ("actors", "genres"):
        through = resource._meta.get_field(field).remote_field.through
        rows[field] = list(through.objects.order_by("pk").values())
    return rows


def test_business_models_have_explicit_lower_snake_case_table_names():
    for model in runtime_apps.get_app_config("nassav").get_models():
        assert model._meta.original_attrs.get("db_table")
        assert re.fullmatch(r"[a-z][a-z0-9]*(?:_[a-z0-9]+)*", model._meta.db_table)
    for name, table in TABLES.items():
        assert runtime_apps.get_model("nassav", name)._meta.db_table == table


@pytest.mark.django_db(transaction=True)
def test_table_rename_upgrade_reverse_and_reupgrade_preserve_rows_and_relations():
    executor = MigrationExecutor(connection)
    latest = executor.loader.graph.leaf_nodes()
    try:
        executor.migrate([OLD])
        old_apps = executor.loader.project_state([OLD]).apps
        old_tables = {
            name: old_apps.get_model("nassav", name)._meta.db_table for name in TABLES
        }
        job_id = seed(old_apps)
        expected = snapshot(old_apps)
        for target in (NEW, OLD, NEW):
            executor = MigrationExecutor(connection)
            executor.migrate([target])
            history = executor.loader.project_state([target]).apps
            assert snapshot(history) == expected
            actual_tables = set(connection.introspection.table_names())
            wanted = TABLES if target == NEW else old_tables
            unwanted = old_tables if target == NEW else TABLES
            assert set(wanted.values()) <= actual_tables
            assert set(unwanted.values()).isdisjoint(actual_tables)
            resource = history.get_model("nassav", "AVResource")
            for field in ("actors", "genres"):
                through = resource._meta.get_field(field).remote_field.through
                assert through._meta.db_table in actual_tables
                assert (
                    through.objects.get().avresource_id
                    == expected["AVResource"][0]["id"]
                )
            checked_models = [history.get_model("nassav", name) for name in TABLES]
            checked_models.extend(
                resource._meta.get_field(field).remote_field.through
                for field in ("actors", "genres")
            )
            for model in checked_models:
                with connection.cursor() as cursor:
                    indexes = connection.introspection.get_constraints(
                        cursor, model._meta.db_table
                    )
                for index in model._meta.indexes:
                    assert indexes[index.name]["index"]
                for constraint in model._meta.constraints:
                    assert constraint.name in indexes
                for field in model._meta.local_fields:
                    if isinstance(field, models.ForeignKey):
                        target_key = (
                            field.remote_field.model._meta.db_table,
                            field.target_field.column,
                        )
                        assert any(
                            item["foreign_key"] == target_key
                            and field.column in item["columns"]
                            for item in indexes.values()
                        )
            attempt = history.get_model("nassav", "TaskAttempt")
            with pytest.raises(IntegrityError), transaction.atomic():
                attempt.objects.create(job_id=job_id, generation=3)
    finally:
        MigrationExecutor(connection).migrate(latest)
