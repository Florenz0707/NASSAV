import hashlib
import os
import tempfile
from pathlib import Path
from urllib.parse import urlparse

from django.conf import settings

from nassav.source.SourceBase import SourceBase
from nassav.constants import HEADERS, IMPERSONATE
from curl_cffi import requests


class RecommendationCoverCacheService:
    ALLOWED_HOSTS = {
        "assets-cdn.jable.tv",
        "assets.jable.tv",
        "jable.tv",
    }

    def __init__(self, jable: SourceBase):
        self.jable = jable

    def ensure_cached(self, cover_url: str) -> Path | None:
        normalized_url = cover_url.strip()
        if not normalized_url or not self.is_allowed_url(normalized_url):
            return None

        cache_path = self.get_cache_path(normalized_url)
        if cache_path.exists():
            return cache_path

        cache_path.parent.mkdir(parents=True, exist_ok=True)
        if self.jable.get_source_name().lower() == "missav":
            return self._cache_missav_image(normalized_url, cache_path)
        success = self.jable.download_file(
            normalized_url,
            str(cache_path),
            referer=f"https://{self.jable.domain}/",
        )
        if not success or not cache_path.exists():
            return None
        return cache_path

    def get_cache_path(self, cover_url: str) -> Path:
        url_hash = hashlib.sha256(cover_url.encode("utf-8")).hexdigest()
        suffix = self.get_file_suffix(cover_url)
        return Path(settings.RECOMMENDATION_COVER_DIR) / f"{url_hash}{suffix}"

    def is_allowed_url(self, cover_url: str) -> bool:
        parsed = urlparse(cover_url)
        hosts = (
            {"fourhoi.com"}
            if self.jable.get_source_name().lower() == "missav"
            else self.ALLOWED_HOSTS
        )
        return parsed.scheme in {"http", "https"} and parsed.netloc in hosts

    def _cache_missav_image(self, url: str, target: Path) -> Path | None:
        """Bounded CDN download; never forward site cookies to a third party."""
        temporary = None
        response = None
        try:
            headers = {**HEADERS, "Referer": f"https://{self.jable.domain}/cn/"}
            response = requests.get(
                url,
                headers=headers,
                proxy=self.jable.proxy,
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

    def get_file_suffix(self, cover_url: str) -> str:
        suffix = Path(urlparse(cover_url).path).suffix.lower()
        if suffix in {".jpg", ".jpeg", ".png", ".webp"}:
            return suffix
        return ".jpg"
