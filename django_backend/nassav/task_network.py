"""Task-scoped budgets and write checks, independent of Django and Celery."""

import time
from collections.abc import Callable
from contextlib import contextmanager
from pathlib import Path
from curl_cffi.requests.session import HttpMethod


class TaskNetworkTimeout(TimeoutError):
    pass


class TaskNetworkControl:
    def __init__(self, check: Callable[[], None], *, clock: Callable = time.monotonic):
        self._check, self.clock = check, clock
        self.deadline: float | None = None

    def check(self) -> None:
        self._check()
        if self.deadline is not None and self.clock() >= self.deadline:
            raise TaskNetworkTimeout("当前抓取阶段已超过执行预算")

    def timeout(self, maximum: float) -> float:
        self.check()
        return (
            max(0.1, min(maximum, self.deadline - self.clock()))
            if self.deadline is not None
            else maximum
        )

    @contextmanager
    def phase(self, seconds: float):
        previous = self.deadline
        self.deadline = (
            min(previous, self.clock() + seconds)
            if previous is not None
            else self.clock() + seconds
        )
        try:
            self.check()
            yield self
        finally:
            self.deadline = previous

    def write(self, path: Path, content: bytes) -> None:
        if len(content) > 16 * 1024 * 1024:
            raise ValueError("图片或页面超出任务文件上限")
        self.check()
        with path.open("wb") as handle:
            for start in range(0, len(content), 64 * 1024):
                self.check()
                handle.write(content[start : start + 64 * 1024])
        self.check()

    def request(self, method: HttpMethod, url: str, *, timeout: float, **kwargs):
        """Bound total transfer time and check stop requests inside the curl callback."""
        from curl_cffi import CurlOpt, requests
        from curl_cffi.curl import CURL_WRITEFUNC_ERROR

        content = bytearray()
        errors = []

        def receive(chunk):
            try:
                self.check()
                if len(content) + len(chunk) > 20 * 1024 * 1024:
                    raise ValueError("任务网络响应超出上限")
                content.extend(chunk)
                return len(chunk)
            except Exception as error:
                errors.append(error)
                return CURL_WRITEFUNC_ERROR

        self.check()
        try:
            with requests.Session(
                curl_options={CurlOpt.PROXY: "", CurlOpt.NOPROXY: ""}
            ) as session:
                response = session.request(
                    method,
                    url,
                    timeout=self.timeout(timeout),
                    content_callback=receive,
                    **kwargs,
                )
        except Exception:
            if errors:
                raise errors[0]
            self.check()
            raise
        self.check()
        response.content = bytes(content)
        return response


class TaskBrowserSession:
    """Requests-shaped bounded transport for task-local browser control calls."""

    def __init__(self, control: TaskNetworkControl):
        self.control = control

    def post(self, url, *, timeout, **kwargs):
        import requests
        from curl_cffi.requests.exceptions import Timeout, RequestException

        try:
            return self.control.request(
                "POST", url, timeout=min(sum(timeout), 75), **kwargs
            )
        except Timeout as error:
            raise requests.exceptions.ReadTimeout() from error
        except RequestException as error:
            raise requests.exceptions.ConnectionError() from error
