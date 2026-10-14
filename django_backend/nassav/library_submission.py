"""Submission orchestration receives source resolver/commands/dispatch explicitly."""

from nassav.shared_work import SharedOperations, specification_hash


class LibrarySubmission:
    def __init__(self, records, resolve_source, dispatch):
        self.records, self.resolve_source, self.dispatch = (
            records,
            resolve_source,
            dispatch,
        )

    def submit(self, user_id, payload):
        if not isinstance(payload, dict):
            raise ValueError("Operation must be an object")
        intent, request_id = SharedOperations.command(user_id, payload)
        previous = self.records.replay(user_id, request_id, specification_hash(intent))
        if previous is not None:
            self.dispatch()
            return previous
        mode = payload.get("credential_mode", "public")
        context, close = self.resolve_source(user_id, payload.get("source"), mode)
        try:
            binding = context.work_binding

            def accept():
                return SharedOperations(self.records).submit(
                    user_id,
                    payload,
                    access_scope=binding["access_scope"],
                    credential_refs=binding["credential_refs"],
                    context_revision=binding["context_revision"],
                )

            result = context.publish(accept)
        finally:
            close()
        self.dispatch()  # The pending outbox survives broker failure.
        return result
