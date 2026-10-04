"""Use the same title/state rules with in-memory contracts and no DB/worker."""

from copy import deepcopy
import pytest
from nassav.translation_contracts import (
    TranslationRepository,
    TranslationRecord,
    TextTranslator,
)
from nassav.translation_workflow import TitleTranslationUseCase


class Repository(TranslationRepository):
    def __init__(self, rows):
        self.rows = {row.pk: deepcopy(row) for row in rows}

    def get(self, avid):
        return next(
            (deepcopy(row) for row in self.rows.values() if row.avid == avid), None
        )

    def select(self, avids, skip_existing):
        return [
            deepcopy(row)
            for row in self.rows.values()
            if (not avids or row.avid in avids)
            and (not skip_existing or row.translation_status != "completed")
        ]

    def save(self, record, fields):
        for field in fields:
            setattr(self.rows[record.pk], field, getattr(record, field))

    def mark_translating(self, ids):
        for pk in ids:
            self.rows[pk].translation_status = "translating"

    def fail_inflight(self, ids):
        for pk in ids:
            if self.rows[pk].translation_status == "translating":
                self.rows[pk].translation_status = "failed"


class Translator(TextTranslator):
    def __init__(self, result):
        self.result, self.texts = result, []

    def translate(self, text):
        self.texts.append(text)
        if isinstance(self.result, Exception):
            raise self.result
        return self.result

    def batch_translate(self, texts):
        return [self.translate(text) for text in texts]


@pytest.mark.parametrize("result", ["译文", None, RuntimeError("offline failure")])
def test_single_and_batch_share_selection_and_final_state(result):
    record = TranslationRecord(1, "TR-001", "Original", "Fallback", "旧译文", "pending")
    for batch in (False, True):
        repository, translator = Repository([record]), Translator(result)
        usecase = TitleTranslationUseCase(repository, translator)
        response = (
            usecase.translate_batch([record.avid])
            if batch
            else usecase.translate(record.avid.lower())
        )
        assert translator.texts == ["Original"]
        assert repository.rows[1].translation_status == (
            "completed" if isinstance(result, str) else "failed"
        )
        assert repository.rows[1].translated_title == (
            result if isinstance(result, str) else "旧译文"
        )
        assert "success" in response


def test_single_missing_empty_and_completed_envelopes():
    empty = TranslationRecord(1, "TR-002", "", "", None, "pending")
    done = TranslationRecord(2, "TR-003", "Title", "", "译文", "completed")
    repository, translator = Repository([empty, done]), Translator("unused")
    usecase = TitleTranslationUseCase(repository, translator)
    assert usecase.translate("missing") == {
        "success": False,
        "error": "资源 MISSING 不存在",
        "avid": "MISSING",
    }
    assert usecase.translate(empty.avid)["translation_status"] == "skipped"
    assert usecase.translate(done.avid)["skipped"] is True
    assert not translator.texts
