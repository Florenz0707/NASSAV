"""Infrastructure-free capabilities consumed by download workflows."""

from abc import ABC, abstractmethod
from collections.abc import Callable


class DownloadLeaseLost(RuntimeError):
    pass


class DownloadOwnership(ABC):
    def retain_for_recovery(self) -> None:
        """Hold only owned reservations when a writer cannot be confirmed stopped."""
        raise NotImplementedError

    def recovery_identity(self) -> dict:
        return {}

    @abstractmethod
    def start(self, ttl: int | None = None) -> None: ...

    @abstractmethod
    def acquire_global(self, ttl: int = 3600) -> bool: ...

    @abstractmethod
    def check(self) -> None: ...

    @abstractmethod
    def cancelled(self) -> bool: ...

    @abstractmethod
    def release_global(self) -> bool: ...

    @abstractmethod
    def mutate(self, operation: str, payload: str = "") -> bool: ...

    @abstractmethod
    def close(self) -> None: ...


class DownloadExecutor(ABC):
    @abstractmethod
    def download_video(
        self,
        avid: str,
        progress_callback: Callable | None = None,
        cancelled: Callable[[], bool] | None = None,
    ) -> bool:
        raise NotImplementedError


class DownloadPersistence(ABC):
    @abstractmethod
    def mark_completed(self, avid: str) -> None:
        """Reflect the downloaded file in the resource record."""

    @abstractmethod
    def mark_failed(self, avid: str) -> None:
        """Mark a failed download as unavailable."""


class DownloadRetriesExhausted(Exception):
    pass


class DownloadRuntime(ABC):
    @abstractmethod
    def create_lock(self, avid: str, task_id: str) -> None:
        raise NotImplementedError

    @abstractmethod
    def wait_for_slot(self, max_wait_time: int) -> bool:
        raise NotImplementedError

    @abstractmethod
    def remove_lock(self, avid: str) -> None:
        raise NotImplementedError

    @abstractmethod
    def remove_from_queue(self, avid: str) -> None:
        raise NotImplementedError

    @abstractmethod
    def notify(self, event: str, data: dict) -> None:
        raise NotImplementedError

    @abstractmethod
    def queue_status(self) -> dict:
        raise NotImplementedError

    @abstractmethod
    def set_state(self, avid: str, state: str) -> None:
        raise NotImplementedError

    @abstractmethod
    def set_progress(self, avid: str, percent: float, speed: str, *, eta: str) -> None:
        raise NotImplementedError

    @abstractmethod
    def release_slot(self) -> None:
        raise NotImplementedError

    @abstractmethod
    def remove_progress(self, avid: str) -> None:
        raise NotImplementedError


class DownloadWorkflow(ABC):
    @abstractmethod
    def run(self, avid: str, task_id: str, **context) -> dict:
        raise NotImplementedError
