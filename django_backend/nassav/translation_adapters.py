"""Django and translator-manager bindings for title translation."""

from django.db.models import Q
from uuid import uuid4

from nassav.models import AVResource
from nassav.translation_contracts import (
    TextTranslator,
    TranslationRecord,
    TranslationRepository,
    TranslationSuperseded,
)


class DjangoTranslationRepository(TranslationRepository):
    def __init__(self, expected_generations: dict[str, int] | None = None):
        self.expected_generations = expected_generations or {}
        self._records: dict[int, TranslationRecord] = {}
        self._owners: dict[int, tuple[int, object]] = {}

    def _record(self, row) -> TranslationRecord:
        self._owners.pop(row.pk, None)
        record = TranslationRecord(
            **{
                field: getattr(row, field)
                for field in TranslationRecord.__dataclass_fields__
            }
        )
        self._records[row.pk] = record
        return record

    def get(self, avid: str) -> TranslationRecord | None:
        row = AVResource.objects.filter(avid=avid).first()
        if (
            row is not None
            and avid in self.expected_generations
            and row.translation_generation != self.expected_generations[avid]
        ):
            raise TranslationSuperseded("排队翻译已被更新请求替代")
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
        return [
            self._record(row)
            for row in AVResource.objects.filter(query)
            if row.avid not in self.expected_generations
            or row.translation_generation == self.expected_generations[row.avid]
        ]

    def save(self, record: TranslationRecord, fields: list[str]) -> None:
        if record.translation_status == "translating" and record.pk not in self._owners:
            self._claim(record)
            return
        generation, owner = self._owners.get(
            record.pk, (record.translation_generation, record.translation_owner)
        )
        if not AVResource.objects.filter(
            pk=record.pk, translation_generation=generation, translation_owner=owner
        ).update(**{field: getattr(record, field) for field in fields}):
            raise TranslationSuperseded("翻译结果归属已变化")

    def _claim(self, record: TranslationRecord) -> None:
        owner = uuid4()
        generation = record.translation_generation + 1
        if not AVResource.objects.filter(
            pk=record.pk,
            translation_generation=record.translation_generation,
            translation_owner=record.translation_owner,
        ).update(
            translation_generation=generation,
            translation_owner=owner,
            translation_status="translating",
        ):
            raise TranslationSuperseded("翻译已被更新请求替代")
        record.translation_generation, record.translation_owner = generation, owner
        self._owners[record.pk] = (generation, owner)

    def mark_translating(self, ids: list[int]) -> None:
        for pk in ids:
            self._claim(self._records[pk])

    def fail_inflight(self, ids: list[int]) -> None:
        for pk in ids:
            if pk in self._owners:
                generation, owner = self._owners[pk]
                AVResource.objects.filter(
                    pk=pk,
                    translation_generation=generation,
                    translation_owner=owner,
                    translation_status="translating",
                ).update(translation_status="failed")


class ManagerTextTranslator(TextTranslator):
    def __init__(self, manager):
        self.manager = manager

    def translate(self, text: str) -> str | None:
        return self.manager.translate(text)

    def batch_translate(self, texts: list[str]) -> list[str | None]:
        return self.manager.batch_translate(texts)
