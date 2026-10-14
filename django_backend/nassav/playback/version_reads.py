"""Per-request fixed playback version pin, separate from shared Redis capacity."""

import time
from uuid import uuid4
from loguru import logger
from .policy import PlaybackGatewayError


class PlaybackVersionRead:
    def __init__(self, reads, row, key):
        self.reads, self.user_id, self.key = reads, row.user_id, key
        self.session_id = row.pk
        self.version_id = row.library_grant.get("version_id")
        self.lease = None
        self.renewed_at = 0.0
        self.closed = False

    def check(self):
        if self.closed:
            raise PlaybackGatewayError("version_read_closed", 410)
        if not self.version_id:
            return
        if self.lease is None:
            self.lease = self.reads.pin(
                self.user_id,
                self.key,
                self.version_id,
                uuid4(),
                playback_session_id=self.session_id,
            )
            self.renewed_at = time.monotonic()
        elif time.monotonic() - self.renewed_at >= 20:
            self.lease = self.reads.renew(
                self.user_id,
                self.key,
                self.lease["lease_id"],
                expected_revision=self.lease["revision"],
            )
            self.renewed_at = time.monotonic()
        else:
            self.reads.check(self.user_id, self.key, self.lease["lease_id"])

    def close(self):
        self.closed = True
        lease, self.lease = self.lease, None
        if lease is not None:
            try:
                self.reads.release(self.user_id, self.key, lease["lease_id"])
            except Exception:
                logger.warning(
                    "Playback version pin cleanup denied; bounded TTL retained"
                )
