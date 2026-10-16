"""Typed registry of user settings: key -> (type, default, bounds). Pure Python.

The `setting` table only stores values the user changed; everything else falls back to these
defaults.
No secret ever goes here: API keys stay in `.env` (see app/config.py).
"""

from dataclasses import dataclass
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

SUPPORTED_UI_LANGUAGES = ("en", "fr")


class SettingError(ValueError):
    """Unknown key or invalid value."""


@dataclass(frozen=True)
class SettingSpec:
    key: str
    type: type
    default: Any
    minimum: float | None = None
    maximum: float | None = None
    choices: tuple[str, ...] | None = None

    def validate(self, value: Any) -> Any:
        """Return the value coerced to the setting's type, or raise SettingError."""
        if isinstance(value, bool) or not isinstance(value, self._accepted_types()):
            raise SettingError(
                f"{self.key}: expected {self.type.__name__}, got {type(value).__name__}"
            )
        value = self.type(value)
        if self.minimum is not None and value < self.minimum:
            raise SettingError(f"{self.key}: {value} is below the minimum {self.minimum}")
        if self.maximum is not None and value > self.maximum:
            raise SettingError(f"{self.key}: {value} is above the maximum {self.maximum}")
        if self.choices is not None and value not in self.choices:
            raise SettingError(f"{self.key}: {value!r} is not one of {', '.join(self.choices)}")
        if self.key == "timezone":
            _check_timezone(value)
        return value

    def _accepted_types(self) -> tuple[type, ...]:
        # An integer is an acceptable float (e.g. tts_rate = 1).
        return (int, float) if self.type is float else (self.type,)


def _check_timezone(name: str) -> None:
    try:
        ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError) as exc:
        raise SettingError(f"timezone: unknown time zone {name!r}") from exc


SETTINGS: dict[str, SettingSpec] = {
    spec.key: spec
    for spec in (
        SettingSpec("daily_time_budget_minutes", int, 45, minimum=10, maximum=240),
        SettingSpec("new_items_per_day", int, 12, minimum=0, maximum=100),
        SettingSpec("target_retention", float, 0.90, minimum=0.70, maximum=0.97),
        SettingSpec("timezone", str, "Africa/Douala"),
        # Hour at which a new study day starts (late-night reviews count for the previous day).
        SettingSpec("day_start_hour", int, 4, minimum=0, maximum=23),
        # Share of a deck's productive cards that must be consolidated before a task is proposed.
        SettingSpec("consolidation_share", float, 0.80, minimum=0.0, maximum=1.0),
        SettingSpec("consolidation_min_stability_days", int, 7, minimum=1),
        SettingSpec("ui_language", str, "en", choices=SUPPORTED_UI_LANGUAGES),
        SettingSpec("tts_rate", float, 1.0, minimum=0.5, maximum=2.0),
    )
}


def spec_for(key: str) -> SettingSpec:
    try:
        return SETTINGS[key]
    except KeyError:
        raise SettingError(f"unknown setting {key!r}") from None


def default_for(key: str) -> Any:
    return spec_for(key).default
