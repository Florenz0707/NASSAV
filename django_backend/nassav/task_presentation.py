"""Safe public task snapshots shared by HTTP and compatibility projections."""


def public_snapshot(snapshot: dict) -> dict:
    from nassav.models import AVResource

    result = {key: value for key, value in snapshot.items() if key != "checkpoint"}
    result["progress"] = snapshot["checkpoint"].get("progress")
    resource = (
        AVResource.objects.filter(avid=snapshot["avid"])
        .values("avid", "original_title", "source_title", "translated_title")
        .first()
    )
    existing = resource is not None
    if resource is None:
        prepared = snapshot["checkpoint"].get("prepared") or {}
        info = prepared.get("info") or {}
        metadata = prepared.get("metadata") or {}
        resource = {
            "avid": snapshot["avid"],
            "original_title": metadata.get("title"),
            "source_title": info.get("source_title"),
            "translated_title": None,
        }
    result["resource"] = resource
    result["resource_avid"] = (
        snapshot["avid"] if snapshot["resource_saved"] or existing else None
    )
    result["workflow_state"], result["workflow_stage"] = (
        snapshot["state"],
        snapshot["stage"],
    )
    if result["error_code"] == "DOWNLOAD_FAILED":
        result["message"] = "下载失败，请查看后端日志"
    if result["cleanup_state"] == "failed":
        result["cleanup_message"] = "清理失败，请检查目录权限或文件提交日志"
    return result
