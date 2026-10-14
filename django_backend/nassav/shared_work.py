"""User demand validation and canonical shared specifications, without ORM or broker."""

import hashlib
import json
from typing import Protocol
from uuid import UUID

from nassav.task_control_rules import normalize_avid
from nassav.source_credentials import origin_host


class OperationConflict(RuntimeError):
    pass


class OperationNotFound(LookupError):
    pass


class OperationRecords(Protocol):
    def subscribe(self, user_id: int, command: dict) -> dict: ...

    def cancel(
        self, user_id: int, operation_id: UUID, expected_version: int, request_id: UUID
    ) -> dict: ...


def specification_hash(spec):
    return hashlib.sha256(
        json.dumps(spec, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


class SharedOperations:
    def __init__(self, records: OperationRecords):
        self.records = records

    def submit(
        self, user_id, payload, *, access_scope, credential_refs, context_revision
    ):
        intent, request_id = self.command(user_id, payload)
        avid, kind, action, source = (
            intent[key] for key in ("avid", "kind", "action", "source")
        )
        expected = intent["expected_entry_version"]
        if (
            not isinstance(access_scope, str)
            or not access_scope
            or len(access_scope) > 128
        ):
            raise ValueError("Invalid resolved resource scope")
        if (
            not isinstance(credential_refs, dict)
            or not isinstance(context_revision, str)
            or not context_revision
            or len(context_revision) > 256
        ):
            raise ValueError("Invalid resolved source context")
        # Resolver-owned IDs/version evidence only. No Cookie, UA or URLs in specs.
        if set(credential_refs) - {
            "credential_id",
            "credential_version",
            "origin_host",
            "source_name",
        }:
            raise ValueError("Unexpected credential evidence")
        if credential_refs:
            if (
                set(credential_refs)
                != {"credential_id", "credential_version", "origin_host", "source_name"}
                or credential_refs["source_name"] != source
            ):
                raise ValueError("Incomplete credential evidence")
            origin_host(credential_refs["origin_host"])
            credential_id, version = (
                credential_refs["credential_id"],
                credential_refs["credential_version"],
            )
            if credential_id is None:
                if version is not None:
                    raise ValueError("Invalid anonymous credential evidence")
            else:
                try:
                    UUID(str(credential_id))
                except (ValueError, TypeError):
                    raise ValueError("Invalid credential reference") from None
                if type(version) is not int or not 1 <= version <= 9223372036854775807:
                    raise ValueError("Invalid credential version")
        spec = {
            "kind": kind,
            "action": action,
            "source": source,
            "quality": "best",
            "access_scope": access_scope,
            "credential_refs": dict(credential_refs),
            "context_revision": context_revision,
        }
        return self.records.subscribe(
            user_id,
            {
                "avid": avid,
                "request_id": request_id,
                "spec": spec,
                "spec_hash": specification_hash(spec),
                "request_hash": specification_hash(intent),
                "expected_entry_version": expected,
            },
        )

    @staticmethod
    def command(user_id, payload):
        if type(user_id) is not int or user_id < 1 or not isinstance(payload, dict):
            raise ValueError("Invalid operation actor or command")
        if set(payload) - {
            "avid",
            "kind",
            "action",
            "source",
            "quality",
            "request_id",
            "expected_entry_version",
            "credential_mode",
        }:
            raise ValueError("Unknown operation fields")
        if not isinstance(payload.get("avid"), str):
            raise ValueError("Invalid resource identity")
        avid = normalize_avid(payload["avid"])
        kind, action = payload.get("kind"), payload.get("action")
        if (
            not isinstance(kind, str)
            or not isinstance(action, str)
            or kind not in {"scrape", "download"}
            or action not in ({"add", "refresh"} if kind == "scrape" else {"download"})
        ):
            raise ValueError("Invalid operation kind or action")
        source = payload.get("source")
        if (
            not isinstance(source, str)
            or not source
            or len(source) > 50
            or source != source.lower()
            or not source.replace("_", "").isalnum()
        ):
            raise ValueError("An explicit source is required")
        if payload.get("quality", "best") != "best":
            raise ValueError("Unsupported media quality")
        expected = payload.get("expected_entry_version")
        if expected is not None and (type(expected) is not int or expected < 1):
            raise ValueError("Invalid membership version")
        mode = payload.get("credential_mode", "public")
        if not isinstance(mode, str) or mode not in {"public", "personal"}:
            raise ValueError("Invalid credential selection")
        try:
            request_id = UUID(str(payload.get("request_id")))
        except (TypeError, ValueError):
            raise ValueError("Invalid operation request ID") from None
        return {
            "avid": avid,
            "kind": kind,
            "action": action,
            "source": source,
            "quality": "best",
            "credential_mode": mode,
            "expected_entry_version": expected,
        }, request_id

    def cancel(self, user_id, operation_id, *, expected_version, request_id):
        if (
            type(user_id) is not int
            or user_id < 1
            or type(expected_version) is not int
            or expected_version < 1
        ):
            raise ValueError("Invalid operation actor/version")
        try:
            identity, command = UUID(str(operation_id)), UUID(str(request_id))
        except (TypeError, ValueError):
            raise ValueError("Invalid operation or request ID") from None
        return self.records.cancel(user_id, identity, expected_version, command)
