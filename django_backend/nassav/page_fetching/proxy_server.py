"""Provider-independent proxy capacity and ordered concurrent operations."""

from collections import deque
from collections.abc import Callable, Iterable, Iterator
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeout
from contextlib import AbstractContextManager, contextmanager, nullcontext
from threading import Event
from typing import Protocol, TypeVar

T = TypeVar("T")
R = TypeVar("R")


class ProxyOperationStopped(RuntimeError):
    pass


class ProxyCapacityError(RuntimeError):
    pass


class ProxyServer(Protocol):
    """Operations must own their sessions; only the consumer merges results."""

    def ordered(
        self,
        operation: Callable[[T, Callable[[], None]], R],
        values: Iterable[T],
        *,
        check: Callable[[], None] | None = None,
    ) -> AbstractContextManager[Iterator[R]]: ...

    def slot(
        self, timeout_ms: int, *, check: Callable[[], None]
    ) -> AbstractContextManager[None]: ...


class OrderedProxyServer:
    def __init__(self, max_concurrency: int = 1, *, capacity=None, worker_scope=None):
        if isinstance(max_concurrency, bool) or not 1 <= max_concurrency <= 8:
            raise ValueError("Proxy server concurrency must be between 1 and 8")
        self.max_concurrency = max_concurrency
        self.capacity = capacity
        self.worker_scope = worker_scope or nullcontext

    @contextmanager
    def slot(self, timeout_ms: int, *, check: Callable[[], None]):
        check()
        if self.capacity is None:
            yield
        else:
            with self.capacity.slot(timeout_ms, check=check):
                yield
        check()

    @contextmanager
    def ordered(self, operation, values, *, check=None):
        stopped = Event()
        check_owner = check or (lambda: None)

        def checkpoint():
            if stopped.is_set():
                raise ProxyOperationStopped("Proxy operation stopped")
            check_owner()

        def invoke(value):
            scope = self.worker_scope if self.max_concurrency > 1 else nullcontext
            with scope():
                checkpoint()
                result = operation(value, checkpoint)
                checkpoint()
                return result

        if self.max_concurrency == 1:
            try:
                yield (invoke(value) for value in values)
            finally:
                stopped.set()
            return

        pool = ThreadPoolExecutor(max_workers=self.max_concurrency)
        pending = deque()
        inputs = iter(values)

        def submit_one():
            checkpoint()
            try:
                value = next(inputs)
            except StopIteration:
                return
            pending.append(pool.submit(invoke, value))

        def results():
            for _ in range(self.max_concurrency):
                submit_one()
            while pending:
                future = pending.popleft()
                while True:
                    checkpoint()
                    try:
                        result = future.result(timeout=0.1)
                        break
                    except FutureTimeout:
                        if future.done():
                            # A TimeoutError raised by the operation is not a wait timeout.
                            result = future.result()
                            break
                checkpoint()
                yield result
                submit_one()

        try:
            yield results()
        finally:
            stopped.set()
            for future in pending:
                future.cancel()
            pool.shutdown(wait=True, cancel_futures=True)
