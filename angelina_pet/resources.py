from __future__ import annotations

import os
import sys
from pathlib import Path


def bundle_root() -> Path:
    frozen_root = getattr(sys, "_MEIPASS", None)
    if frozen_root:
        return Path(frozen_root)
    return Path(__file__).resolve().parents[1]


def resource_path(*parts: str) -> Path:
    return bundle_root().joinpath(*parts)


def app_data_dir() -> Path:
    base = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
    path = base / "AngelinaDesktopPet"
    path.mkdir(parents=True, exist_ok=True)
    return path
