"""Validated audited GC management, with broker dispatch injected outside DB."""

from uuid import UUID
from nassav.account_management import REASONS


class GcAdminConflict(RuntimeError):
    pass


class GcAdministration:
    def __init__(self, records, dispatch):
        self.records, self.dispatch = records, dispatch

    def execute(self, actor_id, action, target_id, payload):
        if (
            type(actor_id) is not int
            or actor_id < 1
            or action not in {"enqueue", "retry", "retention"}
        ):
            raise ValueError("Invalid GC command")
        target = str(UUID(str(target_id)))
        if not isinstance(payload, dict):
            raise ValueError("Command must be an object")
        allowed = {"request_id", "reason", "expected_version"} | (
            {"version_id"}
            if action == "enqueue"
            else {"retained"}
            if action == "retention"
            else set()
        )
        if set(payload) - allowed:
            raise ValueError("Unknown GC command fields")
        command = dict(payload)
        command["request_id"] = str(UUID(str(command.get("request_id"))))
        if (
            not isinstance(command.get("reason"), str)
            or command["reason"] not in REASONS
            or type(command.get("expected_version")) is not int
            or command["expected_version"] < 1
        ):
            raise ValueError("Invalid reason/version")
        if "version_id" in command and command["version_id"] is not None:
            command["version_id"] = str(UUID(str(command["version_id"])))
        if action == "retention" and type(command.get("retained")) is not bool:
            raise ValueError("retained must be boolean")
        result, send = self.records.execute(actor_id, action, target, command)
        if send:
            try:
                self.dispatch(result["job_id"])
            except Exception:
                pass  # Durable queue + recovery handles a lost broker response.
        return result
