from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from PySide6.QtGui import QPixmap

from .resources import resource_path


@dataclass(slots=True)
class Clip:
    frames: list[QPixmap]
    durations: list[int]

    @property
    def aspect_ratio(self) -> float:
        if not self.frames or self.frames[0].height() <= 0:
            return 1.0
        return self.frames[0].width() / self.frames[0].height()


class AssetStore:
    def __init__(self, root: Path | None = None) -> None:
        self.root = root or resource_path("assets", "processed")
        manifest_path = self.root / "manifest.json"
        if not manifest_path.exists():
            raise FileNotFoundError(f"找不到桌宠素材清单：{manifest_path}")
        self.manifest = json.loads(manifest_path.read_text(encoding="utf-8"))["scenes"]
        self._cache: dict[tuple[str, bool], Clip] = {}

    def scene_names(self) -> tuple[str, ...]:
        return tuple(self.manifest)

    def clip(self, name: str, animated: bool = True) -> Clip:
        key = (name, animated)
        if key in self._cache:
            return self._cache[key]
        entry = self.manifest[name]
        animation = entry.get("animation") if animated else None
        if animation:
            frames = [self._pixmap(path) for path in animation["frames"]]
            durations = [int(value) for value in animation["durations"]]
        else:
            frames = [self._pixmap(entry["path"])]
            durations = [1000]
        clip = Clip(frames=frames, durations=durations)
        self._cache[key] = clip
        return clip

    def icon_path(self) -> Path:
        return self.root / "angelina.ico"

    def _pixmap(self, relative: str) -> QPixmap:
        pixmap = QPixmap(str(self.root / relative))
        if pixmap.isNull():
            raise RuntimeError(f"无法载入素材：{relative}")
        return pixmap
