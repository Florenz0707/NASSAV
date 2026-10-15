"""DB-owned recommendation jobs: Celery transports IDs, never business state."""

import logging
from datetime import timedelta
from uuid import uuid4

from django.db import transaction
from django.db.models import F, Q
from django.utils import timezone

from nassav.recommendation_models import RecommendationJob, RecommendationState
from nassav.task_network import TaskNetworkControl, TaskNetworkTimeout
from .execution_budget import RecommendationExecutionBudget
from .data_access import DjangoRecommendationContext
from .workflow import RecommendationManagerError
from nassav.source.search_contracts import SourceSearchError, SourceSearchUnavailable

logger = logging.getLogger(__name__)
BUDGET_SECONDS = 300
ACTIVE = {"queued", "running"}


class RecommendationStopped(Exception):
    pass


def history_generation(user_id=None):
    state, _ = RecommendationState.objects.get_or_create(owner_id=user_id)
    return state.generation


def lock_history(user_id=None):
    """Acquire the shared write fence before any feedback/reset read.

    A write (rather than SELECT FOR UPDATE alone) also serializes SQLite.
    """
    if user_id is not None:
        from nassav.personal_state import lock_user

        lock_user(user_id)
    if not RecommendationState.objects.filter(owner_id=user_id).update(
        generation=F("generation")
    ):
        history_generation(user_id)
        RecommendationState.objects.filter(owner_id=user_id).update(
            generation=F("generation")
        )
    return RecommendationState.objects.get(owner_id=user_id).generation


def fence_history(generation, user_id=None):
    if user_id is not None:
        from nassav.personal_state import lock_user

        lock_user(user_id)
    if not RecommendationState.objects.filter(
        owner_id=user_id, generation=generation
    ).update(generation=F("generation")):
        raise RecommendationStopped("推荐历史已经重置")


def snapshot(job):
    from nassav.discovery_image_handles import recommendation_result

    return {
        "job_id": str(job.pk),
        "version": job.version,
        "state": job.state,
        "message": job.message,
        "result": recommendation_result(job.owner_id, job.result)
        if job.state == "succeeded"
        else None,
        "progress": job.result if job.state == "running" else None,
        "allowed_actions": ["cancel"] if job.state in ACTIVE else [],
        "created_at": job.created_at.isoformat(),
        "updated_at": job.updated_at.isoformat(),
    }


def submit(owner, parameters):
    with transaction.atomic():
        generation = lock_history(owner.pk)
        job = RecommendationJob.objects.create(
            owner=owner,
            parameters=parameters,
            history_generation=generation,
            deadline=timezone.now() + timedelta(seconds=BUDGET_SECONDS),
        )
    dispatch(job.pk)
    return RecommendationJob.objects.get(pk=job.pk)


def dispatch(job_id):
    now = timezone.now()
    claimed = (
        RecommendationJob.objects.filter(pk=job_id, state="queued", deadline__gt=now)
        .filter(Q(dispatch_after__isnull=True) | Q(dispatch_after__lte=now))
        .update(dispatch_after=now + timedelta(seconds=30))
    )
    if not claimed:
        return
    try:
        from nassav.tasks import recommendation_job_task

        recommendation_job_task.apply_async(
            args=(str(job_id),), queue="scrape", expires=BUDGET_SECONDS
        )
    except Exception:
        logger.warning("Recommendation dispatch deferred: %s", job_id)


def cancel(job_id, owner):
    now = timezone.now()
    RecommendationJob.objects.filter(pk=job_id, owner=owner, state__in=ACTIVE).update(
        state="cancelled",
        message="推荐已取消",
        version=F("version") + 1,
        updated_at=now,
    )
    return RecommendationJob.objects.filter(pk=job_id, owner=owner).first()


def recover_expired():
    now = timezone.now()
    RecommendationJob.objects.filter(state__in=ACTIVE, deadline__lte=now).update(
        state="failed",
        message="推荐超时，请重试",
        version=F("version") + 1,
        updated_at=now,
    )


def recover():
    recover_expired()
    now = timezone.now()
    RecommendationJob.objects.exclude(state__in=ACTIVE).filter(
        updated_at__lt=now - timedelta(days=1)
    ).delete()
    for job_id in RecommendationJob.objects.filter(
        state="queued", deadline__gt=now
    ).values_list("pk", flat=True)[:100]:
        dispatch(job_id)


