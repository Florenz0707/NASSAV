"""Scoped version ledger consumes the existing asset journal and execution fence."""

import re
from copy import deepcopy
from pathlib import PurePosixPath

from django.db import connection
from django.utils import timezone

from nassav.library_models import ResourcePoolEntry, UserLibraryEntry
from nassav.models import AVResource
from nassav.resource_version_models import ResourceVersion, ResourceVersionPointer
from nassav.resource_version_snapshot import validated_snapshot
from nassav.shared_work_models import SharedWork
from nassav.shared_work import OperationConflict
from nassav.task_models import TaskArtifact, TaskAssetTarget
from nassav.shared_execution_records import SharedPublicationRejected


def pointer_fields(work):
    return {
        "pool_id": work.pool_id,
        "source_name": work.spec["source"],
        "quality": work.spec["quality"],
        "access_scope": work.access_scope,
        "kind": "metadata" if work.spec["kind"] == "scrape" else "video",
    }


class VersionPublications:
    def __init__(self, execution_records):
        self.records = execution_records

    def prepare(self, token):
        def allocate():
            work = SharedWork.objects.get(job_id=token.job_id)
            existing = ResourceVersion.objects.filter(work=work).first()
            if existing is not None:
                return str(existing.pk)
            pointer, _ = ResourceVersionPointer.objects.get_or_create(
                **pointer_fields(work)
            )
            candidate = ResourceVersion.objects.create(
                pool=work.pool,
                pool_generation=work.pool_generation,
                work=work,
                parent_id=pointer.current_id,
                base_pointer_revision=pointer.revision,
                owner_id=self.records.binding["owner_id"],
                kind=pointer.kind,
                source_name=pointer.source_name,
                quality=pointer.quality,
                access_scope=work.access_scope,
                credential_refs=deepcopy(work.credential_refs),
                context_revision=work.spec["context_revision"],
            )
            return str(candidate.pk)

        return self.records.controlled_transaction(token, allocate)

    @staticmethod
    def target(version_id, name):
        from uuid import UUID

        identity = str(UUID(str(version_id)))
        path = PurePosixPath(name)
        if (
            path.is_absolute()
            or not path.parts
            or any(part in {"", ".", ".."} for part in path.parts)
            or "\\" in name
        ):
            raise ValueError("Invalid version asset name")
        return f"versions/{identity}/{path}"

    @staticmethod
    def _manifest(token, version):
        prefix = f"versions/{version.pk}/"
        assets = TaskArtifact.objects.filter(
            job_id=token.job_id, state="committed", target_path__startswith=prefix
        ).order_by("root", "target_path")
        manifest = []
        for asset in assets:
            path = PurePosixPath(asset.target_path)
            allowed = (
                version.kind == "video"
                and asset.root == "video"
                and asset.kind == "video"
            ) or (
                version.kind == "metadata"
                and (asset.root, asset.kind)
                in {("cover", "cover"), ("avatar", "avatar")}
            )
            if (
                not allowed
                or path.is_absolute()
                or ".." in path.parts
                or "\\" in asset.target_path
                or asset.size is None
                or asset.size <= 0
                or re.fullmatch("[0-9a-f]{64}", asset.sha256) is None
            ):
                raise ValueError("Invalid published asset evidence")
            epoch = TaskAssetTarget.objects.get(
                root=asset.root, relative_path=asset.target_path
            )
            if epoch.sha256 != asset.sha256 or str(epoch.marker) != asset.details.get(
                "new_marker"
            ):
                raise ValueError("Published asset ownership changed")
            manifest.append(
                {
                    "root": asset.root,
                    "kind": asset.kind,
                    "path": asset.target_path,
                    "size": asset.size,
                    "sha256": asset.sha256,
                    "marker": str(epoch.marker),
                }
            )
        if version.kind == "video" and (
            len(manifest) != 1 or not manifest[0]["path"].endswith(".mp4")
        ):
            raise ValueError("Verified MP4 publication required")
        return manifest

    def publish(self, token, version_id, metadata):
        """Short persist callback inside TaskAssets.commit; no hash/stat/copy/network.

        Shared records hold source/pool/work/attempt fences; TaskAssets holds the
        task/resource/target file locks. It is not a stand-alone publishing API.
        """
        if not connection.in_atomic_block:
            raise RuntimeError("Version publication requires the execution transaction")
        self.records.check(token)
        work = SharedWork.objects.get(job_id=token.job_id)
        version = ResourceVersion.objects.select_for_update().get(
            pk=version_id, work=work
        )
        if (
            version.state != "staging"
            or version.pool_generation != work.pool_generation
        ):
            raise SharedPublicationRejected("版本已发布或执行代次不匹配")
        metadata = validated_snapshot(metadata, work.pool.canonical_avid)
        pointer = ResourceVersionPointer.objects.select_for_update().get(
            **pointer_fields(work)
        )
        if (
            pointer.current_id != version.parent_id
            or pointer.revision != version.base_pointer_revision
        ):
            raise SharedPublicationRejected("较新的版本已发布，旧结果不得覆盖")
        manifest = self._manifest(token, version)
        version.metadata, version.manifest = metadata, manifest
        if version.kind == "video":
            version.file_size, version.media_identity = (
                manifest[0]["size"],
                manifest[0]["sha256"],
            )
        version.state, version.published_at = "ready", timezone.now()
        version.save()
        pointer.current = version
        pointer.revision += 1
        pointer.save()
        pool = ResourcePoolEntry.objects.get(pk=work.pool_id)
        if pool.resource_id is None:
            # Canonical anchor only: no private source data enters AVResource.
            pool.resource, _ = AVResource.objects.get_or_create(
                avid=pool.canonical_avid
            )
        pool.state, pool.gc_after = "ready", None
        pool.version += 1
        pool.save(
            update_fields=["resource", "state", "gc_after", "version", "updated_at"]
        )
        return version

    @staticmethod
    def grant_locked(user_id, work, membership_id, *, allow_scope_change=False):
        """Caller holds user -> pool -> work; never recreates membership."""
        version = ResourceVersion.objects.filter(work=work, state="ready").first()
        entry = UserLibraryEntry.objects.filter(
            pk=membership_id, user_id=user_id, pool_id=work.pool_id
        ).first()
        if (
            version is None
            or entry is None
            or version.pool_generation != work.pool_generation
            or (not allow_scope_change and version.access_scope != entry.access_scope)
            or version.access_scope != work.access_scope
            or version.credential_refs != work.credential_refs
            or version.context_revision != work.spec["context_revision"]
            or (version.owner_id is not None and version.owner_id != user_id)
            or (
                not allow_scope_change
                and entry.desired_spec.get("source") != version.source_name
            )
        ):
            raise OperationConflict("publication_not_ready")
        field = "current_version" if version.kind == "metadata" else "video_version"
        setattr(entry, field, version)
        entry.state = "active"
        if version.kind == "metadata":
            entry.desired_spec = {"source": version.source_name}
            entry.access_scope = version.access_scope
        entry.version += 1
        entry.save(
            update_fields=[
                field,
                "state",
                "version",
                "desired_spec",
                "access_scope",
                "updated_at",
            ]
        )
        if version.kind == "metadata":
            from nassav.catalog_projection import sync_entry

            sync_entry(entry)
        return str(version.pk)
