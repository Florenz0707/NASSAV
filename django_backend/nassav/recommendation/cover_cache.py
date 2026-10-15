import hashlib
import os
import tempfile
from abc import ABC, abstractmethod
from pathlib import Path
from urllib.parse import urlparse

from curl_cffi import requests
from django.conf import settings

from nassav.composition import cover_policy_for
from nassav.constants import HEADERS, IMPERSONATE
from nassav.source.SourceBase import SourceBase


class CoverPolicy(ABC):
    @abstractmethod
    def is_allowed_url(self, url: str) -> bool:
        raise NotImplementedError

    @abstractmethod
    def download(self, source: SourceBase, url: str, target: Path) -> Path | None:
        raise NotImplementedError


class JableCoverPolicy(CoverPolicy):
    ALLOWED_HOSTS = {"assets-cdn.jable.tv", "assets.jable.tv", "jable.tv"}

    def is_allowed_url(self, url: str) -> bool:
        parsed = urlparse(url)
        return (
            parsed.scheme in {"http", "https"} and parsed.netloc in self.ALLOWED_HOSTS
        )

    def download(self, source: SourceBase, url: str, target: Path) -> Path | None:
        if source.credential_context is not None:
            return download_image(
                source, url, target, referer=f"https://{source.domain}/"
            )
        success = source.download_file(
            url, str(target), referer=f"https://{source.domain}/"
        )
        return target if success and target.exists() else None


class MissAVCoverPolicy(CoverPolicy):
    def is_allowed_url(self, url: str) -> bool:
        parsed = urlparse(url)
        return parsed.scheme in {"http", "https"} and parsed.netloc == "fourhoi.com"

    def download(self, source: SourceBase, url: str, target: Path) -> Path | None:
        return download_image(
            source, url, target, referer=f"https://{source.domain}/cn/"
        )


def download_image(source, url, target, *, referer):
    """Bounded image transfer; scoped origin policy strips third-party cookies."""
    temporary = None
    response = None
    context = source.credential_context

    def check():
        if context is not None:
            context.check()
        if source.task_control is not None:
            source.task_control.check()

    try:
        check()
        headers = {**HEADERS, "Referer": referer}
        if context is not None:
            if source.cookie:
                headers["Cookie"] = source.cookie
            headers = context.filter_headers(url, headers)
        response = requests.get(
            url,
            headers=headers,
            proxy=source.proxy,
            impersonate=IMPERSONATE,
            timeout=20,
            stream=True,
            allow_redirects=False,
        )
        check()
        if response.status_code != 200 or response.headers.get(
            "Content-Type", ""
        ).split(";", 1)[0].lower() not in {"image/jpeg", "image/png", "image/webp"}:
            return None
        with tempfile.NamedTemporaryFile(dir=target.parent, delete=False) as output:
            temporary = Path(output.name)
            size = 0
            for chunk in response.iter_content():
                check()
                size += len(chunk)
                if size > 5 * 1024 * 1024:
                    return None
                output.write(chunk)
        if not size:
            return None
        check()
        os.replace(temporary, target)
        return target
    except Exception:
        check()
        return None
    finally:
        if response is not None:
            response.close()
        if temporary is not None:
            temporary.unlink(missing_ok=True)


class RecommendationCoverCacheService:
    # Historical public constant retained for callers during migration.
    ALLOWED_HOSTS = JableCoverPolicy.ALLOWED_HOSTS

    def __init__(self, jable: SourceBase, *, policy: CoverPolicy | None = None):
        self.jable = jable
        self.policy = (
            policy if policy is not None else cover_policy_for(jable.get_source_name())
        )

    def ensure_cached(self, cover_url: str) -> Path | None:
        normalized_url = cover_url.strip()
        if not normalized_url or not self.is_allowed_url(normalized_url):
            return None

        context = self.jable.credential_context
        if context is not None:
            context.check()

        cache_path = self.get_cache_path(normalized_url)
        if context is not None:
            from nassav.recommendation_image_files import cache_directory

            root = Path(settings.RECOMMENDATION_COVER_DIR).resolve()
            directory = cache_directory(root, cache_path.parent.relative_to(root))
            temporary = None
            try:
                target = Path(f"/proc/self/fd/{directory}") / cache_path.name
                if target.is_symlink():
                    raise ValueError("Unsafe scoped image cache")
                if target.exists():
                    context.check()
                    return cache_path
                with tempfile.NamedTemporaryFile(
                    dir=target.parent, suffix=cache_path.suffix, delete=False
                ) as file:
                    temporary = Path(file.name)
                result = self.policy.download(self.jable, normalized_url, temporary)
                if result is None:
                    return None
                context.check()
                context.publish(
                    lambda: os.replace(
                        temporary.name,
                        cache_path.name,
                        src_dir_fd=directory,
                        dst_dir_fd=directory,
                    )
                )
                return cache_path
            finally:
                if temporary is not None:
                    temporary.unlink(missing_ok=True)
                os.close(directory)
        if cache_path.exists():
            return cache_path
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        return self.policy.download(self.jable, normalized_url, cache_path)

    def get_cache_path(self, cover_url: str) -> Path:
        url_hash = hashlib.sha256(cover_url.encode("utf-8")).hexdigest()
        suffix = self.get_file_suffix(cover_url)
        root = Path(settings.RECOMMENDATION_COVER_DIR)
        context = self.jable.credential_context
        if context is not None:
            scope = hashlib.sha256(
                (
                    self.jable.get_source_name().lower() + ":" + context.scope_key
                ).encode()
            ).hexdigest()
            root = root.resolve() / "scoped" / scope
        return root / f"{url_hash}{suffix}"

    def is_allowed_url(self, cover_url: str) -> bool:
        return self.policy.is_allowed_url(cover_url)

    def get_file_suffix(self, cover_url: str) -> str:
        suffix = Path(urlparse(cover_url).path).suffix.lower()
        if suffix in {".jpg", ".jpeg", ".png", ".webp"}:
            return suffix
        return ".jpg"
