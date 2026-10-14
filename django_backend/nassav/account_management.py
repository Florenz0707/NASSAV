"""Validated admin commands; dependencies supplied by production composition."""

from typing import Protocol
from uuid import UUID


REASONS = frozenset(
    {"bootstrap", "security", "maintenance", "user_request", "quota_adjustment"}
)


class AccountConflict(RuntimeError):
    pass


class AccountCommands(Protocol):
    def execute(
        self, actor_id: int, action: str, target_id: int | None, command: dict
    ) -> dict: ...


class AccountManagement:
    def __init__(self, commands: AccountCommands):
        self.commands = commands

    def execute(self, actor_id, action, target_id, payload):
        if type(actor_id) is not int or actor_id < 1:
            raise ValueError("Invalid actor")
        if action not in {
            "create",
            "update",
            "revoke_sessions",
            "reset_password",
            "bootstrap",
        }:
            raise ValueError("Invalid account action")
        if action != "create" and (type(target_id) is not int or target_id < 1):
            raise ValueError("Invalid target")
        if not isinstance(payload, dict):
            raise ValueError("Invalid command")
        allowed = {"request_id", "reason", "expected_version"}
        allowed |= (
            {"username", "password", "role", "is_active"}
            if action == "create"
            else set()
        )
        allowed |= (
            {"role", "is_active", "storage_quota_bytes", "max_active_operations"}
            if action == "update"
            else set()
        )
        allowed |= {"password"} if action == "reset_password" else set()
        if set(payload) - allowed:
            raise ValueError("Unknown command fields")
        command = dict(payload)
        try:
            command["request_id"] = str(UUID(str(command["request_id"])))
        except (KeyError, ValueError, TypeError) as error:
            raise ValueError("Invalid request ID") from error
        if (
            not isinstance(command.get("reason"), str)
            or command["reason"] not in REASONS
        ):
            raise ValueError("Choose a non-sensitive reason code")
        if action not in {"create", "bootstrap"} and (
            type(command.get("expected_version")) is not int
            or command["expected_version"] < 1
        ):
            raise ValueError("Invalid account version")
        if "role" in command and (
            not isinstance(command["role"], str)
            or command["role"] not in {"user", "admin"}
        ):
            raise ValueError("Invalid application role")
        if "is_active" in command and type(command["is_active"]) is not bool:
            raise ValueError("Invalid active flag")
        if (
            "storage_quota_bytes" in command
            and command["storage_quota_bytes"] is not None
            and (
                type(command["storage_quota_bytes"]) is not int
                or not 0 <= command["storage_quota_bytes"] <= 9223372036854775807
            )
        ):
            raise ValueError("Invalid storage quota")
        if "max_active_operations" in command and (
            type(command["max_active_operations"]) is not int
            or not 1 <= command["max_active_operations"] <= 2147483647
        ):
            raise ValueError("Invalid operation quota")
        if action == "create" and (
            not isinstance(command.get("username"), str)
            or not command["username"]
            or len(command["username"]) > 150
        ):
            raise ValueError("Invalid username")
        if action in {"create", "reset_password"} and (
            not isinstance(command.get("password"), str)
            or not 12 <= len(command["password"]) <= 256
        ):
            raise ValueError("Password must contain 12 to 256 characters")
        if action == "update" and not (
            set(command) - {"request_id", "reason", "expected_version"}
        ):
            raise ValueError("No account changes supplied")
        return self.commands.execute(actor_id, action, target_id, command)
