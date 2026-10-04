"""Optional source abilities, separate from required detail lookup methods."""

from abc import ABC, abstractmethod


class ListingSource(ABC):
    @abstractmethod
    def search_listing(
        self,
        kind: str,
        term: str,
        *,
        page: int = 1,
        ordering: str = "-views",
        force_refresh: bool = False,
    ) -> list[dict]:
        """Return a valid empty/list result or raise a source search error."""
