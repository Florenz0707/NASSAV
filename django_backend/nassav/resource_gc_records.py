"""Pool-fenced GC claims and tombstones. Slow filesystem work belongs to storage."""

from datetime import timedelta
import re
from pathlib import PurePosixPath
from uuid import UUID, uuid4

from django.db import transaction
from django.db.models import F
from django.utils import timezone
from nassav.db_retry import retry_sqlite_contention
from nassav.library_models import ResourcePoolEntry
from nassav.resource_gc_models import ResourceGcJob, ResourceGcAsset
from nassav.resource_gc_policy import blockers
from nassav.resource_gc import (
    GcDeferred,
    GcNotFound,
    GcLeaseLost,
    GcEvidenceError,
    GcToken,
)
from nassav.resource_version_models import ResourceVersion, ResourceVersionPointer
from nassav.task_models import TaskAssetTarget


def manifest_assets(version):
    if not isinstance(version.manifest, list) or len(version.manifest) > 256:
        raise GcEvidenceError("invalid_manifest")
    result, paths = [], set()
    for asset in version.manifest:
        if not isinstance(asset, dict):
            raise GcEvidenceError("invalid_manifest")
        path = asset.get("path")
        root = asset.get("root")
        kind = asset.get("kind")
        allowed = (
            version.kind == "metadata" and root in {"cover", "avatar"} and kind == root
        ) or (version.kind == "video" and root == kind == "video")
        if (
            not allowed
            or not isinstance(path, str)
            or len(path) > 512
            or "\\" in path
            or any(ord(char) < 32 for char in path)
            or any(part in {"", "..", "."} for part in path.split("/"))
            or PurePosixPath(path).parts[:2] != ("versions", str(version.pk))
            or len(PurePosixPath(path).parts) < 3
            or type(asset.get("size")) is not int
            or asset["size"] < 1
            or not isinstance(asset.get("sha256"), str)
            or re.fullmatch("[0-9a-f]{64}", asset["sha256"]) is None
            or (root, path) in paths
        ):
            raise GcEvidenceError("invalid_manifest")
        try:
            marker = UUID(str(asset.get("marker")))
        except (ValueError, TypeError):
            raise GcEvidenceError("invalid_manifest") from None
        paths.add((root, path))
        result.append(
            {
                "version": version,
                "root": root,
                "kind": kind,
                "relative_path": path,
                "size": asset["size"],
                "sha256": asset["sha256"],
                "marker": marker,
            }
        )
    return result


def gc_snapshot(row):
    return {
        "job_id": str(row.pk),
        "pool_id": str(row.pool_id),
        "version_id": str(row.version_id) if row.version_id else None,
        "pool_generation": row.pool_generation,
        "state": row.state,
        "revision": row.revision,
        "error_code": row.error_code,
    }


