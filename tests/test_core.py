from __future__ import annotations

import os
import json
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PIL import Image
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QPoint, QPointF, QRect, QSettings, Qt
from PySide6.QtTest import QTest

from angelina_pet.ai import (
    chat_completion,
    completion_endpoint,
    recommended_reasoning_effort,
    recommended_thinking,
)
from angelina_pet.assets import AssetStore
from angelina_pet.bubble import SpeechBubble
from angelina_pet.keyboard_hook import key_name
from angelina_pet.controller import PetController, scene_should_mirror
from angelina_pet.destination_picker import DestinationPicker
from angelina_pet.mini_chat import MiniChatDialog
from angelina_pet.persona import DIALOGUES, SYSTEM_PROMPT, line
from angelina_pet.pet_window import PetWindow
from angelina_pet.secrets import protect, unprotect
from angelina_pet.settings import AppSettings, SettingsStore


APP = QApplication.instance() or QApplication([])
ROOT = Path(__file__).resolve().parents[1]


class CoreTests(unittest.TestCase):
    def test_completion_endpoint(self) -> None:
        self.assertEqual(
            completion_endpoint("https://api.stepfun.com/step_plan/v1"),
            "https://api.stepfun.com/step_plan/v1/chat/completions",
        )
        explicit = "https://example.test/v1/chat/completions"
        self.assertEqual(completion_endpoint(explicit), explicit)
        self.assertEqual(
            completion_endpoint("https://api.stepfun.com/step_plan"),
            "https://api.stepfun.com/step_plan/v1/chat/completions",
        )
        self.assertEqual(
            completion_endpoint("https://api.stepfun.com/step_plan/v1/messages"),
            "https://api.stepfun.com/step_plan/v1/chat/completions",
        )
        self.assertEqual(
            recommended_reasoning_effort("https://api.stepfun.com/step_plan/v1", "step-3.7-flash"),
            "low",
        )
        self.assertIsNone(recommended_reasoning_effort("https://api.deepseek.com", "deepseek-chat"))
        self.assertEqual(
            recommended_thinking("https://api.deepseek.com", "deepseek-v4-flash"),
            {"type": "disabled"},
        )
        self.assertIsNone(recommended_thinking("https://api.stepfun.com/step_plan/v1", "step-3.7-flash"))

    def test_empty_reasoning_response_retries_without_exposing_reasoning(self) -> None:
        requests: list[dict[str, object]] = []

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self) -> None:  # noqa: N802
                length = int(self.headers["Content-Length"])
                requests.append(json.loads(self.rfile.read(length).decode("utf-8")))
                if len(requests) == 1:
                    result = {"choices": [{"message": {"content": "", "reasoning_content": "内部推理"}}]}
                else:
                    result = {"choices": [{"message": {"content": "收到，博士。"}}]}
                body = json.dumps(result).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, format: str, *args: object) -> None:
                return

        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            result = chat_completion(
                base_url=f"http://127.0.0.1:{server.server_port}/v1",
                api_key="local-test",
                model="step-3.7-flash",
                messages=[{"role": "user", "content": "你好"}],
                max_tokens=32,
            )
        finally:
            server.shutdown()
            server.server_close()
        self.assertEqual(result, "收到，博士。")
        self.assertEqual(len(requests), 2)
        self.assertEqual(requests[1]["max_tokens"], 512)

    def test_null_content_at_budget_limit_is_an_error(self) -> None:
        class Handler(BaseHTTPRequestHandler):
            def do_POST(self) -> None:  # noqa: N802
                length = int(self.headers["Content-Length"])
                self.rfile.read(length)
                result = {
                    "choices": [{"finish_reason": "length", "message": {"content": None, "reasoning": "private"}}]
                }
                body = json.dumps(result).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, format: str, *args: object) -> None:
                return

        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            with self.assertRaisesRegex(RuntimeError, "预算已耗尽"):
                chat_completion(
                    base_url=f"http://127.0.0.1:{server.server_port}/v1",
                    api_key="local-test",
                    model="step-3.7-flash",
                    messages=[{"role": "user", "content": "你好"}],
                    max_tokens=1024,
                )
        finally:
            server.shutdown()
            server.server_close()

    def test_openai_compatible_request(self) -> None:
        received: dict[str, object] = {}

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self) -> None:  # noqa: N802
                length = int(self.headers["Content-Length"])
                received.update(json.loads(self.rfile.read(length).decode("utf-8")))
                body = json.dumps({"choices": [{"message": {"content": "收到，博士。"}}]}).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, format: str, *args: object) -> None:
                return

        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            result = chat_completion(
                base_url=f"http://127.0.0.1:{server.server_port}/v1",
                api_key="local-test",
                model="step-3.7-flash",
                messages=[{"role": "user", "content": "你好"}],
                reasoning_effort="low",
                thinking={"type": "disabled"},
            )
        finally:
            server.shutdown()
            server.server_close()
        self.assertEqual(result, "收到，博士。")
        self.assertEqual(received["model"], "step-3.7-flash")
        self.assertEqual(received["reasoning_effort"], "low")
        self.assertEqual(received["thinking"], {"type": "disabled"})
        self.assertEqual(received["messages"][0]["content"], "你好")

    def test_persona_and_local_lines(self) -> None:
        self.assertIn("安洁莉娜", SYSTEM_PROMPT)
        self.assertIn("博士", SYSTEM_PROMPT)
        for category in ("click", "jump", "squash", "shake", "lonely", "office"):
            self.assertIn(line(category), DIALOGUES[category])

    def test_key_names_do_not_reconstruct_text(self) -> None:
        self.assertEqual(key_name(0x41), "A")
        self.assertEqual(key_name(0x20), "Space")
        self.assertEqual(key_name(0x01), "Key")
        self.assertEqual(key_name(0x87), "F24")

    def test_scene_facing_respects_each_source_asset(self) -> None:
        self.assertFalse(scene_should_mirror("纸飞机", -1))
        self.assertTrue(scene_should_mirror("纸飞机", 1))
        self.assertFalse(scene_should_mirror("骑行", 1))
        self.assertTrue(scene_should_mirror("骑行", -1))

    def test_drag_and_throw_keep_motion_scene_facing_the_velocity(self) -> None:
        class FakePet:
            scene_name = "纸飞机"

            def __init__(self) -> None:
                self._x = 100
                self.mirrored: list[bool] = []

            def x(self) -> int:
                return self._x

            def set_mirrored(self, enabled: bool) -> None:
                self.mirrored.append(enabled)

        controller = PetController.__new__(PetController)
        controller.pet = FakePet()
        controller._last_drag_x = 100
        controller._on_geometry_changed = lambda: None
        controller._touch = lambda: None
        controller._keep_on_screen = lambda: None

        controller._on_dragged(QPoint(130, 20))
        self.assertTrue(controller.pet.mirrored[-1], "纸飞机向右拖时应镜像")
        controller._on_dragged(QPoint(80, 20))
        self.assertFalse(controller.pet.mirrored[-1], "纸飞机向左拖时应保持原朝向")

        controller._on_drag_released(360.0, -80.0)
        self.assertEqual(controller.mode, "thrown")
        self.assertTrue(controller.pet.mirrored[-1])
        controller._on_drag_released(-360.0, -80.0)
        self.assertFalse(controller.pet.mirrored[-1])

    def test_destination_travel_moves_towards_target_and_faces_it(self) -> None:
        class FakePet:
            scene_name = "纸飞机"

            def __init__(self) -> None:
                self._pos = QPoint(80, 60)
                self.mirrored = False
                self.effects: list[dict[str, float]] = []

            def pos(self) -> QPoint:
                return QPoint(self._pos)

            def move(self, point: QPoint) -> None:
                self._pos = QPoint(point)

            def set_mirrored(self, enabled: bool) -> None:
                self.mirrored = enabled

            def set_effect(self, **effect: float) -> None:
                self.effects.append(effect)

        controller = PetController.__new__(PetController)
        controller.pet = FakePet()
        controller.travel_target = QPointF(180, 60)
        controller.travel_speed = 50.0
        controller._tick_travel(0.25, 0.2)
        self.assertEqual(controller.pet.pos(), QPoint(90, 60))
        self.assertTrue(controller.pet.mirrored)
        self.assertTrue(controller.pet.effects)

        controller.travel_target = QPointF(20, 60)
        controller._tick_travel(0.5, 0.2)
        self.assertLess(controller.pet.pos().x(), 90)
        self.assertFalse(controller.pet.mirrored)

    def test_secret_round_trip(self) -> None:
        sample = "not-a-real-key-测试"
        encrypted = protect(sample)
        self.assertNotIn(sample, encrypted)
        self.assertEqual(unprotect(encrypted), sample)

    def test_processed_assets_are_transparent(self) -> None:
        root = ROOT / "assets" / "processed"
        store = AssetStore(root)
        self.assertEqual(len(store.scene_names()), 11)
        for path in list((root / "static").glob("*.png")) + list((root / "animations").glob("*/*.png")):
            with Image.open(path) as image:
                rgba = image.convert("RGBA")
                self.assertEqual(rgba.getpixel((0, 0))[3], 0, path.name)

    def test_pet_window_loads_static_and_animation(self) -> None:
        window = PetWindow(AssetStore(ROOT / "assets" / "processed"))
        window.set_scene("坐坐", animated=True)
        self.assertGreater(len(window.clip.frames), 1)
        window.set_scene("办公", animated=False)
        self.assertEqual(len(window.clip.frames), 1)
        window.set_pet_height(420)
        self.assertEqual(window.height(), 420)
        self.assertGreater(window.width(), 100)

    def test_office_keyboard_overlay_renders(self) -> None:
        window = PetWindow(AssetStore(ROOT / "assets" / "processed"), height=300)
        window.set_scene("办公", animated=False)
        window.flash_key("A", duration=2.0)
        window.show()
        APP.processEvents()
        rendered = window.grab()
        self.assertFalse(rendered.isNull())
        self.assertEqual(rendered.height(), 300)
        baseline = rendered.toImage()
        for label in ("Space", "Enter"):
            window.flash_key(label, duration=2.0)
            APP.processEvents()
            active = window.grab().toImage()
            differences = 0
            left = round(active.width() * 0.20)
            right = round(active.width() * 0.72)
            top = round(active.height() * 0.52)
            bottom = round(active.height() * 0.78)
            for y in range(top, bottom, 2):
                for x in range(left, right, 2):
                    differences += active.pixel(x, y) != baseline.pixel(x, y)
            self.assertGreater(differences, 12, label)
            window.office_key_until = 0.0
            window.update()
            APP.processEvents()
        window.close()

    def test_office_motion_uses_soft_impulses_and_low_frequency_skits(self) -> None:
        window = PetWindow(AssetStore(ROOT / "assets" / "processed"), height=300)
        window.set_scene("办公", animated=False)
        start = window.office_scene_started
        idle = window.office_motion_state(start + 1.0)
        self.assertLess(abs(idle["shift_x"]), 0.002)
        self.assertLess(abs(idle["shift_y"]), 0.003)
        self.assertEqual(idle["bounce"], 0.0)

        window.office_key_started = start + 2.0
        window.office_key_duration = 0.52
        active = window.office_motion_state(start + 2.26)
        settled = window.office_motion_state(start + 2.70)
        self.assertGreater(active["bounce"], 0.7)
        self.assertEqual(settled["bounce"], 0.0)
        self.assertGreater(window.office_motion_state(start + 12.3)["celebration"], 0.9)
        self.assertGreater(window.office_motion_state(start + 16.85)["stretch"], 0.9)
        window.close()

    def test_office_input_immediately_triggers_visible_stars(self) -> None:
        window = PetWindow(AssetStore(ROOT / "assets" / "processed"), height=300)
        window.set_scene("办公", animated=False)
        window.flash_key("Enter", duration=0.52)
        started = window.office_spark_started
        state = window.office_motion_state(started + 0.08)
        self.assertGreater(state["input_spark"], 0.9)
        self.assertGreaterEqual(state["spark_twinkle"], 0.82)
        self.assertEqual(window.office_motion_state(window.office_spark_until + 0.01)["input_spark"], 0.0)
        window.close()

    def test_open_chat_suppresses_overlapping_speech_bubble(self) -> None:
        class FakeChat:
            raised = 0

            def isVisible(self) -> bool:
                return True

            def raise_(self) -> None:
                self.raised += 1

        class FakeBubble:
            shown = 0

            def show_message(self, *_args) -> None:
                self.shown += 1

        controller = PetController.__new__(PetController)
        controller.vision_in_flight = False
        controller.chat = FakeChat()
        controller.bubble = FakeBubble()
        controller.pet = SimpleNamespace(geometry=lambda: QRect(0, 0, 120, 180))
        controller.say("不会盖住聊天窗")
        self.assertEqual(controller.chat.raised, 1)
        self.assertEqual(controller.bubble.shown, 0)

    def test_speech_bubble_is_clickable(self) -> None:
        bubble = SpeechBubble()
        clicked: list[bool] = []
        bubble.clicked.connect(lambda: clicked.append(True))
        bubble.show_message("博士，点一下就可以聊天。", QRect(420, 360, 220, 280), 20000)
        APP.processEvents()
        QTest.mouseClick(bubble, Qt.LeftButton, pos=bubble.rect().center())
        APP.processEvents()
        self.assertEqual(clicked, [True])
        self.assertFalse(bubble.isVisible())
        bubble.close()

    def test_speech_bubble_grows_for_long_text(self) -> None:
        bubble = SpeechBubble()
        bubble.show_message("短句。", QRect(420, 360, 220, 280), 20000)
        short_height = bubble.height()
        bubble.show_message("博士，" + "这是一段需要完整显示而不能被裁掉的较长中文对话。" * 6, QRect(420, 360, 220, 280), 20000)
        self.assertGreater(bubble.height(), short_height)
        bubble.close()


