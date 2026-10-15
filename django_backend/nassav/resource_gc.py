"""Reclamation contracts; file locks must precede every database claim."""

from dataclasses import dataclass
from uuid import UUID


class GcNotFound(LookupError):
    pass


class GcDeferred(RuntimeError):
    def __init__(self, reasons):
        self.reasons = tuple(reasons)
        super().__init__("resource_gc_protected")


class GcLeaseLost(RuntimeError):
    pass


class GcEvidenceError(RuntimeError):
    pass


@dataclass(frozen=True)
class GcToken:
    job_id: UUID
    owner: UUID
    pool_generation: int
