"""Shared HTTP parsing rules, preserving existing defaults and envelopes."""


def _parse_positive_int(value, default: int) -> int:
    try:
        parsed = int(value)
        return parsed if parsed > 0 else default
    except (TypeError, ValueError):
        return default


def _parse_bool(value, default: bool) -> bool:
    if value is None:
        return default
    normalized = str(value).strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    return default


def _parse_choice(value, default: str, choices: set[str]) -> str:
    normalized = str(value or "").strip().lower()
    if normalized in choices:
        return normalized
    return default


def _parse_recommendation_request_params(query_params) -> dict:
    return {
        "limit": _parse_positive_int(query_params.get("limit"), 12),
        "per_seed_limit": _parse_positive_int(query_params.get("per_seed_limit"), 12),
        "actor_seed_limit": _parse_positive_int(
            query_params.get("actor_seed_limit"), 5
        ),
        "genre_seed_limit": _parse_positive_int(
            query_params.get("genre_seed_limit"), 5
        ),
        "exclude_existing": _parse_bool(
            query_params.get("exclude_existing"),
            True,
        ),
        "avoid_recent_recommendations": _parse_bool(
            query_params.get("avoid_recent_recommendations"),
            True,
        ),
        "recent_snapshot_limit": _parse_positive_int(
            query_params.get("recent_snapshot_limit"), 3
        ),
        "recent_item_limit": _parse_positive_int(
            query_params.get("recent_item_limit"), 36
        ),
        "include_hot_board": _parse_bool(
            query_params.get("include_hot_board"),
            True,
        ),
        "include_latest_updates": _parse_bool(
            query_params.get("include_latest_updates"),
            True,
        ),
        "discovery_limit": _parse_positive_int(query_params.get("discovery_limit"), 12),
        "detail_enrichment_limit": _parse_positive_int(
            query_params.get("detail_enrichment_limit"), 24
        ),
        "type_preference": _parse_choice(
            query_params.get("type_preference"),
            "balanced",
            {"actor_heavy", "balanced", "genre_heavy"},
        ),
        "actor_preference": _parse_choice(
            query_params.get("actor_preference"),
            "balanced",
            {"familiar", "balanced", "rare"},
        ),
        "genre_preference": _parse_choice(
            query_params.get("genre_preference"),
            "balanced",
            {"familiar", "balanced", "rare"},
        ),
        "force_refresh_external": _parse_bool(
            query_params.get("force_refresh_external"),
            False,
        ),
    }


def _parse_recommendation_feedback_payload(data) -> dict:
    snapshot_id = data.get("snapshot_id")
    try:
        parsed_snapshot_id = int(snapshot_id)
        if parsed_snapshot_id <= 0:
            raise ValueError
    except (TypeError, ValueError):
        raise ValueError("snapshot_id 参数非法")

    avid = str(data.get("avid", "")).strip().upper()
    if not avid:
        raise ValueError("avid 参数缺失")

    feedback = str(data.get("feedback", "")).strip().lower()
    if feedback not in {"like", "dislike", "clear"}:
        raise ValueError("feedback 仅支持 like、dislike 或 clear")

    return {
        "snapshot_id": parsed_snapshot_id,
        "avid": avid,
        "feedback": feedback,
    }


def _parse_recommendation_seed_block_payload(data) -> dict:
    seed_type = str(data.get("seed_type", "")).strip().lower()
    if seed_type not in {"actor", "genre"}:
        raise ValueError("seed_type 仅支持 actor 或 genre")

    entity_id = data.get("id")
    try:
        parsed_entity_id = int(entity_id)
        if parsed_entity_id <= 0:
            raise ValueError
    except (TypeError, ValueError):
        raise ValueError("id 参数非法")

    reason = str(data.get("reason", "")).strip() or "manual"
    return {
        "seed_type": seed_type,
        "id": parsed_entity_id,
        "reason": reason,
    }


def _parse_recommendation_avid_block_payload(data) -> dict:
    avid = str(data.get("avid", "")).strip().upper()
    if not avid:
        raise ValueError("avid 参数缺失")

    reason = str(data.get("reason", "")).strip() or "manual"
    return {
        "avid": avid,
        "reason": reason,
    }
