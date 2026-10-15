"""Named, owned external-search subjects carry no global mapping identity."""

from dataclasses import dataclass


@dataclass(frozen=True)
class CatalogEntity:
    id: int
    name: str
    resource_count: int
    search_identity: str
    avatar_url: str | None = None
    avatar_filename: str | None = None
    legacy_mapping_id: int | None = None

    @property
    def pk(self):
        return self.id

    @property
    def search_keyword(self):
        return self.name