class NewWidgetTests(unittest.TestCase):
    def test_destination_picker_selects_global_point_and_cancels(self) -> None:
        picker = DestinationPicker(topmost=False)
        selected: list[QPoint] = []
        cancelled: list[bool] = []
        picker.selected.connect(selected.append)
        picker.cancelled.connect(lambda: cancelled.append(True))

        anchor = QApplication.primaryScreen().availableGeometry().center()
        picker.show_picker(anchor)
        APP.processEvents()
        self.assertTrue(picker.isVisible())
        chosen = anchor + QPoint(17, 23)
        picker._select(chosen)
        self.assertEqual(selected, [chosen])
        self.assertFalse(picker.isVisible())

        picker.show_picker(anchor)
        APP.processEvents()
        picker._cancel()
        self.assertEqual(cancelled, [True])
        self.assertFalse(picker.isVisible())
        picker.close()

    def test_mini_chat_keeps_only_two_recent_rounds_and_follows_pet(self) -> None:
        chat = MiniChatDialog()
        self.assertTrue(chat.windowFlags() & Qt.WindowStaysOnTopHint)
        chat.append_message("系统", "这条只应进入状态提示")
        for index in range(6):
            author = "博士" if index % 2 == 0 else "安洁莉娜"
            chat.append_message(author, f"消息 {index}")
        APP.processEvents()

        self.assertEqual(len(chat._messages), 4)
        self.assertEqual([text for _, text in chat._messages], ["消息 2", "消息 3", "消息 4", "消息 5"])
        self.assertFalse(chat.system_hint.isHidden())

        area = QApplication.primaryScreen().availableGeometry()
        pet_rect = QRect(area.center().x() - 80, area.center().y() - 120, 160, 200)
        chat.show_near(pet_rect)
        APP.processEvents()
        self.assertTrue(chat.isVisible())
        self.assertTrue(area.contains(chat.geometry()))
        self.assertGreater(chat.y(), pet_rect.bottom())
        original = chat.pos()
        chat.follow(pet_rect.translated(100, 0))
        APP.processEvents()
        self.assertNotEqual(chat.pos(), original)
        self.assertTrue(area.contains(chat.geometry()))
        chat.close()


