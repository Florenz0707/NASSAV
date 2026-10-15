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


class ResourceReclaimer:
    """Own ordering between durable evidence and a replaceable file adapter."""

    def __init__(self, records, storage, *, batch_size=32):
        if type(batch_size) is not int or not 1 <= batch_size <= 100:
            raise ValueError("Invalid GC batch")
        self.records, self.storage, self.batch_size = records, storage, batch_size

    def run(self, job_id):
        intent = self.records.intent(job_id)
        with self.storage.locked(intent):
            token = self.records.claim(job_id)
            if token is None:
                return self.records.status(job_id)
            try:

                def check():
                    return self.records.check(token)

                for asset in self.records.assets(token, self.batch_size):
                    with self.storage.deletion(asset, check) as (fingerprint, remove):
                        if fingerprint is not None:
                            self.records.verified(token, asset["pk"], fingerprint)
                        self.records.unlink(token, asset["pk"], remove)
                if self.records.assets(token, 1):
                    return self.records.yield_claim(token)
                self.storage.clean_namespaces(self.records.versions(token), check)
                return self.records.complete(token)
            except GcLeaseLost:
                raise
            except Exception as error:
                code = (
                    str(error)
                    if isinstance(error, GcEvidenceError)
                    else "file_cleanup_failed"
                )
                return self.records.fail(token, code)
