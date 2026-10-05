"""Read-only presentation of resource metadata and a scrape's translation child."""

from celery.result import AsyncResult

from nassav.models import AVResource


def translation_details(task_id: str) -> dict:
    """Celery SUCCESS alone does not imply the business translation succeeded."""
    try:
        task = AsyncResult(task_id)
        state = task.state
        if state in {"FAILURE", "REVOKED"}:
            return {"task_id": task_id, "state": "failed", "message": "翻译任务失败"}
        if state != "SUCCESS":
            return {
                "task_id": task_id,
                "state": "translating" if state == "STARTED" else "queued",
            }
        result = task.result
        if not isinstance(result, dict):
            return {"task_id": task_id, "state": "failed", "message": "翻译结果无效"}
        status = result.get("translation_status")
        if status == "completed" and result.get("success"):
            return {"task_id": task_id, "state": "completed"}
        if status == "skipped":
            return {
                "task_id": task_id,
                "state": "skipped",
                "message": "没有可翻译的标题",
            }
        return {"task_id": task_id, "state": "failed", "message": "标题翻译失败"}
    except Exception:
        return {
            "task_id": task_id,
            "state": "unknown",
            "message": "暂时无法读取翻译状态",
        }


def resource_job_details(snapshot: dict) -> dict:
    translation = snapshot.get("translation") or {
        "state": "unavailable",
        "message": "此任务未记录翻译结果",
    }
    if translation.get("task_id"):
        translation = translation_details(translation["task_id"])
    # Read after the translation result so a completed result includes the saved title.
    resource = (
        AVResource.objects.filter(avid=snapshot["avid"])
        .values(
            "avid",
            "original_title",
            "source_title",
            "translated_title",
            "translation_status",
        )
        .first()
    )
    return {
        **snapshot,
        "resource": resource or snapshot.get("resource"),
        "translation": translation,
    }
