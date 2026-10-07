from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from django.utils import timezone
from nassav.recommendation import jobs
from nassav.recommendation.entities import (
    RecommendationExecution,
    RecommendationRequest,
    RecommendationRun,
)
from nassav.recommendation_models import RecommendationJob
from nassav.models import RecommendationSnapshot

pytestmark = pytest.mark.django_db
original_dispatch = jobs.dispatch


@pytest.fixture
def owner(django_user_model):
    return django_user_model.objects.create_user(username="recommendation-owner")


@pytest.fixture(autouse=True)
def no_broker(monkeypatch):
    monkeypatch.setattr(jobs, "dispatch", Mock())


def builder(*, context, control):
    def recommend(**kwargs):
        control.check()
        request = RecommendationRequest()
        context.prepare(request, "jable_page_lookup", "local_preference")
        execution = RecommendationExecution(
            "jable_page_lookup", "local_preference", request, RecommendationRun([], [])
        )
        context.persist(execution)

    return SimpleNamespace(recommend=recommend)


def test_worker_commits_snapshot_and_duplicate_delivery_is_ignored(owner):
    job = jobs.submit(owner, {})
    assert job.state == "queued"
    assert RecommendationSnapshot.objects.count() == 0
    jobs.execute(job.pk, manager_builder=builder)
    jobs.execute(
        job.pk, manager_builder=Mock(side_effect=AssertionError("duplicate ran"))
    )
    job.refresh_from_db()
    assert job.state == "succeeded"
    assert job.result["meta"]["snapshot_id"] is not None
    assert RecommendationSnapshot.objects.count() == 1


def test_cancel_during_execution_rejects_result_commit(owner):
    job = jobs.submit(owner, {})

    def cancel_builder(*, context, control):
        jobs.cancel(job.pk, owner)
        return builder(context=context, control=control)

    jobs.execute(job.pk, manager_builder=cancel_builder)
    job.refresh_from_db()
    assert job.state == "cancelled"
    assert RecommendationSnapshot.objects.count() == 0


def test_history_reset_fences_late_worker_and_sync_results(owner):
    from nassav.recommendation.repository import recommendation_snapshot_repository
    from nassav.recommendation.data_access import DjangoRecommendationContext

    context = DjangoRecommendationContext()
    request = RecommendationRequest()
    context.prepare(request, "jable_page_lookup", "local_preference")
    job = jobs.submit(owner, {})

    def reset_builder(*, context, control):
        recommendation_snapshot_repository.reset_state()
        return builder(context=context, control=control)

    jobs.execute(job.pk, manager_builder=reset_builder)
    with pytest.raises(jobs.RecommendationStopped):
        context.persist(
            RecommendationExecution(
                "jable_page_lookup",
                "local_preference",
                request,
                RecommendationRun([], []),
            )
        )
    job.refresh_from_db()
    assert job.state == "cancelled"
    assert RecommendationSnapshot.objects.count() == 0


def test_expired_jobs_fail_and_cannot_execute(owner):
    job = jobs.submit(owner, {})
    RecommendationJob.objects.filter(pk=job.pk).update(
        deadline=timezone.now() - timedelta(seconds=1)
    )
    jobs.recover()
    jobs.execute(
        job.pk, manager_builder=Mock(side_effect=AssertionError("expired ran"))
    )
    job.refresh_from_db()
    assert job.state == "failed"
    assert "超时" in job.message


def test_backend_cancel_is_idempotent_and_owner_scoped(owner, django_user_model):
    stranger = django_user_model.objects.create_user(username="stranger")
    job = jobs.submit(owner, {})
    assert jobs.cancel(job.pk, stranger) is None
    first = jobs.cancel(job.pk, owner)
    second = jobs.cancel(job.pk, owner)
    assert first.version == second.version
    assert first.state == "cancelled"


def test_http_submission_only_queues(api_client):
    response = api_client.post(
        "/nassav/api/recommendations/jobs", {"limit": 12}, format="json"
    )
    assert response.status_code == 202
    job = response.json()["data"]
    assert job["state"] == "queued"
    assert RecommendationSnapshot.objects.count() == 0
    response = api_client.post(
        f"/nassav/api/recommendations/jobs/{job['job_id']}/cancel", {}, format="json"
    )
    assert response.json()["data"]["state"] == "cancelled"


def test_recovery_retries_broker_failure(owner, monkeypatch):
    from nassav.tasks import recommendation_job_task

    monkeypatch.setattr(jobs, "dispatch", original_dispatch)
    publish = Mock(side_effect=ConnectionError("offline"))
    monkeypatch.setattr(recommendation_job_task, "apply_async", publish)
    job = jobs.submit(owner, {})
    assert job.state == "queued"
    RecommendationJob.objects.filter(pk=job.pk).update(
        dispatch_after=timezone.now() - timedelta(seconds=1)
    )
    jobs.recover()
    assert publish.call_count == 2
    assert publish.call_args.kwargs["queue"] == "scrape"


def test_progress_is_versioned_owner_fenced_and_not_a_history_snapshot(owner):
    job = jobs.submit(owner, {})

    def progress_builder(*, context, control):
        context.report_progress({"stage": "details", "verified_count": 2})
        current = RecommendationJob.objects.get(pk=job.pk)
        assert jobs.snapshot(current)["progress"]["verified_count"] == 2
        assert jobs.snapshot(current)["result"] is None
        assert current.version == 3
        assert RecommendationSnapshot.objects.count() == 0
        jobs.cancel(job.pk, owner)
        with pytest.raises(jobs.RecommendationStopped):
            context.report_progress({"stage": "details", "verified_count": 3})
        return builder(context=context, control=control)

    jobs.execute(job.pk, manager_builder=progress_builder)
    job.refresh_from_db()
    assert job.state == "cancelled"


def test_soft_budget_finalizes_partial_with_history_but_empty_partial_fails(owner):
    from nassav.recommendation.entities import RecommendationCandidate

    for items in [[RecommendationCandidate("PARTIAL", "", "", "")], []]:
        job = jobs.submit(owner, {})

        def partial_builder(*, context, control):
            def recommend(**kwargs):
                request = RecommendationRequest(completion_reason="network_budget")
                context.prepare(request, "jable_page_lookup", "local_preference")
                execution = RecommendationExecution(
                    "jable_page_lookup",
                    "local_preference",
                    request,
                    RecommendationRun([], items),
                )
                context.persist(execution)

            return SimpleNamespace(recommend=recommend)

        jobs.execute(job.pk, manager_builder=partial_builder)
        job.refresh_from_db()
        assert job.state == ("succeeded" if items else "failed")
        if items:
            assert job.result["meta"]["partial"]
            assert job.result["meta"]["returned_count"] == 1
            assert job.result["meta"]["completion_reason"] == "network_budget"
    assert RecommendationSnapshot.objects.count() == 1
