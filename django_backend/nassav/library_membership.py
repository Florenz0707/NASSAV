"""Membership use cases, independent of HTTP, task dispatch and production adapters."""

from datetime import timedelta
from typing import Protocol
from uuid import UUID

from nassav.task_control_rules import normalize_avid


class LibraryConflict(RuntimeError):
    def __init__(self, code, snapshot=None):
        self.code = code
        self.snapshot = snapshot
        super().__init__(code)


class LibraryNotFound(LookupError):
    pass


class MembershipRecords(Protocol):
    def attach(self, user_id: int, avid: str, source: str, scope: str) -> dict: ...

    def release(
        self, user_id: int, entry_id: UUID, expected_version: int, grace: timedelta
    ) -> dict: ...

    def release_command(
        self,
        user_id: int,
        entry_id: UUID,
        expected_version: int,
        request_id: UUID,
        grace: timedelta,
    ) -> dict: ...


class LibraryMembership:
    """Internal P1 interface; callers own demand/idempotency until P4 exists.

    Attaching creates pending membership, never grants access to an arbitrary
    existing file. Releasing only removes the caller's relationship and marks
    a GC candidate. Neither operation dispatches jobs or deletes assets.
    """

    def __init__(self, records: MembershipRecords, *, gc_grace=timedelta(hours=24)):
        if not isinstance(gc_grace, timedelta) or gc_grace < timedelta(0):
            raise ValueError("Invalid GC grace")
        self.records = records
        self.gc_grace = gc_grace

    def attach(self, user_id, avid, *, source, access_scope):
        self._user(user_id)
        if not isinstance(avid, str):
            raise ValueError("Invalid AVID")
        avid = normalize_avid(avid)
        if (
            not isinstance(source, str)
            or not source.strip()
            or len(source.strip()) > 128
        ):
            raise ValueError("Invalid source")
        # Scope is supplied by the trusted resolver, never by an HTTP owner field.
        if (
            not isinstance(access_scope, str)
            or not access_scope
            or len(access_scope) > 128
        ):
            raise ValueError("Invalid access scope")
        return self.records.attach(user_id, avid, source.strip().lower(), access_scope)

    def release(self, user_id, entry_id, *, expected_version, request_id=None):
        self._user(user_id)
        if type(expected_version) is not int or expected_version < 1:
            raise ValueError("Invalid membership version")
        try:
            entry_id = UUID(str(entry_id))
        except (ValueError, TypeError, AttributeError) as error:
            raise ValueError("Invalid membership ID") from error
        if request_id is not None:
            try:
                request_id = UUID(str(request_id))
            except (ValueError, TypeError):
                raise ValueError("Invalid library request ID") from None
            return self.records.release_command(
                user_id, entry_id, expected_version, request_id, self.gc_grace
            )
        return self.records.release(user_id, entry_id, expected_version, self.gc_grace)

    @staticmethod
    def _user(user_id):
        if type(user_id) is not int or user_id < 1:
            raise ValueError("Invalid user")
