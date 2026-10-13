"""Canonical, current preference keys and value rules; independent of ORM."""

from dataclasses import dataclass
import math

PreferenceValue = str | bool | int | float


class InvalidPreference(ValueError):
    def __init__(self, message, *, key=None):
        self.key = key
        super().__init__(message)


@dataclass(frozen=True)
class PreferenceDefinition:
    default: PreferenceValue
    choices: tuple[PreferenceValue, ...] = ()
    max_length: int | None = None

    def __post_init__(self):
        self.validate(self.default)

    def validate(self, value):
        if type(value) is not type(self.default):
            raise ValueError("类型错误")
        if isinstance(value, float) and not math.isfinite(value):
            raise ValueError("必须是有限数值")
        if isinstance(value, str):
            if not value.strip():
                raise ValueError("不能为空")
            if self.max_length is not None and len(value) > self.max_length:
                raise ValueError(f"最多{self.max_length}字符")
        if self.choices and value not in self.choices:
            raise ValueError("不支持的取值")


PREFERENCE_DEFINITIONS = {
    "enable_avatar": PreferenceDefinition("true", ("true", "false")),
    "display_title": PreferenceDefinition(
        "source_title", ("original_title", "source_title", "translated_title")
    ),
    "font_family": PreferenceDefinition("Mplus2", max_length=100),
    "color_mode": PreferenceDefinition("dark", ("light", "dark")),
    "search_result_display_style": PreferenceDefinition("grid", ("grid", "masonry")),
    "default_external_search_source": PreferenceDefinition(
        "jable", ("jable", "missav")
    ),
}


def validate_preferences(changes):
    if not isinstance(changes, dict):
        raise InvalidPreference("设置必须是键值对象")
    for key, value in changes.items():
        definition = PREFERENCE_DEFINITIONS.get(key)
        if definition is None:
            raise InvalidPreference(f"不支持的设置项: {key}", key=key)
        try:
            definition.validate(value)
        except ValueError as error:
            raise InvalidPreference(f"{key}: {error}", key=key) from error


def effective_preferences(overrides):
    # Unsupported or malformed stored values never become business configuration.
    overrides = overrides if isinstance(overrides, dict) else {}
    result = {}
    for key, definition in PREFERENCE_DEFINITIONS.items():
        value = overrides.get(key, definition.default)
        try:
            definition.validate(value)
        except ValueError:
            value = definition.default
        result[key] = value
    return result
