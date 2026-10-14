"""Per-job publication policies keep network translation outside immutable commits."""

from copy import deepcopy
from pathlib import PurePosixPath
import hashlib

from nassav.resource_version_snapshot import validated_snapshot
from nassav.utils import parse_duration


class VersionedScrapePublication:
    def __init__(self, records, publications, translator_builder):
        self.records, self.publications = records, publications
        self.translator_builder = translator_builder
        self.version_id = None

    def begin(self, token):
        self.version_id = self.publications.prepare(token)

    def target(self, token, root, name, kind):
        if self.version_id is None:
            raise RuntimeError("Publication has not begun")
        if kind == "html":
            return None
        filename = (
            "cover.jpg"
            if kind == "cover"
            else f"avatars/{hashlib.sha256(PurePosixPath(name).stem.encode()).hexdigest()}.jpg"
        )
        return self.publications.target(self.version_id, filename)

    def prepare(self, token, data, control):
        metadata = deepcopy(data.scraped_data or {})
        actors = metadata.get("actors") or list(data.relations.actor_names)
        snapshot = {
            "avid": data.avid,
            "original_title": metadata.get("title") or "",
            "source_title": data.info.source_title or "",
            "translated_title": "",
            "release_date": metadata.get("release_date") or "",
            "duration": parse_duration(
                metadata.get("duration", data.info.duration or 0)
            ),
            "actors": actors,
            "genres": metadata.get("genres") or [],
            "translation_status": "not_requested",
        }
        title = snapshot["original_title"] or snapshot["source_title"]
        if title.strip() and title.strip().upper() != data.avid:
            self.records.checkpoint(token, "translating")
            self.records.translation_transaction(token, "translating", lambda: None)
            # Synchronous network unwinds before the existing workflow acknowledges stops.
            try:
                translated = self.translator_builder(control).translate(title)
                control.check()
                if not translated:
                    raise RuntimeError("Title translation failed before publication")
            except Exception:
                self.records.translation_transaction(token, "failed", lambda: None)
                raise
            snapshot["translated_title"] = translated
            snapshot["translation_status"] = "completed"
            self.records.translation_transaction(token, "completed", lambda: None)
            self.records.checkpoint(token, "translation_completed")
        else:
            self.records.translation_transaction(token, "not_requested", lambda: None)
        return validated_snapshot(snapshot, data.avid)

    def persist(self, token, snapshot, base_revision, action):
        if self.version_id is None:
            raise RuntimeError("Publication has not begun")
        return self.publications.publish(token, self.version_id, snapshot)

    @staticmethod
    def checkpoint(version):
        return {"resource_committed": True, "resource_version": str(version.pk)}


class VersionedDownloadPublication:
    def __init__(self, publications, snapshot):
        self.publications = publications
        self.snapshot = deepcopy(snapshot)
        self.version_id = None

    def begin(self, token):
        self.version_id = self.publications.prepare(token)

    def target(self, token):
        if self.version_id is None:
            raise RuntimeError("Publication has not begun")
        return self.publications.target(self.version_id, "video.mp4")

    def persist(self, token):
        if self.version_id is None:
            raise RuntimeError("Publication has not begun")
        return self.publications.publish(token, self.version_id, self.snapshot)
