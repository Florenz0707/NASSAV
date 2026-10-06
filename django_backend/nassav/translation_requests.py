"""Retranslation reset/submission shared by synchronous HTTP entry points."""

from abc import ABC, abstractmethod
from collections.abc import Callable

from nassav.models import AVResource


class TranslationResourceMissing(LookupError):
    pass


class TranslationRequests(ABC):
    @abstractmethod
    def request(self, avid: str) -> None: ...


class DjangoTranslationRequests(TranslationRequests):
    def __init__(self, dispatch: Callable[[str], object]):
        self.dispatch = dispatch

    def request(self, avid: str) -> None:
        resource = AVResource.objects.filter(avid=avid).first()
        if resource is None:
            raise TranslationResourceMissing(f"{avid} 的资源不存在")
        resource.refresh_from_db()
        resource.translation_status = "pending"
        resource.translated_title = None
        resource.save(update_fields=["translation_status", "translated_title"])
        self.dispatch(avid)
