import hashlib
from pathlib import Path
from urllib.parse import urlparse

from django.conf import settings

from nassav.source import Jable


class RecommendationCoverCacheService:
    ALLOWED_HOSTS = {
        "assets-cdn.jable.tv",
        "assets.jable.tv",
        "jable.tv",
    }

    def __init__(self, jable: Jable):
        self.jable = jable

    def ensure_cached(self, cover_url: str) -> Path | None:
        normalized_url = cover_url.strip()
        if not normalized_url or not self.is_allowed_url(normalized_url):
            return None

        cache_path = self.get_cache_path(normalized_url)
        if cache_path.exists():
            return cache_path

        cache_path.parent.mkdir(parents=True, exist_ok=True)
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
        return (
            parsed.scheme in {"http", "https"} and parsed.netloc in self.ALLOWED_HOSTS
        )

    def get_file_suffix(self, cover_url: str) -> str:
        suffix = Path(urlparse(cover_url).path).suffix.lower()
        if suffix in {".jpg", ".jpeg", ".png", ".webp"}:
            return suffix
        return ".jpg"
