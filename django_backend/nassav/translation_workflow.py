"""Shared title selection and state transitions without ORM or Celery."""

from loguru import logger
from nassav.translation_contracts import (
    TranslationRepository,
    TranslationRecord,
    TextTranslator,
    TranslationWorkflow,
)


class TitleTranslationUseCase(TranslationWorkflow):
    def __init__(self, repository: TranslationRepository, translator: TextTranslator):
        self.repository, self.translator = repository, translator

    @staticmethod
    def title_for(record: TranslationRecord) -> str:
        return record.original_title or record.source_title or ""

    def _save_status(self, record: TranslationRecord, status: str) -> None:
        record.translation_status = status
        self.repository.save(record, ["translation_status"])

    def _apply_result(self, record: TranslationRecord, translated: str | None) -> str:
        if not self.title_for(record):
            self._save_status(record, "skipped")
        elif translated:
            record.translated_title = translated
            record.translation_status = "completed"
            self.repository.save(record, ["translated_title", "translation_status"])
        else:
            self._save_status(record, "failed")
        return record.translation_status

    def _fail_inflight(self, ids: list[int]) -> None:
        try:
            self.repository.fail_inflight(ids)
        except Exception as error:
            logger.error("翻译失败状态收尾异常: {}", error)

    def translate(self, avid: str) -> dict:
        avid = avid.upper()
        try:
            record = self.repository.get(avid)
            if record is None:
                return {"success": False, "error": f"资源 {avid} 不存在", "avid": avid}
            if record.translated_title and record.translation_status == "completed":
                return {
                    "success": True,
                    "skipped": True,
                    "avid": avid,
                    "translation_status": "completed",
                    "translated_title": record.translated_title,
                }
            title = self.title_for(record)
            if not title:
                self._save_status(record, "skipped")
                return {
                    "success": False,
                    "error": "没有可翻译的标题",
                    "avid": avid,
                    "translation_status": "skipped",
                }
            self._save_status(record, "translating")
            translated = self.translator.translate(title)
            state = self._apply_result(record, translated)
            if state == "completed":
                return {
                    "success": True,
                    "avid": avid,
                    "translation_status": state,
                    "original": title,
                    "translated_title": translated,
                }
            return {
                "success": False,
                "error": "翻译返回空结果",
                "avid": avid,
                "translation_status": state,
            }
        except Exception as error:
            # Preserve the single-task failure envelope, including failures before start.
            try:
                record = self.repository.get(avid)
                if record:
                    self._save_status(record, "failed")
            except Exception as cleanup_error:
                logger.error("单条翻译状态收尾异常: {}", cleanup_error)
            return {
                "success": False,
                "error": str(error),
                "avid": avid,
                "translation_status": "failed",
            }

    def translate_batch(
        self, avids: list[str] | None = None, skip_existing: bool = True
    ) -> dict:
        ids: list[int] = []
        try:
            records = self.repository.select(avids, skip_existing)
            total = len(records)
            counts = {"translated": 0, "failed": 0, "skipped": 0}
            if not records:
                return {"success": True, "total": 0, **counts}
            ids = [record.pk for record in records]
            self.repository.mark_translating(ids)
            results = self.translator.batch_translate(
                [self.title_for(record) for record in records]
            )
            if results is None or len(results) != total:
                raise ValueError("批量翻译结果数量与资源数量不一致")
            for record, translated in zip(records, results, strict=True):
                state = self._apply_result(record, translated)
                counts["translated" if state == "completed" else state] += 1
            return {"success": True, "total": total, **counts}
        except Exception as error:
            self._fail_inflight(ids)
            return {"success": False, "error": str(error)}
