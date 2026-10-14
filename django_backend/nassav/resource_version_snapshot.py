"""Published display metadata excludes source links, headers and personal state."""

from copy import deepcopy
import math

FIELDS = frozenset(
    {
        "avid",
        "original_title",
        "source_title",
        "translated_title",
        "translation_status",
        "release_date",
        "duration",
        "actors",
        "genres",
    }
)


def validated_snapshot(value, avid):
    if not isinstance(value, dict) or set(value) - FIELDS or value.get("avid") != avid:
        raise ValueError("Invalid published metadata fields")
    result = deepcopy(value)
    for key in ("original_title", "source_title", "translated_title", "release_date"):
        text = result.get(key, "")
        if not isinstance(text, str) or len(text) > 4096:
            raise ValueError("Invalid published text")
        result[key] = text
    duration = result.get("duration", 0)
    if (
        type(duration) not in {int, float}
        or not math.isfinite(duration)
        or not 0 <= duration <= 86400
    ):
        raise ValueError("Invalid published duration")
    result["duration"] = duration
    status = result.get("translation_status", "not_requested")
    if status not in {"completed", "skipped", "not_requested"}:
        raise ValueError("Translation must finish before publication")
    result["translation_status"] = status
    for key in ("actors", "genres"):
        names = result.get(key, [])
        if (
            not isinstance(names, list)
            or len(names) > 200
            or any(
                not isinstance(name, str) or not name or len(name) > 256
                for name in names
            )
        ):
            raise ValueError("Invalid published relations")
        result[key] = list(dict.fromkeys(names))
    return result
