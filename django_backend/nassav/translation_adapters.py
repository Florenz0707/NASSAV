"""Django and translator-manager bindings for title translation."""

from django.db.models import Q

from nassav.models import AVResource
from nassav.translation_contracts import (
    TextTranslator,
    TranslationRecord,
    TranslationRepository,
)


class DjangoTranslationRepository(TranslationRepository):
    def __init__(self):
        self._rows: dict[int, AVResource] = {}

    def _record(self, row) -> TranslationRecord:
        self._rows[row.pk] = row
        return TranslationRecord(
            **{
                field: getattr(row, field)
                for field in TranslationRecord.__dataclass_fields__
            }
        )

    def get(self, avid: str) -> TranslationRecord | None:
        row = AVResource.objects.filter(avid=avid).first()
        return self._record(row) if row else None

    def select(
        self, avids: list[str] | None, skip_existing: bool
    ) -> list[TranslationRecord]:
        query = Q(avid__in=[avid.upper() for avid in avids]) if avids else Q()
        query &= (Q(original_title__isnull=False) & ~Q(original_title="")) | (
            Q(source_title__isnull=False) & ~Q(source_title="")
        )
        if skip_existing:
            query &= ~Q(translation_status="completed")
        return [self._record(row) for row in AVResource.objects.filter(query)]

    def save(self, record: TranslationRecord, fields: list[str]) -> None:
        row = self._rows[record.pk]
        for field in fields:
            setattr(row, field, getattr(record, field))
        row.save(update_fields=fields)

    def mark_translating(self, ids: list[int]) -> None:
        AVResource.objects.filter(pk__in=ids).update(translation_status="translating")

    def fail_inflight(self, ids: list[int]) -> None:
        AVResource.objects.filter(pk__in=ids, translation_status="translating").update(
            translation_status="failed"
        )


class ManagerTextTranslator(TextTranslator):
    def __init__(self, manager):
        self.manager = manager

    def translate(self, text: str) -> str | None:
        return self.manager.translate(text)

    def batch_translate(self, texts: list[str]) -> list[str | None]:
        return self.manager.batch_translate(texts)
