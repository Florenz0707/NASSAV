"""Reclamation protections are database facts, never a reference-count guess."""

from django.db.models import Q
from nassav.library_models import UserLibraryEntry
from nassav.resource_version_models import ResourceVersion, ResourceReadLease
from nassav.shared_work_models import WorkSubscription, SharedWork
from nassav.task_models import TaskJob, TaskAttempt, TaskArtifact
from nassav.task_control_rules import TERMINAL_STATES
from nassav.playback.models import PlaybackSession
from nassav.resource_gc_models import ResourceGcJob


def blockers(pool, version, now, *, job=None, resuming=False):
    reasons = []
    if pool.retained:
        reasons.append("admin_retention")
    if not resuming:
        if version is None:
            if pool.state != "pending_gc":
                reasons.append("pool_not_pending_gc")
            deadline = pool.gc_after
        else:
            if pool.state not in {
                "ready",
                "preparing",
                "pending_gc",
            } or version.state not in {"ready", "retired"}:
                reasons.append("version_not_reclaimable")
            deadline = version.gc_after
        if deadline is None or deadline > now:
            reasons.append("grace_period")
    entries = UserLibraryEntry.objects.filter(pool=pool)
    if version is not None:
        entries = entries.filter(
            Q(current_version=version) | Q(video_version=version) | Q(state="pending")
        )
    if entries.exists():
        reasons.append("memberships")
    if SharedWork.objects.filter(pool=pool, active_key__isnull=False).exists():
        reasons.append("active_shared_work")
    if WorkSubscription.objects.filter(work__pool=pool, state="attached").exists():
        reasons.append("subscriptions")
    jobs = TaskJob.objects.filter(avid=pool.canonical_avid)
    if jobs.filter(
        Q(active_key__isnull=False) | ~Q(state__in=TERMINAL_STATES)
    ).exists():
        reasons.append("active_or_paused_task")
    if jobs.exclude(cleanup_state__in=["not_required", "completed"]).exists():
        reasons.append("task_cleanup_pending")
    if (
        TaskAttempt.objects.filter(job__in=jobs)
        .filter(
            Q(state="running") | Q(started_at__isnull=False, stopped_at__isnull=True)
        )
        .exists()
    ):
        reasons.append("writer_stop_unconfirmed")
    if (
        TaskArtifact.objects.filter(job__in=jobs)
        .exclude(state__in=["committed", "deleted"])
        .exists()
    ):
        reasons.append("artifact_recovery_pending")
    leases = ResourceReadLease.objects.filter(
        version__pool=pool,
        state="active",
        expires_at__gt=now,
        absolute_expires_at__gt=now,
    )
    sessions = PlaybackSession.objects.filter(
        state__in=["queued", "resolving", "ready"],
        idle_expires_at__gt=now,
        absolute_expires_at__gt=now,
    )
    if version is not None:
        leases = leases.filter(version=version)
        sessions = sessions.filter(library_grant__version_id=str(version.pk))
    else:
        sessions = (
            sessions.filter(
                Q(library_grant__pool_id=str(pool.pk)) | Q(resource_id=pool.resource_id)
            )
            if pool.resource_id
            else sessions.filter(library_grant__pool_id=str(pool.pk))
        )
    if leases.exists():
        reasons.append("read_leases")
    if sessions.exists():
        reasons.append("playback_sessions")
    other = ResourceGcJob.objects.filter(
        pool=pool, state__in=["deleting", "cleanup_failed"]
    )
    if job is not None:
        other = other.exclude(pk=job.pk)
    if other.exists():
        reasons.append("other_gc_pending")
    if version is None:
        if (
            not resuming
            and ResourceVersion.objects.filter(
                pool=pool, state__in=["ready", "retired"]
            )
            .filter(Q(gc_after__isnull=True) | Q(gc_after__gt=now))
            .exists()
        ):
            reasons.append("version_grace_period")
        if ResourceVersion.objects.filter(
            pool=pool, state__in=["staging", "quarantined"]
        ).exists():
            reasons.append("unverified_versions")
        resource = pool.resource
        if resource is not None and (
            resource.file_exists
            or resource.source_title
            or resource.original_title
            or resource.translated_title
            or resource.actors.exists()
            or resource.genres.exists()
        ):
            reasons.append("legacy_assets_unmapped")
    return reasons
