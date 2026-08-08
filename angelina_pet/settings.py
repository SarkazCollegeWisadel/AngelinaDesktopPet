from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import QSettings

from .constants import (
    DEFAULT_HEIGHT,
    DEFAULT_STEP_BASE_URL,
    DEFAULT_STEP_MODEL,
    DEFAULT_TEXT_BASE_URL,
    DEFAULT_TEXT_MODEL,
)
from .resources import app_data_dir
from .secrets import protect, unprotect


@dataclass
class AppSettings:
    pet_height: int = DEFAULT_HEIGHT
    x: int = -1
    y: int = -1
    always_on_top: bool = True
    free_walk: bool = True
    leash: bool = False
    keyboard_reaction: bool = True
    idle_nudges: bool = True
    autostart: bool = False
    text_ai_enabled: bool = False
    text_base_url: str = DEFAULT_TEXT_BASE_URL
    text_model: str = DEFAULT_TEXT_MODEL
    text_api_key: str = ""
    vision_enabled: bool = False
    vision_periodic_enabled: bool = False
    vision_interval_minutes: int = 30
    vision_base_url: str = DEFAULT_STEP_BASE_URL
    vision_model: str = DEFAULT_STEP_MODEL
    vision_api_key: str = ""


class SettingsStore:
    def __init__(self) -> None:
        self._settings = QSettings(str(app_data_dir() / "settings.ini"), QSettings.IniFormat)

    def load(self) -> AppSettings:
        s = self._settings
        return AppSettings(
            pet_height=int(s.value("pet/height", DEFAULT_HEIGHT)),
            x=int(s.value("pet/x", -1)),
            y=int(s.value("pet/y", -1)),
            always_on_top=self._bool(s.value("pet/always_on_top", True)),
            free_walk=self._bool(s.value("behavior/free_walk", True)),
            leash=self._bool(s.value("behavior/leash", False)),
            keyboard_reaction=self._bool(s.value("behavior/keyboard_reaction", True)),
            idle_nudges=self._bool(s.value("behavior/idle_nudges", True)),
            autostart=self._bool(s.value("system/autostart", False)),
            text_ai_enabled=self._bool(s.value("ai/text_enabled", False)),
            text_base_url=str(s.value("ai/text_base_url", DEFAULT_TEXT_BASE_URL)),
            text_model=str(s.value("ai/text_model", DEFAULT_TEXT_MODEL)),
            text_api_key=unprotect(str(s.value("ai/text_key", ""))),
            vision_enabled=self._bool(s.value("ai/vision_enabled", False)),
            vision_periodic_enabled=self._bool(s.value("ai/vision_periodic_enabled", False)),
            vision_interval_minutes=max(5, min(240, int(s.value("ai/vision_interval_minutes", 30)))),
            vision_base_url=str(s.value("ai/vision_base_url", DEFAULT_STEP_BASE_URL)),
            vision_model=str(s.value("ai/vision_model", DEFAULT_STEP_MODEL)),
            vision_api_key=unprotect(str(s.value("ai/vision_key", ""))),
        )

    def save(self, value: AppSettings) -> None:
        s = self._settings
        s.setValue("pet/height", value.pet_height)
        s.setValue("pet/x", value.x)
        s.setValue("pet/y", value.y)
        s.setValue("pet/always_on_top", value.always_on_top)
        s.setValue("behavior/free_walk", value.free_walk)
        s.setValue("behavior/leash", value.leash)
        s.setValue("behavior/keyboard_reaction", value.keyboard_reaction)
        s.setValue("behavior/idle_nudges", value.idle_nudges)
        s.setValue("system/autostart", value.autostart)
        s.setValue("ai/text_enabled", value.text_ai_enabled)
        s.setValue("ai/text_base_url", value.text_base_url.strip())
        s.setValue("ai/text_model", value.text_model.strip())
        s.setValue("ai/text_key", protect(value.text_api_key.strip()))
        s.setValue("ai/vision_enabled", value.vision_enabled)
        s.setValue("ai/vision_periodic_enabled", value.vision_periodic_enabled)
        s.setValue("ai/vision_interval_minutes", max(5, min(240, value.vision_interval_minutes)))
        s.setValue("ai/vision_base_url", value.vision_base_url.strip())
        s.setValue("ai/vision_model", value.vision_model.strip())
        s.setValue("ai/vision_key", protect(value.vision_api_key.strip()))
        s.sync()

    @staticmethod
    def _bool(value: object) -> bool:
        if isinstance(value, bool):
            return value
        return str(value).strip().lower() in {"1", "true", "yes", "on"}
