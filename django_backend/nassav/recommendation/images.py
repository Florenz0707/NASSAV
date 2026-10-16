"""Request-owned image lookup and stream checks, with source factories injected."""

import hashlib
import os
from contextlib import AbstractContextManager
from typing import Callable
from nassav.recommendation.cover_cache import RecommendationCoverCacheService
from nassav.resource_reads import ReadLeaseNotFound


def source_image_context(source):
    context = source.credential_context
    if context is None:
        raise PermissionError("Scoped image source required")
    return [source.domain, hashlib.sha256(context.scope_key.encode()).hexdigest()]


class CheckedImage:
    def __init__(self, handle, check):
        self.handle, self.check = handle, check
        info = os.fstat(handle.fileno())
        self.cache_validator = [
            info.st_dev,
            info.st_ino,
            info.st_size,
            info.st_mtime_ns,
            info.st_ctime_ns,
        ]

    def read(self, size=-1):
        self.check()
        data = self.handle.read(size)
        self.check()
        return data

    def close(self):
        self.handle.close()


class RecommendationImages:
    def __init__(
        self,
        source_scope: Callable[..., AbstractContextManager],
        check_actor,
        open_image,
    ):
        self.source_scope, self.check_actor, self.open_image = (
            source_scope,
            check_actor,
            open_image,
        )

    def open(
        self,
        user_id,
        source_name,
        url,
        *,
        expected_context=None,
        check_result=lambda: None,
    ):
        check_result()
        self.check_actor(user_id)
        handle = None
        transferred = False
        try:
            with self.source_scope(user_id, source_name, check_result) as source:
                context = source.credential_context
                if context is None:
                    raise PermissionError("Scoped image source required")
                if (
                    expected_context is not None
                    and source_image_context(source) != expected_context
                ):
                    raise ReadLeaseNotFound("Image source context changed")
                check_result()
                service = RecommendationCoverCacheService(source)
                if not service.is_allowed_url(url):
                    raise ValueError("Image source not supported")
                path = service.ensure_cached(url)
                if path is None:
                    raise ReadLeaseNotFound("Image unavailable")
                handle = self.open_image(path)
                context.check()

                def check():
                    check_result()
                    self.check_actor(user_id)
                    context.check()

                result = CheckedImage(handle, check)
            # Transfer ownership only after the source's exit check passed.
            transferred = True
            return result
        except PermissionError:
            raise
        except OSError:
            raise ReadLeaseNotFound("Image unavailable") from None
        finally:
            if handle is not None and not transferred:
                handle.close()
