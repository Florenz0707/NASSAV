"""Management health summaries omit payloads, filenames and credential-bearing errors."""


def queue_snapshot(snapshot):
    result = {
        key: snapshot[key]
        for key in ("active_count", "pending_count", "total_count")
        if key in snapshot
    }
    for group in ("active_tasks", "pending_tasks"):
        result[group] = [
            {key: task[key] for key in ("task_id", "state", "task_type") if key in task}
            for task in snapshot.get(group, [])
        ]
    return result


def work_snapshot(snapshot, user):
    return work_snapshots([snapshot], user)[0]


def work_snapshots(snapshots, user):
    from django.db.models import Q
    from nassav.account_policy import is_legacy_operator, is_app_admin
    from nassav.library_models import UserLibraryEntry

    if is_legacy_operator(user):
        return snapshots
    scope = Q(
        user_id=user.pk, access_scope__in=["public", f"legacy:operator:{user.pk}"]
    )
    admin = is_app_admin(user)
    if admin:
        scope |= Q(access_scope="public", pool__state="ready")
    readable = set(
        UserLibraryEntry.objects.filter(
            scope,
            state="active",
            pool__is_available=True,
            pool__resource__isnull=False,
            pool__state__in=["ready", "preparing"],
            pool__canonical_avid__in={row["avid"] for row in snapshots},
        ).values_list("pool__canonical_avid", flat=True)
    )
    results = []
    for snapshot in snapshots:
        result = dict(snapshot)
        if not admin:
            result["allowed_actions"] = []
        if snapshot["avid"] not in readable:
            result["resource"] = {"avid": snapshot["avid"]}
            result["resource_avid"] = None
        if result.get("error_code"):
            result["message"] = "任务需要处理，请查看后端日志"
        results.append(result)
    return results
