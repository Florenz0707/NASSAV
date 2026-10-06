"""R7 import isolation, registered task compatibility and source error behavior."""

import os
import subprocess
import sys

import pytest
from nassav.recommendation.contracts import (
    CandidateInventory,
    RecommendationSource,
    SeedProvider,
)
from nassav.recommendation.entities import RecommendationRequest, RecommendationSeed
from nassav.recommendation.jable_search import JableSearchRecommender


def test_core_workflows_import_without_framework_or_default_assembly():
    env = os.environ.copy()
    env.pop("DJANGO_SETTINGS_MODULE", None)
    code = """
import sys
from nassav.resource_workflow import ResourceService
from nassav.download_workflow import DownloadUseCase, MockDownloadUseCase
from nassav.translation_workflow import TitleTranslationUseCase
from nassav.recommendation.workflow import RecommenderManager
assert not ({'django', 'celery', 'redis', 'nassav.composition', 'nassav.tasks'} & sys.modules.keys()), sorted(sys.modules)
"""
    result = subprocess.run(
        [sys.executable, "-c", code], env=env, capture_output=True, text=True
    )
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize(
    "task_name,kwargs,command,args",
    [
        (
            "check_videos_consistency",
            {"apply_changes": True, "limit": 5, "report": "/tmp/report"},
            "check_videos_consistency",
            ["--apply", "--limit", "5", "--report", "/tmp/report"],
        ),
        (
            "check_actor_avatars_consistency",
            {"apply_changes": True, "report": "/tmp/report"},
            "check_actor_avatars_consistency",
            ["--apply", "--report", "/tmp/report"],
        ),
        ("backup_avid_list", {"days": 8}, "backup_avid_list", ["--days", "8"]),
        ("backup_database", {"days": 9}, "backup_database", ["--days", "9"]),
        (
            "sync_backups",
            {"target": "/tmp/target", "days": 0},
            "sync_backups",
            ["--target", "/tmp/target", "--days", "0"],
        ),
        ("cleanup_logs", {"days": 10}, "cleanup_logs", ["--days", "10"]),
        (
            "check_resources_consistency",
            {"fix_issues": True, "report": "/tmp/report"},
            "check_resources_consistency",
            ["--apply", "--report", "/tmp/report"],
        ),
    ],
)
def test_maintenance_tasks_keep_serialized_names_and_eager_arguments(
    monkeypatch, task_name, kwargs, command, args
):
    from django_project.celery import app
    from nassav import tasks

    calls = []
    monkeypatch.setattr(
        "django.core.management.call_command", lambda *args: calls.append(args)
    )
    task = getattr(tasks, task_name)
    assert task.name == "nassav.tasks." + task_name
    assert app.tasks[task.name] is task._get_current_object()
    assert task.apply(kwargs=kwargs, throw=True).successful()
    assert calls == [(command, *args)]


def test_download_and_translation_registration_and_routes_are_stable():
    from django_project.celery import app
    from nassav import tasks

    for name in (
        "download_video_task",
        "mock_download_video_task",
        "translate_title_task",
        "batch_translate_titles_task",
    ):
        task = getattr(tasks, name)
        assert task.name == "nassav.tasks." + name
        assert app.tasks[task.name] is task._get_current_object()
        expected_queue = "download" if "download" in name else "default"
        assert app.amqp.router.route({}, task.name)["queue"].name == expected_queue
    assert tasks.download_video_task.max_retries == 3
    assert tasks.download_video_task.default_retry_delay == 60


class Inventory(CandidateInventory):
    def existing(self, avids):
        return set()


class Seeds(SeedProvider):
    def get_seeds(self, request):
        return [RecommendationSeed("genre", "tag", 1, "test")]

    def get_additional_seeds(self, request, *, used_seeds, batch_size):
        return []


class BrokenSource(RecommendationSource):
    def __init__(self):
        self.calls = []

    def search(self, keyword, page=1, *, force_refresh=False):
        self.calls.append((keyword, page, force_refresh))
        raise TypeError("implementation error inside source")

    def get_model_videos(
        self, model_slug, page=1, sort_by="video_viewed", *, force_refresh=False
    ):
        return []

    def get_category_videos(self, category_slug, page=1, *, force_refresh=False):
        return []

    def get_tag_videos(self, tag_slug, page=1, *, force_refresh=False):
        return []

    def discover_hot_items(self, page=1, *, force_refresh=False):
        return []

    def discover_latest_updates(self, page=1, *, force_refresh=False):
        return []

    def get_video_detail(self, avid, detail_url="", *, force_refresh=False):
        return {}


def test_recommendation_does_not_retry_source_implementation_typeerror():
    source = BrokenSource()
    workflow = JableSearchRecommender(source, Seeds(), candidate_inventory=Inventory())
    with pytest.raises(TypeError, match="implementation error"):
        workflow.recommend(
            RecommendationRequest(
                limit=1, discovery_limit=0, force_refresh_external=True
            )
        )
    assert source.calls == [("tag", 1, True)]
