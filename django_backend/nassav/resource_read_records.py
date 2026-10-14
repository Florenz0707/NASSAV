"""User -> pool -> reader fences; no file access, network or broker under locks."""

from datetime import timedelta

from django.contrib.sessions.models import Session
from django.db import transaction
from django.utils import timezone
from django.utils.crypto import salted_hmac

from nassav.account_policy import execution_epoch
from nassav.db_retry import retry_sqlite_contention
from nassav.library_models import ResourcePoolEntry, UserLibraryEntry
from nassav.personal_state import lock_user
from nassav.playback.models import PlaybackSession
from nassav.playback.records import login_hash as playback_login_hash
from nassav.resource_reads import ReadLeaseConflict, ReadLeaseNotFound
from nassav.resource_version_models import ResourceVersion, ResourceReadLease


def binding(key):
    return salted_hmac("nassav-resource-read-login", key).hexdigest()


def snapshot(row):
    return {
        "lease_id": str(row.pk),
        "version_id": str(row.version_id),
        "state": row.state,
        "revision": row.revision,
        "expires_at": row.expires_at.isoformat(),
        "absolute_expires_at": row.absolute_expires_at.isoformat(),
    }


class DjangoReadLeases:
    IDLE_SECONDS = 60
    ASSET_MAX_SECONDS = 120
    PLAYBACK_MAX_SECONDS = 14400

    @staticmethod
    def _login(user_id, key):
        session = Session.objects.filter(
            session_key=key, expire_date__gt=timezone.now()
        ).first()
        if session is None or str(session.get_decoded().get("_auth_user_id")) != str(
            user_id
        ):
            raise ReadLeaseNotFound("Read authorization not available")

    @staticmethod
    def _version(version_id):
        row = ResourceVersion.objects.filter(pk=version_id).first()
        if row is None:
            raise ReadLeaseNotFound("Version not available")
        return row

    @staticmethod
    def _pool(version):
        return ResourcePoolEntry.objects.select_for_update().get(pk=version.pool_id)

    @staticmethod
    def _scope(user_id, version, pool):
        if (
            not pool.is_available
            or pool.resource_id is None
            or pool.state not in {"ready", "preparing", "pending_gc"}
            or version.state not in {"ready", "retired"}
            or (version.owner_id is not None and version.owner_id != user_id)
        ):
            raise ReadLeaseNotFound("Version not available")

    @staticmethod
    def _membership(user_id, version, pool):
        field = "current_version" if version.kind == "metadata" else "video_version"
        return UserLibraryEntry.objects.filter(
            user_id=user_id,
            pool=pool,
            state="active",
            access_scope=version.access_scope,
            **{field: version},
        ).exists()

    @staticmethod
    def _playback(user_id, key, session_id, version):
        row = PlaybackSession.objects.filter(
            pk=session_id,
            user_id=user_id,
            login_hash=playback_login_hash(key),
            state__in=["queued", "resolving", "ready"],
            idle_expires_at__gt=timezone.now(),
            absolute_expires_at__gt=timezone.now(),
        ).first()
        if (
            row is None
            or row.library_grant.get("version_id") != str(version.pk)
            or row.library_grant.get("pool_id") != str(version.pool_id)
            or row.library_grant.get("scope") != version.access_scope
            or row.resource.pk != version.pool.resource_id
            or (version.kind == "video") != (row.media_kind == "local")
        ):
            raise ReadLeaseNotFound("Playback version not available")
        return row

    def _valid(self, user_id, key, row, version, pool):
        self._scope(user_id, version, pool)
        if row.login_hash != binding(key) or row.account_epoch != execution_epoch(
            user_id
        ):
            raise ReadLeaseNotFound("Read authorization not available")
        if (
            row.state != "active"
            or row.expires_at <= timezone.now()
            or row.absolute_expires_at <= timezone.now()
        ):
            raise ReadLeaseConflict("read_lease_expired")
        if row.playback_session_id is not None:
            self._playback(user_id, key, row.playback_session_id, version)
        elif not self._membership(user_id, version, pool):
            raise ReadLeaseNotFound("Version not held")

    @retry_sqlite_contention
    def pin(self, user_id, key, version_id, request_id, playback_session_id):
        with transaction.atomic():
            lock_user(user_id)
            self._login(user_id, key)
            version = self._version(version_id)
            pool = self._pool(version)
            self._scope(user_id, version, pool)
            previous = ResourceReadLease.objects.filter(
                user_id=user_id, request_id=request_id
            ).first()
            if previous:
                if (
                    previous.version_id != version_id
                    or previous.login_hash != binding(key)
                    or previous.playback_session_id != playback_session_id
                ):
                    raise ReadLeaseConflict("request_id_reused")
                self._valid(user_id, key, previous, version, pool)
                return snapshot(previous)
            now = timezone.now()
            absolute = now + timedelta(seconds=self.ASSET_MAX_SECONDS)
            if playback_session_id is not None:
                # This is an existing, fixed-version playback grant, not a new
                # playback authorization. It may drain after membership release.
                session = self._playback(user_id, key, playback_session_id, version)
                absolute = min(
                    session.absolute_expires_at,
                    now + timedelta(seconds=self.PLAYBACK_MAX_SECONDS),
                )
            elif pool.state == "pending_gc" or not self._membership(
                user_id, version, pool
            ):
                raise ReadLeaseNotFound("Version not held")
            row = ResourceReadLease.objects.create(
                user_id=user_id,
                version=version,
                request_id=request_id,
                login_hash=binding(key),
                account_epoch=execution_epoch(user_id),
                playback_session_id=playback_session_id,
                absolute_expires_at=absolute,
                expires_at=min(absolute, now + timedelta(seconds=self.IDLE_SECONDS)),
            )
            return snapshot(row)

    def _locked(self, user_id, key, lease_id):
        lock_user(user_id)
        self._login(user_id, key)
        row = ResourceReadLease.objects.filter(pk=lease_id, user_id=user_id).first()
        if row is None:
            raise ReadLeaseNotFound("Read lease not available")
        version = self._version(row.version_id)
        pool = self._pool(version)
        row = ResourceReadLease.objects.select_for_update().get(pk=row.pk)
        return row, version, pool

    @retry_sqlite_contention
    def renew(self, user_id, key, lease_id, revision):
        with transaction.atomic():
            row, version, pool = self._locked(user_id, key, lease_id)
            self._valid(user_id, key, row, version, pool)
            if row.revision != revision:
                raise ReadLeaseConflict("read_lease_revision_conflict")
            row.expires_at = min(
                row.absolute_expires_at,
                timezone.now() + timedelta(seconds=self.IDLE_SECONDS),
            )
            row.revision += 1
            row.save(update_fields=["expires_at", "revision", "updated_at"])
            return snapshot(row)

    @retry_sqlite_contention
    def check(self, user_id, key, lease_id):
        with transaction.atomic():
            row, version, pool = self._locked(user_id, key, lease_id)
            self._valid(user_id, key, row, version, pool)
            return snapshot(row)

    @retry_sqlite_contention
    def release(self, user_id, key, lease_id):
        with transaction.atomic():
            row, _, _ = self._locked(user_id, key, lease_id)
            if row.login_hash != binding(key):
                raise ReadLeaseNotFound("Read lease not available")
            if row.state != "released":
                row.state = "released"
                row.revision += 1
                row.save(update_fields=["state", "revision", "updated_at"])
            return snapshot(row)

    @staticmethod
    def has_readers(version_id):
        return ResourceReadLease.objects.filter(
            version_id=version_id,
            state="active",
            expires_at__gt=timezone.now(),
            absolute_expires_at__gt=timezone.now(),
        ).exists()
