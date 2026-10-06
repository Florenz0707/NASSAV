"""Retranslation reset/submission shared by synchronous HTTP entry points."""

from abc import ABC, abstractmethod
from collections.abc import Callable

from nassav.models import AVResource
from django.db import transaction


class TranslationResourceMissing(LookupError):
    pass


class TranslationRequests(ABC):
    @abstractmethod
    def request(self, avid: str) -> None: ...


class DjangoTranslationRequests(TranslationRequests):
    def __init__(self, dispatch: Callable[[str, int], object]):
        self.dispatch = dispatch

    def request(self, avid: str) -> None:
        with transaction.atomic():
            resource = AVResource.objects.select_for_update().filter(avid=avid).first()
            if resource is None:
                raise TranslationResourceMissing(f"{avid} 的资源不存在")
            generation = resource.translation_generation + 1
            AVResource.objects.filter(pk=resource.pk).update(
                translation_status="pending",
                translated_title=None,
                translation_generation=generation,
                translation_owner=None,
            )
        self.dispatch(avid, generation)
