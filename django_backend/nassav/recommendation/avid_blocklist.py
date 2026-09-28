"""Persistence and list projection for manually blocked recommendation AVIDs."""

from abc import ABC, abstractmethod

from django.core.paginator import Paginator

from nassav.models import AVResource, RecommendationAvidBlocklist


class AvidBlocklistRepository(ABC):
    @abstractmethod
    def list(
        self, *, page: int, page_size: int, search: str
    ) -> tuple[list[dict], dict]:
        """Return entries and the existing API pagination shape."""

    @abstractmethod
    def block(self, *, avid: str, reason: str) -> dict:
        """Create or update a manual block and return its API projection."""

    @abstractmethod
    def unblock(self, *, avid: str) -> bool:
        """Remove a block; return whether one existed."""


class DjangoAvidBlocklistRepository(AvidBlocklistRepository):
    def list(
        self, *, page: int, page_size: int, search: str
    ) -> tuple[list[dict], dict]:
        qs = RecommendationAvidBlocklist.objects.all().order_by("-updated_at", "-id")
        if search:
            qs = qs.filter(avid__icontains=search.upper())

        paginator = Paginator(qs, page_size)
        page_obj = paginator.get_page(page)
        avids = [str(item.avid or "").strip().upper() for item in page_obj.object_list]
        resources = {
            resource.avid.upper(): resource
            for resource in AVResource.objects.filter(avid__in=avids)
        }

        data = []
        for item in page_obj.object_list:
            resource = resources.get(item.avid.upper())
            title = ""
            source = ""
            if resource is not None:
                title = (
                    resource.translated_title
                    or resource.original_title
                    or resource.source_title
                    or ""
                )
                source = resource.source or ""
            data.append(
                {
                    "avid": item.avid,
                    "title": title,
                    "source": source,
                    "reason": item.reason,
                    "is_blocked": True,
                    "exists_in_library": resource is not None,
                    "updated_at": item.updated_at.isoformat()
                    if item.updated_at is not None
                    else None,
                }
            )

        pagination = {
            "total": paginator.count,
            "page": page_obj.number,
            "page_size": page_size,
            "pages": paginator.num_pages,
        }
        return data, pagination

    def block(self, *, avid: str, reason: str) -> dict:
        block, _ = RecommendationAvidBlocklist.objects.update_or_create(
            avid=avid,
            defaults={"source": "manual", "reason": reason},
        )
        return {
            "avid": block.avid,
            "reason": block.reason,
            "source": block.source,
            "is_blocked": True,
        }

    def unblock(self, *, avid: str) -> bool:
        deleted_count, _ = RecommendationAvidBlocklist.objects.filter(
            avid=avid
        ).delete()
        return deleted_count != 0


recommendation_avid_blocklist_repository = DjangoAvidBlocklistRepository()