class PeriodicVisionTests(unittest.TestCase):
    def test_periodic_vision_settings_round_trip_and_clamp(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store = SettingsStore()
            store._settings = QSettings(str(Path(temp_dir) / "settings.ini"), QSettings.IniFormat)

            value = AppSettings(
                vision_enabled=True,
                vision_periodic_enabled=True,
                vision_interval_minutes=1,
                vision_api_key="temporary-test-key",
            )
            store.save(value)
            loaded = store.load()
            self.assertTrue(loaded.vision_periodic_enabled)
            self.assertEqual(loaded.vision_interval_minutes, 5)
            self.assertEqual(loaded.vision_api_key, "temporary-test-key")

            value.vision_interval_minutes = 999
            store.save(value)
            self.assertEqual(store.load().vision_interval_minutes, 240)

    def test_periodic_timer_clamps_interval_and_uses_periodic_request_id(self) -> None:
        class FakeTimer:
            def __init__(self) -> None:
                self.stopped = 0
                self.started: list[int] = []

            def stop(self) -> None:
                self.stopped += 1

            def start(self, interval: int) -> None:
                self.started.append(interval)

        controller = PetController.__new__(PetController)
        controller.periodic_vision_timer = FakeTimer()
        controller.settings = SimpleNamespace(
            vision_periodic_enabled=True,
            vision_enabled=True,
            vision_api_key="temporary-test-key",
            vision_base_url="https://vision.example/v1",
            vision_model="vision-test",
            vision_interval_minutes=1,
        )
        controller._configure_periodic_vision()
        self.assertEqual(controller.periodic_vision_timer.started, [5 * 60_000])

        request_ids: list[str] = []
        controller.vision_in_flight = False
        controller.mode = "idle"
        controller.destination_picker = SimpleNamespace(isVisible=lambda: False)
        controller._begin_screen_capture = request_ids.append
        controller._periodic_screen_check()
        self.assertEqual(request_ids, ["vision-periodic"])

        controller.mode = "drag"
        controller._periodic_screen_check()
        self.assertEqual(request_ids, ["vision-periodic"])

    def test_begin_periodic_capture_sets_request_state_without_real_capture(self) -> None:
        class Hideable:
            def __init__(self, visible: bool = True) -> None:
                self.hidden = False
                self._visible = visible

            def hide(self) -> None:
                self.hidden = True
                self._visible = False

            def isVisible(self) -> bool:
                return self._visible

        class FakePet(Hideable):
            def geometry(self) -> QRect:
                return QRect(100, 100, 120, 180)

        controller = PetController.__new__(PetController)
        controller.vision_in_flight = False
        controller._pending_vision_request_id = None
        controller._pending_vision_screen = None
        controller._vision_chat_was_visible = False
        controller.pet = FakePet()
        controller.bubble = Hideable()
        controller.tether = Hideable()
        controller.chat = Hideable()

        scheduled: list[tuple[int, object]] = []
        with patch("angelina_pet.controller.QTimer.singleShot", side_effect=lambda delay, callback: scheduled.append((delay, callback))):
            controller._begin_screen_capture("vision-periodic")

        self.assertTrue(controller.vision_in_flight)
        self.assertEqual(controller._pending_vision_request_id, "vision-periodic")
        self.assertTrue(controller._vision_chat_was_visible)
        self.assertTrue(controller.pet.hidden)
        self.assertTrue(controller.bubble.hidden)
        self.assertTrue(controller.tether.hidden)
        self.assertTrue(controller.chat.hidden)
        self.assertEqual(scheduled[0][0], 220)


if __name__ == "__main__":
    unittest.main()