class JobContext(DjangoRecommendationContext):
    def __init__(self, job, token):
        super().__init__(user_id=job.owner_id)
        self.job, self.token = job, token
        self.execution_budget: RecommendationExecutionBudget | None = None

    def report_progress(self, progress):
        if not RecommendationJob.objects.filter(
            pk=self.job.pk,
            state="running",
            execution_owner=self.token,
            deadline__gt=timezone.now(),
        ).update(result=progress, version=F("version") + 1, updated_at=timezone.now()):
            raise RecommendationStopped("推荐执行已失效")

    @transaction.atomic
    def publish_cache(self, operation):
        fence_history(self.job.history_generation, self.job.owner_id)
        if not RecommendationJob.objects.filter(
            pk=self.job.pk,
            state="running",
            execution_owner=self.token,
            deadline__gt=timezone.now(),
        ).update(version=F("version")):
            raise RecommendationStopped("推荐执行已失效")
        return operation()

    def prepare(self, request, recommender_id, strategy_id):
        fingerprint = super().prepare(request, recommender_id, strategy_id)
        request.history_generation = self.job.history_generation
        return fingerprint

    @transaction.atomic
    def persist(self, execution):
        if (
            execution.request.completion_reason == "network_budget"
            and not execution.run.items
        ):
            raise TaskNetworkTimeout("网络预算耗尽且没有合格推荐")
        fence_history(self.job.history_generation, self.job.owner_id)
        updated = RecommendationJob.objects.filter(
            pk=self.job.pk,
            state="running",
            execution_owner=self.token,
            deadline__gt=timezone.now(),
        ).update(version=F("version") + 1)
        if not updated:
            raise RecommendationStopped("推荐执行已失效")
        snapshot_id = super().persist(execution)
        execution.snapshot_id = snapshot_id
        for item in execution.run.items:
            item.snapshot_id = snapshot_id
        RecommendationJob.objects.filter(pk=self.job.pk).update(
            state="succeeded", result=execution.to_dict(), updated_at=timezone.now()
        )
        return snapshot_id


def execute(job_id, *, manager_builder=None):
    token = uuid4()
    now = timezone.now()
    if not RecommendationJob.objects.filter(
        pk=job_id, state="queued", deadline__gt=now
    ).update(
        state="running", execution_owner=token, version=F("version") + 1, updated_at=now
    ):
        return
    job = RecommendationJob.objects.get(pk=job_id)

    def check():
        if not RecommendationJob.objects.filter(
            pk=job_id, state="running", execution_owner=token, owner__is_active=True
        ).exists():
            raise RecommendationStopped("推荐已取消或失效")
        if timezone.now() >= job.deadline:
            raise TaskNetworkTimeout("推荐超时")

    context = JobContext(job, token)
    remaining = max(0, (job.deadline - timezone.now()).total_seconds())
    budget = RecommendationExecutionBudget(remaining, report=context.report_progress)
    context.execution_budget = budget

    def network_check():
        check()
        budget.check()

    control = TaskNetworkControl(network_check, publish_fence=context.publish_cache)
    if manager_builder is None:
        from nassav.composition import build_recommendation_manager

        def default_manager_builder(*, context, control):
            return build_recommendation_manager(
                context=context, control=control, user_id=getattr(job, "owner_id", None)
            )

        manager_builder = default_manager_builder

    try:
        with control.phase(max(0.1, budget.deadline - budget.clock())):
            manager = manager_builder(context=context, control=control)
            manager.recommend(
                strategy_id=job.parameters.get("strategy"),
                request_params=job.parameters,
            )
            check_terminal = RecommendationJob.objects.filter(
                pk=job_id, state="succeeded"
            ).exists()
            if not check_terminal:
                raise RecommendationManagerError("推荐结果未提交")
    except RecommendationStopped:
        RecommendationJob.objects.filter(
            pk=job_id, state="running", execution_owner=token, owner__is_active=True
        ).update(
            state="cancelled",
            message="推荐已取消或历史已重置",
            version=F("version") + 1,
            updated_at=timezone.now(),
        )
    except Exception as error:
        if isinstance(error, TaskNetworkTimeout):
            logger.warning(
                "Recommendation timeout job=%s stage=%s reason=%s "
                "db_remaining_seconds=%.3f network_remaining_seconds=%.3f",
                job_id,
                budget.stage,
                str(error),
                (job.deadline - timezone.now()).total_seconds(),
                budget.deadline - budget.clock(),
            )
            message = "推荐超时，请重试"
        elif isinstance(error, SourceSearchUnavailable):
            message = "推荐来源未启用"
        elif isinstance(error, SourceSearchError):
            message = "推荐来源抓取失败，请稍后重试"
        elif isinstance(error, RecommendationManagerError):
            message = "推荐参数无效"
        else:
            message = "推荐执行失败，请重试"
            logger.exception("Recommendation job failed: %s", job_id)
        RecommendationJob.objects.filter(
            pk=job_id, state="running", execution_owner=token, owner__is_active=True
        ).update(
            state="failed",
            message=message,
            version=F("version") + 1,
            updated_at=timezone.now(),
        )
