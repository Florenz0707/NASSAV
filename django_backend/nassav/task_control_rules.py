"""Task control transitions with no ORM, Celery or filesystem dependencies."""

import re
from dataclasses import dataclass

TERMINAL_STATES = frozenset({"succeeded", "failed", "cancelled"})


class TaskNotFound(LookupError):
    pass


class TaskForbidden(PermissionError):
    pass


class TaskConflict(RuntimeError):
    def __init__(self, message: str, snapshot: dict):
        super().__init__(message)
        self.snapshot = snapshot


class TaskExecutionInvalid(RuntimeError):
    pass


class TaskPauseRequested(RuntimeError):
    pass


class TaskCancelRequested(RuntimeError):
    pass


@dataclass(frozen=True)
class ExecutionToken:
    job_id: str
    attempt_id: str
    generation: int
    owner: str


def normalize_avid(avid: str) -> str:
    normalized = avid.strip().upper()
    if (
        len(normalized) > 50
        or ".." in normalized
        or not re.fullmatch(r"[A-Z0-9][A-Z0-9._-]*", normalized)
    ):
        raise ValueError("无效的资源编号")
    return normalized


def allowed_actions(state: str, cleanup_state: str = "not_required") -> list[str]:
    actions = {
        "queued": ["pause", "cancel"],
        "running": ["pause", "cancel"],
        "pausing": ["cancel"],
        "paused": ["resume", "cancel"],
    }.get(state, [])
    if state in TERMINAL_STATES and cleanup_state == "failed":
        actions = [*actions, "cleanup_retry"]
    return actions


def command_state(state: str, action: str, has_writer: bool) -> str:
    if action not in {"pause", "resume", "cancel"}:
        raise ValueError("无效的任务控制动作")
    if action == "pause" and state in {"paused", "pausing"}:
        return state
    if action == "cancel" and state in {"cancelled", "cancelling"}:
        return state
    if action not in allowed_actions(state):
        raise ValueError("当前状态不允许此操作")
    if action == "resume":
        return "queued"
    if action == "cancel":
        return "cancelling" if has_writer else "cancelled"
    return "pausing" if has_writer else "paused"
