"""CAS ownership for a scrape's translation; no late result can update a successor."""

from django.db.models import F

from nassav.models import AVResource
from nassav.translation_contracts import TranslationSuperseded, translation_identity


class OwnedTranslation:
    @staticmethod
    def begin(base: dict, owner: str) -> dict:
        resource = (
            AVResource.objects.select_for_update()
            .filter(pk=base["resource_id"])
            .first()
        )
        if resource is None or translation_identity(resource) != base:
            raise TranslationSuperseded("资源标题或翻译归属已经变化")
        updated = AVResource.objects.filter(
            pk=resource.pk,
            translation_generation=base["generation"],
            translation_owner=base["owner"],
        ).update(
            translation_generation=F("translation_generation") + 1,
            translation_owner=owner,
            translation_status="translating",
        )
        if not updated:
            raise TranslationSuperseded("翻译已被其他执行领取")
        resource.refresh_from_db()
        return translation_identity(resource)

    @staticmethod
    def apply(claim: dict, translated: str | None) -> str:
        resource = AVResource.objects.filter(pk=claim["resource_id"]).first()
        if resource is None or translation_identity(resource) != claim:
            raise TranslationSuperseded("迟到翻译不得覆盖新结果")
        state = (
            "skipped" if not claim["title"] else "completed" if translated else "failed"
        )
        values: dict[str, object] = {"translation_status": state}
        if state == "completed":
            values["translated_title"] = translated
        if not AVResource.objects.filter(
            pk=claim["resource_id"],
            translation_generation=claim["generation"],
            translation_owner=claim["owner"],
            original_title=resource.original_title,
            source_title=resource.source_title,
        ).update(**values):
            raise TranslationSuperseded("迟到翻译不得覆盖新结果")
        return state

    @staticmethod
    def interrupt(claim: dict, *, cancel: bool):
        values: dict[str, object] = {"translation_status": "pending"}
        if cancel:
            values.update(
                translation_owner=None,
                translation_generation=F("translation_generation") + 1,
            )
        AVResource.objects.filter(
            pk=claim["resource_id"],
            translation_generation=claim["generation"],
            translation_owner=claim["owner"],
            translation_status="translating",
        ).update(**values)
