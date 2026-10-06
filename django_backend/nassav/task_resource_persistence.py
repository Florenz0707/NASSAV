"""Optimistic resource revision and transactional commit for controlled scrape jobs."""

import hashlib
import json

from nassav.models import AVResource
from nassav.task_resource_events import record_resource_event


def resource_revision(avid: str) -> dict | None:
    resource = AVResource.objects.filter(avid=avid).first()
    if resource is None:
        return None
    return {
        "id": resource.pk,
        "metadata_updated_at": resource.metadata_updated_at.isoformat(),
        "content": hashlib.sha256(
            json.dumps(
                {
                    "metadata": resource.metadata,
                    "original_title": resource.original_title,
                    "source_title": resource.source_title,
                    "m3u8": resource.m3u8,
                    "source": resource.source,
                },
                sort_keys=True,
                ensure_ascii=False,
            ).encode()
        ).hexdigest(),
    }


class TaskResourcePersistence:
    def __init__(self, persistence):
        self.persistence = persistence

    def save(self, token, data, base_revision, action):
        # Caller holds the task DB write fence and the resource file lock.
        list(AVResource.objects.select_for_update().filter(avid=data.avid))
        if resource_revision(data.avid) != base_revision:
            raise ValueError("资源版本已更新，旧刮削检查点不能覆盖它")
        resource = self.persistence.save(data)
        record_resource_event(token.job_id, "added" if action == "add" else "refreshed")
        return resource