class DjangoGcRecords:
    LEASE_SECONDS = 30

    def __init__(self, *, now=timezone.now):
        self.now = now

    @staticmethod
    def _pool(pool_id):
        if not ResourcePoolEntry.objects.filter(pk=pool_id).update(
            version=F("version")
        ):
            raise GcNotFound("pool_not_found")
        return (
            ResourcePoolEntry.objects.select_for_update(of=("self",))
            .select_related("resource")
            .get(pk=pool_id)
        )

    @staticmethod
    def _version(pool, version_id):
        if version_id is None:
            return None
        row = ResourceVersion.objects.filter(pk=version_id, pool=pool).first()
        if row is None:
            raise GcNotFound("version_not_found")
        return row

    def preview(self, pool_id, version_id=None):
        pool = ResourcePoolEntry.objects.select_related("resource").get(pk=pool_id)
        version = self._version(pool, version_id)
        reasons = blockers(pool, version, self.now())
        return {
            "pool_id": str(pool.pk),
            "version_id": str(version.pk) if version else None,
            "pool_generation": pool.lifetime_generation,
            "pool_version": pool.version,
            "eligible": not reasons,
            "blockers": reasons,
        }

    @retry_sqlite_contention
    def enqueue(self, pool_id, version_id=None):
        with transaction.atomic():
            pool = self._pool(pool_id)
            version = self._version(pool, version_id)
            key = f"{pool.pk}:{version.pk if version else 'pool'}:{pool.lifetime_generation}"
            previous = ResourceGcJob.objects.filter(active_key=key).first()
            if previous is not None:
                return gc_snapshot(previous)
            reasons = blockers(pool, version, self.now())
            if reasons:
                raise GcDeferred(reasons)
            row = ResourceGcJob.objects.create(
                pool=pool,
                version=version,
                pool_generation=pool.lifetime_generation,
                active_key=key,
            )
            return gc_snapshot(row)

    def intent(self, job_id):
        return ResourceGcJob.objects.select_related("pool", "version").get(pk=job_id)

    @retry_sqlite_contention
    def claim(self, job_id):
        """Internal worker callback: caller already holds task/resource/target locks."""
        candidate = self.intent(job_id)
        with transaction.atomic():
            pool = self._pool(candidate.pool_id)
            job = ResourceGcJob.objects.select_for_update().get(pk=job_id)
            now = self.now()
            if job.state in {"completed", "cancelled"} or (
                job.owner is not None and job.lease_until > now
            ):
                return None
            version = self._version(pool, job.version_id)
            resuming = job.started_at is not None
            if (
                not resuming or version is None
            ) and job.pool_generation != pool.lifetime_generation:
                job.state, job.active_key, job.finished_at = "cancelled", None, now
                job.owner = job.lease_until = None
                job.revision += 1
                job.save()
                return None
            if resuming and (
                (version is None and pool.state not in {"deleting", "cleanup_failed"})
                or (
                    version is not None
                    and version.state not in {"deleting", "cleanup_failed"}
                )
            ):
                raise GcLeaseLost("gc_tombstone_changed")
            reasons = blockers(pool, version, now, job=job, resuming=resuming)
            if reasons:
                job.error_code = reasons[0]
                job.revision += 1
                job.save(update_fields=["error_code", "revision", "updated_at"])
                return None
            if not resuming:
                versions = (
                    [version]
                    if version is not None
                    else list(
                        ResourceVersion.objects.filter(pool=pool)
                        .exclude(state="reclaimed")
                        .order_by("pk")[:65]
                    )
                )
                if len(versions) > 64:
                    raise GcDeferred(["version_batch_limit"])
                assets = []
                for item in versions:
                    plans = manifest_assets(item)
                    if len(assets) + len(plans) > 1024:
                        raise GcDeferred(["asset_batch_limit"])
                    markers = {
                        (row["root"], row["relative_path"]): (
                            row["marker"],
                            row["sha256"],
                        )
                        for row in TaskAssetTarget.objects.filter(
                            root__in={asset["root"] for asset in plans},
                            relative_path__in=[
                                asset["relative_path"] for asset in plans
                            ],
                        ).values("root", "relative_path", "marker", "sha256")
                    }
                    for asset in plans:
                        if markers.get((asset["root"], asset["relative_path"])) != (
                            asset["marker"],
                            asset["sha256"],
                        ):
                            raise GcEvidenceError("asset_marker_changed")
                        assets.append(ResourceGcAsset(job=job, **asset))
                ResourceGcAsset.objects.bulk_create(assets)
                version_ids = [item.pk for item in versions]
                ResourceVersionPointer.objects.filter(
                    pool=pool, current_id__in=version_ids
                ).update(current=None, revision=F("revision") + 1)
                ResourceVersion.objects.filter(pk__in=version_ids).update(
                    state="deleting", gc_after=None
                )
                if version is None:
                    pool.state, pool.gc_after = "deleting", None
                    pool.version += 1
                    pool.save(
                        update_fields=["state", "gc_after", "version", "updated_at"]
                    )
                job.started_at = now
            if resuming:
                versions = ResourceVersion.objects.filter(
                    pool=pool, state="cleanup_failed"
                )
                if version is not None:
                    versions = versions.filter(pk=version.pk)
                versions.update(state="deleting")
                if version is None and pool.state == "cleanup_failed":
                    pool.state = "deleting"
                    pool.version += 1
                    pool.save(update_fields=["state", "version", "updated_at"])
            job.state, job.owner, job.lease_until = (
                "deleting",
                uuid4(),
                now + timedelta(seconds=self.LEASE_SECONDS),
            )
            job.error_code = ""
            job.revision += 1
            job.save()
            return GcToken(job.pk, job.owner, job.pool_generation)

    def _owned(self, token):
        job = ResourceGcJob.objects.select_for_update().get(pk=token.job_id)
        if (
            job.owner != token.owner
            or job.pool_generation != token.pool_generation
            or job.state != "deleting"
            or job.lease_until <= self.now()
        ):
            raise GcLeaseLost("gc_claim_lost")
        return job

    @retry_sqlite_contention
    def check(self, token):
        candidate = self.intent(token.job_id)
        with transaction.atomic():
            pool = self._pool(candidate.pool_id)
            job = self._owned(token)
            if pool.retained:
                raise GcDeferred(["admin_retention"])
            if job.version_id is None and (
                pool.lifetime_generation != token.pool_generation
                or pool.state != "deleting"
            ):
                raise GcLeaseLost("gc_generation_changed")
            if job.lease_until - self.now() < timedelta(seconds=10):
                job.lease_until = self.now() + timedelta(seconds=self.LEASE_SECONDS)
                job.revision += 1
                job.save(update_fields=["lease_until", "revision", "updated_at"])
            return gc_snapshot(job)

    @retry_sqlite_contention
    def fail(self, token, error_code):
        candidate = self.intent(token.job_id)
        with transaction.atomic():
            pool = self._pool(candidate.pool_id)
            job = self._owned(token)
            job.state, job.owner, job.lease_until = "cleanup_failed", None, None
            job.error_code = (
                error_code
                if isinstance(error_code, str)
                and re.fullmatch("[a-z_]{1,64}", error_code)
                else "file_cleanup_failed"
            )
            job.revision += 1
            job.save()
            ids = (
                [job.version_id]
                if job.version_id
                else list(
                    ResourceVersion.objects.filter(
                        pool=pool, state="deleting"
                    ).values_list("pk", flat=True)
                )
            )
            ResourceVersion.objects.filter(pk__in=ids, state="deleting").update(
                state="cleanup_failed"
            )
            if job.version_id is None:
                pool.state = "cleanup_failed"
                pool.version += 1
                pool.save(update_fields=["state", "version", "updated_at"])
            return gc_snapshot(job)

    def assets(self, token, limit=32):
        self.check(token)
        return list(
            ResourceGcAsset.objects.filter(job_id=token.job_id)
            .exclude(state="deleted")
            .order_by("root", "relative_path")
            .values(
                "pk",
                "version_id",
                "root",
                "relative_path",
                "marker",
                "sha256",
                "size",
                "state",
                "fingerprint",
            )[:limit]
        )

    def versions(self, token):
        self.check(token)
        job = self.intent(token.job_id)
        rows = ResourceVersion.objects.filter(pool_id=job.pool_id, state="deleting")
        if job.version_id:
            rows = rows.filter(pk=job.version_id)
        return list(rows.values_list("pk", flat=True))

    @staticmethod
    def _marker(asset):
        if not TaskAssetTarget.objects.filter(
            root=asset.root,
            relative_path=asset.relative_path,
            marker=asset.marker,
            sha256=asset.sha256,
        ).exists():
            raise GcEvidenceError("asset_marker_changed")

    @retry_sqlite_contention
    def verified(self, token, asset_id, fingerprint):
        candidate = self.intent(token.job_id)
        with transaction.atomic():
            self._pool(candidate.pool_id)
            self._owned(token)
            asset = ResourceGcAsset.objects.select_for_update().get(
                pk=asset_id, job_id=token.job_id
            )
            self._marker(asset)
            if asset.state == "deleted" or (
                asset.state == "verified" and asset.fingerprint != fingerprint
            ):
                raise GcEvidenceError("asset_identity_changed")
            asset.state, asset.fingerprint = "verified", dict(fingerprint)
            asset.save(update_fields=["state", "fingerprint", "updated_at"])

    def unlink(self, token, asset_id, remove):
        """Only a checked stat/unlink callback; hash/copy/network must finish first.

        Do not retry this transaction around a filesystem side effect. A crash
        after unlink leaves the previously committed verified journal recoverable.
        """
        candidate = self.intent(token.job_id)
        with transaction.atomic():
            pool = self._pool(candidate.pool_id)
            self._owned(token)
            if pool.retained:
                raise GcDeferred(["admin_retention"])
            asset = ResourceGcAsset.objects.select_for_update().get(
                pk=asset_id, job_id=token.job_id
            )
            if asset.state != "verified":
                raise GcEvidenceError("asset_not_verified")
            self._marker(asset)
            remove()
            TaskAssetTarget.objects.filter(
                root=asset.root, relative_path=asset.relative_path, marker=asset.marker
            ).update(marker=uuid4(), sha256="")
            asset.state = "deleted"
            asset.save(update_fields=["state", "updated_at"])

    @retry_sqlite_contention
    def yield_claim(self, token):
        candidate = self.intent(token.job_id)
        with transaction.atomic():
            self._pool(candidate.pool_id)
            job = self._owned(token)
            job.state, job.owner, job.lease_until = "queued", None, None
            job.revision += 1
            job.save()
            return gc_snapshot(job)

    def complete(self, token):
        candidate = self.intent(token.job_id)
        with transaction.atomic():
            pool = self._pool(candidate.pool_id)
            job = self._owned(token)
            target = self._version(pool, job.version_id)
            reasons = blockers(pool, target, self.now(), job=job, resuming=True)
            if reasons:
                raise GcDeferred(reasons)
            if (
                ResourceGcAsset.objects.filter(job=job)
                .exclude(state="deleted")
                .exists()
            ):
                raise GcEvidenceError("assets_not_deleted")
            versions = ResourceVersion.objects.filter(pool=pool, state="deleting")
            if job.version_id:
                versions = versions.filter(pk=job.version_id)
            versions.update(state="reclaimed", gc_after=None, metadata={})
            if job.version_id is None:
                # No effective readers/sessions survived the protection recheck.
                # Expired/released pins must not PROTECT obsolete session rows.
                from nassav.playback.models import PlaybackSession
                from nassav.resource_version_models import ResourceReadLease

                ResourceReadLease.objects.filter(version__pool=pool).delete()
                if pool.resource_id is not None:
                    PlaybackSession.objects.filter(
                        resource_id=pool.resource_id
                    ).delete()
                    pool.resource.delete()
                pool.resource = None
                pool.state, pool.gc_after = "reclaimed", None
                pool.version += 1
                pool.save(
                    update_fields=[
                        "resource",
                        "state",
                        "gc_after",
                        "version",
                        "updated_at",
                    ]
                )
            job.state, job.owner, job.lease_until, job.active_key = (
                "completed",
                None,
                None,
                None,
            )
            job.finished_at = self.now()
            job.revision += 1
            job.save()
            return gc_snapshot(job)

    def status(self, job_id):
        return gc_snapshot(self.intent(job_id))
