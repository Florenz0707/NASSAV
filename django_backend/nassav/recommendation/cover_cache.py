from abc import ABC, abstractmethod

import hashlib
import os
import tempfile
from pathlib import Path
from urllib.parse import urlparse

from django.conf import settings

from nassav.source.SourceBase import SourceBase
from nassav.composition import cover_policy_for
from nassav.constants import HEADERS, IMPERSONATE
from curl_cffi import requests


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
        success = source.download_file(
            url, str(target), referer=f"https://{source.domain}/"
        )
        return target if success and target.exists() else None


class MissAVCoverPolicy(CoverPolicy):
    def is_allowed_url(self, url: str) -> bool:
        parsed = urlparse(url)
        return parsed.scheme in {"http", "https"} and parsed.netloc == "fourhoi.com"

    def download(self, source: SourceBase, url: str, target: Path) -> Path | None:
        """Bounded CDN download; never forward site cookies to a third party."""
        temporary = None
        response = None
        try:
            headers = {**HEADERS, "Referer": f"https://{source.domain}/cn/"}
            response = requests.get(
                url,
                headers=headers,
                proxy=source.proxy,
                impersonate=IMPERSONATE,
                timeout=20,
                stream=True,
                allow_redirects=False,
            )
            if response is not None:
                if response.status_code != 200 or not response.headers.get(
                    "Content-Type", ""
                ).startswith("image/"):
                    return None
                with tempfile.NamedTemporaryFile(
                    dir=target.parent, delete=False
                ) as output:
                    temporary = Path(output.name)
                    size = 0
                    for chunk in response.iter_content():
                        size += len(chunk)
                        if size > 5 * 1024 * 1024:
                            return None
                        output.write(chunk)
            if temporary is None:
                return None
            os.replace(temporary, target)
            return target
        except Exception:
            return None
        finally:
            if response is not None:
                response.close()
            if temporary:
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

        cache_path = self.get_cache_path(normalized_url)
        if cache_path.exists():
            return cache_path

        cache_path.parent.mkdir(parents=True, exist_ok=True)
        return self.policy.download(self.jable, normalized_url, cache_path)

    def get_cache_path(self, cover_url: str) -> Path:
        url_hash = hashlib.sha256(cover_url.encode("utf-8")).hexdigest()
        suffix = self.get_file_suffix(cover_url)
        return Path(settings.RECOMMENDATION_COVER_DIR) / f"{url_hash}{suffix}"

    def is_allowed_url(self, cover_url: str) -> bool:
        return self.policy.is_allowed_url(cover_url)

    def get_file_suffix(self, cover_url: str) -> str:
        suffix = Path(urlparse(cover_url).path).suffix.lower()
        if suffix in {".jpg", ".jpeg", ".png", ".webp"}:
            return suffix
        return ".jpg"
