from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication

from angelina_pet.controller import PetController
from angelina_pet.settings import AppSettings, SettingsStore


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="angelina-smoke-") as directory:
        os.environ["APPDATA"] = directory
        store = SettingsStore()
        settings = AppSettings(keyboard_reaction=False, free_walk=False, idle_nudges=False)
        store.save(settings)
        app = QApplication([])
        controller = PetController(app)
        controller.pet.mirrored = True  # Simulate entering office from a flipped walk scene.
        controller._enter_office(manual=True)
        if controller.pet.mirrored:
            raise RuntimeError("office scene inherited the previous walk mirror")
        controller.pet.flash_key("A", duration=2.0)
        QTimer.singleShot(450, controller.quit)
        code = app.exec()
        if controller.pet.scene_name not in {"办公", "坐坐"}:
            raise RuntimeError("unexpected scene after smoke test")
        print("controller smoke test passed")
        return code


if __name__ == "__main__":
    raise SystemExit(main())
