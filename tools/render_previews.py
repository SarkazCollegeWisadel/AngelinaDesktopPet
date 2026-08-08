from __future__ import annotations

import os
import sys
import time
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from PySide6.QtCore import QRect, Qt
from PySide6.QtWidgets import QApplication

from angelina_pet.assets import AssetStore
from angelina_pet.bubble import SpeechBubble
from angelina_pet.destination_picker import DestinationPicker
from angelina_pet.mini_chat import MiniChatDialog
from angelina_pet.pet_window import PetWindow


def main() -> None:
    app = QApplication.instance() or QApplication([])
    hide_native = os.environ.get("ANGELINA_PREVIEW_HIDDEN") == "1"
    target = ROOT / "tmp" / "previews"
    target.mkdir(parents=True, exist_ok=True)
    window = PetWindow(AssetStore(ROOT / "assets" / "processed"), height=480, topmost=False)
    if hide_native:
        window.setAttribute(Qt.WA_DontShowOnScreen, True)
    for scene, animated, key in (("坐坐", True, ""), ("办公", False, "A"), ("看书", True, "")):
        window.set_scene(scene, animated=animated)
        if key:
            window.flash_key(key, duration=5.0)
        window.show()
        app.processEvents()
        window.grab().save(str(target / f"{scene}.png"))
        if scene == "办公":
            window.office_scene_started = time.monotonic() - 12.3
            window.office_key_started = time.monotonic() - window.office_key_duration / 2
            window.update()
            app.processEvents()
            window.grab().save(str(target / "办公-Q弹与彩蛋.png"))
            window.office_key_until = 0.0
            window.flash_mouse(duration=5.0)
            app.processEvents()
            window.grab().save(str(target / "办公-鼠标.png"))
            window.office_mouse_until = 0.0
            window.scene_name = ""
            window.update()
            app.processEvents()
            window.grab().save(str(target / "办公-无反馈层.png"))
            window.scene_name = scene
    bubble = SpeechBubble()
    if hide_native:
        bubble.setAttribute(Qt.WA_DontShowOnScreen, True)
    bubble.show_message("博士，今天的进度也有好好向前走哦。要不要坐下来和我聊一会儿？", QRect(480, 430, 260, 300), 30000)
    app.processEvents()
    bubble.grab().save(str(target / "气泡.png"))
    bubble.close()
    chat = MiniChatDialog()
    chat.set_topmost(False)
    if hide_native:
        chat.setAttribute(Qt.WA_DontShowOnScreen, True)
    chat.append_message("博士", "今天的任务有点多，你陪我一会儿吧。")
    chat.append_message("安洁莉娜", "当然。先挑最小的一件，我们一起把它稳稳做完~")
    chat.append_message("博士", "好，那就从这一步开始。")
    chat.append_message("安洁莉娜", "嗯，我把小键盘也拉过来啦。")
    chat.show_near(QRect(480, 160, 260, 260), activate=False)
    app.processEvents()
    chat.grab().save(str(target / "两轮小聊天气泡.png"))
    chat.close()
    picker = DestinationPicker(topmost=False)
    if hide_native:
        picker.setAttribute(Qt.WA_DontShowOnScreen, True)
    picker.show_picker(QApplication.primaryScreen().availableGeometry().center())
    app.processEvents()
    picker.grab().save(str(target / "目的地选点.png"))
    picker.close()
    window.close()
    print(target)


if __name__ == "__main__":
    main()
