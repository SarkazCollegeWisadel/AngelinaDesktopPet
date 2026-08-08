from __future__ import annotations

import base64
import math
import random
import time
from collections import deque

from PySide6.QtCore import QByteArray, QBuffer, QIODevice, QPoint, QPointF, QRect, Qt, QTimer
from PySide6.QtGui import QAction, QActionGroup, QIcon
from PySide6.QtWidgets import QApplication, QMenu, QMessageBox, QSystemTrayIcon

from .ai import AIService, recommended_reasoning_effort, recommended_thinking
from .assets import AssetStore
from .bubble import SpeechBubble
from .constants import (
    ALL_CHARACTER_SCENES,
    IDLE_SCENE,
    LOCOMOTION_SCENES,
    OFFICE_SCENE,
    READING_SCENE,
    SCENE_SOURCE_FACING,
)
from .destination_picker import DestinationPicker
from .dialogs import SettingsDialog
from .keyboard_hook import KeyboardHook
from .mini_chat import MiniChatDialog
from .persona import SYSTEM_PROMPT, event_prompt, line, vision_prompt
from .pet_window import PetWindow, TetherOverlay
from .resources import app_data_dir
from .settings import AppSettings, SettingsStore
from .startup import open_app_data, set_autostart


def cleaned_reply(text: str, limit: int = 180) -> str:
    result = text.strip().replace("**", "").replace("`", "")
    if result.startswith("安洁莉娜："):
        result = result[6:].lstrip()
    return result[:limit]


def scene_should_mirror(scene_name: str, direction: int) -> bool:
    """Return whether a scene must be flipped to face its travel direction."""
    desired = -1 if direction < 0 else 1
    return SCENE_SOURCE_FACING.get(scene_name, 1) != desired


def local_chat_reply(message: str) -> str:
    text = message.strip().lower()
    if any(word in text for word in ("累", "困", "疲惫", "不想干")):
        return random.choice((
            "那就先停两分钟吧。博士休息的时候，我替你看着进度。",
            "辛苦了。先喝口水、伸伸肩膀，回来时我还在这里。",
            "累不是做得不够好，是已经努力很久了哦。",
        ))
    if any(word in text for word in ("早", "起床", "早安")):
        return "早安，博士！今天的第一封好消息，就由我送来吧。"
    if any(word in text for word in ("晚安", "睡觉", "睡了")):
        return "晚安，博士。剩下的路明天再走也来得及，做个轻飘飘的好梦。"
    if any(word in text for word in ("喜欢", "可爱", "漂亮")):
        return "诶、诶？这么突然……嗯哼哼~这句话我会好好收下的。"
    if any(word in text for word in ("加油", "工作", "学习", "代码")):
        return "好！我也把小键盘拉出来。博士负责向前，我负责陪你到完成。"
    if "吃" in text:
        return "说到这个，我想起还有一小块柑橘奶油千层……要分你一半吗？"
    return random.choice((
        "嗯，我在听。博士慢慢说就好。",
        "这封心情我收到啦。要是还有下一封，也交给我吧。",
        "原来博士在想这个呀……让我陪你一起想一会儿。",
        "嗯哼哼~能这样和博士聊几句，我今天也有精神了。",
    ))


class PetController:
    def __init__(self, app: QApplication) -> None:
        self.app = app
        self.app.setQuitOnLastWindowClosed(False)
        self.store = SettingsStore()
        self.settings = self.store.load()
        self.assets = AssetStore()
        self.pet = PetWindow(self.assets, self.settings.pet_height, self.settings.always_on_top)
        self.bubble = SpeechBubble()
        self.bubble.set_topmost(self.settings.always_on_top)
        self.tether = TetherOverlay(self.settings.always_on_top)
        self.ai = AIService()
        self.keyboard = KeyboardHook()
        self.destination_picker = DestinationPicker(True)
        self.chat: MiniChatDialog | None = None
        self.chat_history: list[dict[str, str]] = []

        self.mode = "idle"
        self.velocity = QPointF()
        self.effect_started = 0.0
        self.effect_duration = 0.0
        self.effect_base_pos = QPoint()
        self.behavior_ends = 0.0
        self.walk_speed = 0.0
        self.walk_base_y = 0
        self.travel_target = QPointF()
        self.travel_speed = 0.0
        self._last_drag_x: int | None = None
        self.click_index = 0
        self.last_tick = time.monotonic()
        self.last_touch = time.monotonic()
        self.next_nudge = self.last_touch + random.uniform(150, 260)
        self.next_behavior = self.last_touch + random.uniform(12, 32)
        self.last_ai_event = 0.0
        self.key_times: deque[float] = deque(maxlen=32)
        self.last_key_time = 0.0
        self.office_manual = False
        self.leash_anchor = QPointF()
        self.leash_radius = 220.0
        self._pending_vision_screen = None
        self._pending_vision_request_id: str | None = None
        self._vision_chat_was_visible = False
        self.vision_in_flight = False

        self._connect_signals()
        self.pet.set_scene(IDLE_SCENE, animated=True)
        self._restore_position()
        self._setup_tray()
        self.pet.show()
        self.pet.raise_()
        if self.settings.leash:
            self._enable_leash(True)
        if self.settings.keyboard_reaction:
            self.keyboard.start()

        self.tick_timer = QTimer()
        self.tick_timer.setTimerType(Qt.PreciseTimer)
        self.tick_timer.timeout.connect(self._tick)
        self.tick_timer.start(16)

        self.periodic_vision_timer = QTimer()
        self.periodic_vision_timer.timeout.connect(self._periodic_screen_check)
        self._configure_periodic_vision()

    def _connect_signals(self) -> None:
        self.pet.clicked.connect(self._on_clicked)
        self.pet.drag_started.connect(self._on_drag_started)
        self.pet.dragged.connect(self._on_dragged)
        self.pet.drag_released.connect(self._on_drag_released)
        self.pet.context_requested.connect(self._show_context_menu)
        self.pet.height_requested.connect(self._on_height_changed)
        self.pet.geometry_changed.connect(self._on_geometry_changed)
        self.keyboard.key_pressed.connect(self._on_key_pressed)
        self.keyboard.error.connect(self.say)
        self.bubble.clicked.connect(self.open_chat)
        self.destination_picker.selected.connect(self._travel_to)
        self.ai.completed.connect(self._on_ai_completed)
        self.ai.failed.connect(self._on_ai_failed)

    def _restore_position(self) -> None:
        screen = QApplication.primaryScreen()
        area = screen.availableGeometry()
        if self.settings.x < 0 or self.settings.y < 0:
            self.pet.move(area.right() - self.pet.width() - 36, area.bottom() - self.pet.height() + 1)
        else:
            self.pet.move(self.settings.x, self.settings.y)
            self._keep_on_screen()

    def _setup_tray(self) -> None:
        icon = QIcon(str(self.assets.icon_path()))
        self.app.setWindowIcon(icon)
        self.tray = QSystemTrayIcon(icon, self.app)
        self.tray.setToolTip("安洁莉娜桌宠")
        self.tray.setContextMenu(self._build_menu())
        self.tray.activated.connect(self._tray_activated)
        self.tray.show()

    def _tray_activated(self, reason) -> None:
        if reason in (QSystemTrayIcon.DoubleClick, QSystemTrayIcon.Trigger):
            self.pet.show()
            self.pet.raise_()
            if self.chat and self.chat.isVisible():
                self.chat.raise_()

    def _build_menu(self) -> QMenu:
        menu = QMenu("安洁莉娜")
        chat_action = menu.addAction("和安洁莉娜聊天…")
        chat_action.triggered.connect(self.open_chat)
        vision_action = menu.addAction("看看博士的屏幕…")
        vision_action.triggered.connect(self.analyze_screen)
        menu.addSeparator()

        office_action = menu.addAction("拉出小键盘办公")
        office_action.triggered.connect(lambda: self._enter_office(manual=True))
        reading_action = menu.addAction("递给她一本书 / 收起书")
        reading_action.triggered.connect(self._toggle_reading)
        destination_action = menu.addAction("让她去指定地点…")
        destination_action.triggered.connect(self._choose_destination)
        leash_action = menu.addAction("系上小链子")
        leash_action.setCheckable(True)
        leash_action.setChecked(self.settings.leash)
        leash_action.toggled.connect(self._enable_leash)

        free_walk = menu.addAction("自由走动")
        free_walk.setCheckable(True)
        free_walk.setChecked(self.settings.free_walk)
        free_walk.toggled.connect(self._toggle_walk)

        scene_menu = menu.addMenu("换个动作")
        for name in ALL_CHARACTER_SCENES:
            action = scene_menu.addAction(name)
            action.triggered.connect(lambda checked=False, scene=name: self._manual_scene(scene))

        size_menu = menu.addMenu("调整大小")
        size_group = QActionGroup(size_menu)
        for label, height in (("很小 160px", 160), ("小 220px", 220), ("默认 300px", 300), ("大 420px", 420), ("很大 560px", 560)):
            action = QAction(label, size_group)
            action.triggered.connect(lambda checked=False, value=height: self.pet.set_pet_height(value))
            size_menu.addAction(action)

        menu.addSeparator()
        topmost = menu.addAction("始终置顶")
        topmost.setCheckable(True)
        topmost.setChecked(self.settings.always_on_top)
        topmost.toggled.connect(self._toggle_topmost)
        autostart = menu.addAction("开机启动")
        autostart.setCheckable(True)
        autostart.setChecked(self.settings.autostart)
        autostart.toggled.connect(self._toggle_autostart)
        settings_action = menu.addAction("AI 与隐私设置…")
        settings_action.triggered.connect(self.open_settings)
        data_action = menu.addAction("打开本地设置目录")
        data_action.triggered.connect(lambda: open_app_data(app_data_dir()))
        menu.addSeparator()
        quit_action = menu.addAction("退出程序")
        quit_action.triggered.connect(self.quit)
        return menu

    def _show_context_menu(self, position: QPoint) -> None:
        self._touch()
        menu = self._build_menu()
        menu.exec(position)

    def _on_clicked(self) -> None:
        self._touch()
        if self.mode == "reading":
            self._return_idle()
            self.say("书签夹好啦。博士现在想做点别的吗？")
            return
        if self.mode == "office":
            self.pet.flash_mouse()
            self.behavior_ends = time.monotonic() + (45.0 if self.office_manual else 10.0)
            if random.random() < 0.28:
                self.say(random.choice(("鼠标也有认真工作哦。", "咔哒——这一步替博士点好啦。", "嗯，下一项任务交给我吧。")))
            return
        actions = ("jump", "squash", "shake")
        effect = actions[self.click_index % len(actions)]
        self.click_index += 1
        self._start_effect(effect)

    def _start_effect(self, effect: str) -> None:
        self.mode = effect
        self.effect_started = time.monotonic()
        self.effect_duration = {"jump": 0.72, "squash": 0.62, "shake": 0.68}[effect]
        self.effect_base_pos = self.pet.pos()
        self.velocity = QPointF()
        self.say(line(effect))
        self._maybe_ai_event({"jump": "博士轻点了她，她轻快地跳了一下", "squash": "博士把桌宠压扁后她弹了回来", "shake": "博士碰了她，她左右晃了晃"}[effect])

    def _on_drag_started(self) -> None:
        self._touch()
        self.mode = "drag"
        self.velocity = QPointF()
        self._last_drag_x = self.pet.x()
        self.pet.set_effect()

    def _on_dragged(self, target: QPoint) -> None:
        if self._last_drag_x is not None and self.pet.scene_name in SCENE_SOURCE_FACING:
            delta_x = target.x() - self._last_drag_x
            if abs(delta_x) >= 2:
                self.pet.set_mirrored(scene_should_mirror(self.pet.scene_name, delta_x))
        self._last_drag_x = target.x()
        self._on_geometry_changed()

    def _on_drag_released(self, vx: float, vy: float) -> None:
        self._touch()
        self._last_drag_x = None
        speed = math.hypot(vx, vy)
        if speed > 120:
            scale = min(1.0, 1200.0 / speed)
            self.velocity = QPointF(vx * scale, vy * scale)
            self.mode = "thrown"
            if self.pet.scene_name in SCENE_SOURCE_FACING and abs(vx) >= 18:
                self.pet.set_mirrored(scene_should_mirror(self.pet.scene_name, vx))
        else:
            self._return_idle(keep_position=True)
        self._keep_on_screen()

    def _on_height_changed(self, height: int) -> None:
        self.settings.pet_height = height
        self._keep_on_screen()
        self._save_settings()

    def _on_geometry_changed(self) -> None:
        self.bubble.follow(self.pet.geometry())
        self._update_tether()
        if self.chat:
            self.chat.follow(self.pet.geometry())
            if self.chat.isVisible():
                self.chat.raise_()

    def _tick(self) -> None:
        now = time.monotonic()
        dt = min(0.05, max(0.001, now - self.last_tick))
        self.last_tick = now

        if self.mode in {"jump", "squash", "shake"}:
            self._tick_effect(now)
        elif self.mode == "thrown":
            self._tick_thrown(dt)
        elif self.mode == "walk":
            self._tick_walk(now, dt)
        elif self.mode == "travel":
            self._tick_travel(now, dt)
        elif self.mode == "animation" and now >= self.behavior_ends:
            self._return_idle(keep_position=True)
        elif self.mode == "office" and not self.office_manual and now - self.last_key_time > 10.0:
            self._return_idle(keep_position=True)
        elif self.mode == "office" and self.office_manual and now >= self.behavior_ends:
            self._return_idle(keep_position=True)

        if self.mode == "idle" and self.settings.free_walk and now >= self.next_behavior:
            self._random_behavior()
        if self.settings.idle_nudges and now >= self.next_nudge:
            self.say(line("lonely"))
            self.next_nudge = now + random.uniform(210, 480)
        if self.pet.scene_name == OFFICE_SCENE:
            self.pet.update()

    def _tick_effect(self, now: float) -> None:
        progress = min(1.0, (now - self.effect_started) / self.effect_duration)
        wave = math.sin(progress * math.pi)
        if self.mode == "jump":
            self.pet.move(self.effect_base_pos.x(), self.effect_base_pos.y() - round(wave * min(95, self.pet.pet_height * 0.32)))
            self.pet.set_effect(1.0 - wave * 0.08, 1.0 + wave * 0.08)
        elif self.mode == "squash":
            self.pet.set_effect(1.0 + wave * 0.38, 1.0 - wave * 0.42)
        else:
            shake = math.sin(progress * math.pi * 10) * (1.0 - progress) * 14
            self.pet.move(self.effect_base_pos.x() + round(shake), self.effect_base_pos.y())
            self.pet.set_effect(rotation=math.sin(progress * math.pi * 8) * 5 * (1.0 - progress))
        if progress >= 1.0:
            self.pet.move(self.effect_base_pos)
            self.pet.set_effect()
            self._return_idle(keep_position=True)

    def _tick_thrown(self, dt: float) -> None:
        pos = QPointF(self.pet.pos()) + self.velocity * dt
        self.velocity.setY(self.velocity.y() + 1500.0 * dt)
        area = self._available_geometry(pos.toPoint())
        min_x, max_x = area.left(), area.right() - self.pet.width() + 1
        min_y, floor_y = area.top(), area.bottom() - self.pet.height() + 1
        if pos.x() < min_x or pos.x() > max_x:
            pos.setX(max(min_x, min(max_x, pos.x())))
            self.velocity.setX(-self.velocity.x() * 0.64)
        if pos.y() < min_y:
            pos.setY(min_y)
            self.velocity.setY(abs(self.velocity.y()) * 0.6)
        if pos.y() >= floor_y:
            pos.setY(floor_y)
            if abs(self.velocity.y()) > 110:
                self.velocity.setY(-abs(self.velocity.y()) * 0.42)
                self.velocity.setX(self.velocity.x() * 0.82)
            else:
                self.velocity.setY(0)
                self.velocity.setX(self.velocity.x() * 0.88)
        pos = self._apply_leash(pos)
        if self.pet.scene_name in SCENE_SOURCE_FACING and abs(self.velocity.x()) >= 18:
            self.pet.set_mirrored(scene_should_mirror(self.pet.scene_name, self.velocity.x()))
        self.pet.move(pos.toPoint())
        if pos.y() >= floor_y - 1 and abs(self.velocity.x()) < 18 and abs(self.velocity.y()) < 18:
            self._return_idle(keep_position=True)

    def _tick_walk(self, now: float, dt: float) -> None:
        pos = QPointF(self.pet.pos())
        pos.setX(pos.x() + self.walk_speed * dt)
        area = self._available_geometry(pos.toPoint())
        left, right = area.left(), area.right() - self.pet.width() + 1
        if pos.x() <= left or pos.x() >= right:
            pos.setX(max(left, min(right, pos.x())))
            self.walk_speed *= -1
            self.pet.set_mirrored(scene_should_mirror(self.pet.scene_name, self.walk_speed))
        pos.setY(self.walk_base_y - abs(math.sin(now * 5.2)) * min(7, self.pet.pet_height * 0.025))
        pos = self._apply_leash(pos)
        self.pet.move(pos.toPoint())
        if now >= self.behavior_ends:
            self._return_idle(keep_position=True)

    def _tick_travel(self, now: float, dt: float) -> None:
        pos = QPointF(self.pet.pos())
        delta = self.travel_target - pos
        distance = math.hypot(delta.x(), delta.y())
        step = self.travel_speed * dt
        if distance <= max(3.0, step):
            self.pet.move(self.travel_target.toPoint())
            self.pet.set_effect()
            self._return_idle(keep_position=True)
            self.say(random.choice(("到啦，博士。", "目的地抵达——稳稳落地。", "安洁莉娜已送达，请签收~")))
            return
        if abs(delta.x()) >= 1.0:
            self.pet.set_mirrored(scene_should_mirror(self.pet.scene_name, delta.x()))
        ratio = step / distance
        next_pos = pos + delta * ratio
        self.pet.set_effect(rotation=math.sin(now * 7.2) * 1.8)
        self.pet.move(next_pos.toPoint())

    def _random_behavior(self) -> None:
        choice = random.random()
        if choice < 0.48:
            self._start_walk()
        elif choice < 0.88:
            name = random.choice(tuple(scene for scene in ALL_CHARACTER_SCENES if scene != IDLE_SCENE))
            self.pet.set_scene(name, animated=True)
            self.mode = "animation"
            self.behavior_ends = time.monotonic() + random.uniform(3.8, 8.5)
            self._keep_on_screen()
        else:
            self.say(line("idle"))
            self.next_behavior = time.monotonic() + random.uniform(12, 38)

    def _start_walk(self) -> None:
        name = random.choice(LOCOMOTION_SCENES)
        self.pet.set_scene(name, animated=True)
        self.mode = "walk"
        direction = random.choice((-1, 1))
        self.walk_speed = direction * random.uniform(38, 86)
        self.pet.set_mirrored(scene_should_mirror(name, direction))
        area = self._available_geometry(self.pet.pos())
        self.walk_base_y = area.bottom() - self.pet.height() + 1
        self.pet.move(self.pet.x(), self.walk_base_y)
        self.behavior_ends = time.monotonic() + random.uniform(5.5, 13.0)
        if random.random() < 0.35:
            self.say(line("walk"))

    def _choose_destination(self) -> None:
        self._touch()
        self.destination_picker.show_picker(self.pet.geometry().center())

    def _travel_to(self, point: QPoint) -> None:
        screen = QApplication.screenAt(point) or QApplication.primaryScreen()
        if screen is None:
            return
        area = screen.availableGeometry()
        target = QPointF(point.x() - self.pet.width() / 2, point.y() - self.pet.height() + 1)
        target.setX(max(area.left(), min(area.right() - self.pet.width() + 1, target.x())))
        target.setY(max(area.top(), min(area.bottom() - self.pet.height() + 1, target.y())))
        target = self._limit_destination_to_leash(target)

        delta_x = target.x() - self.pet.x()
        name = random.choice(LOCOMOTION_SCENES)
        self.mode = "travel"
        self.office_manual = False
        self.velocity = QPointF()
        self.travel_target = target
        self.travel_speed = random.uniform(145.0, 210.0)
        self.pet.set_effect()
        self.pet.set_scene(name, animated=True)
        self.pet.set_mirrored(scene_should_mirror(name, -1 if delta_x < 0 else 1))
        self.say(random.choice(("好，目的地记住啦。", "收到，这就出发~", "路线确认，交给我吧。")))

    def _limit_destination_to_leash(self, pos: QPointF) -> QPointF:
        if not self.settings.leash or self.leash_anchor.isNull():
            return pos
        center = QPointF(pos.x() + self.pet.width() / 2, pos.y() + self.pet.height() * 0.65)
        delta = center - self.leash_anchor
        distance = math.hypot(delta.x(), delta.y())
        if distance <= self.leash_radius or distance == 0:
            return pos
        limited = self.leash_anchor + delta * (self.leash_radius / distance)
        return QPointF(limited.x() - self.pet.width() / 2, limited.y() - self.pet.height() * 0.65)

    def _return_idle(self, keep_position: bool = True) -> None:
        bottom = self.pet.y() + self.pet.height()
        center = self.pet.x() + self.pet.width() // 2
        self.mode = "idle"
        self.office_manual = False
        self.velocity = QPointF()
        self.pet.set_effect()
        self.pet.set_mirrored(False)
        self.pet.set_scene(IDLE_SCENE, animated=True)
        if keep_position:
            self.pet.move(center - self.pet.width() // 2, bottom - self.pet.height())
        self._keep_on_screen()
        self.next_behavior = time.monotonic() + random.uniform(12, 42)

    def _manual_scene(self, name: str) -> None:
        self._touch()
        self.pet.set_mirrored(False)
        self.pet.set_scene(name, animated=True)
        self.mode = "animation"
        self.behavior_ends = time.monotonic() + random.uniform(6, 12)
        self._keep_on_screen()

    def _toggle_reading(self) -> None:
        self._touch()
        if self.mode == "reading":
            self._return_idle(keep_position=True)
            return
        self.mode = "reading"
        self.velocity = QPointF()
        self.pet.set_mirrored(False)
        self.pet.set_scene(READING_SCENE, animated=True)
        self._keep_on_screen()
        self.say(line("reading"))

    def _enter_office(self, manual: bool = False) -> None:
        if self.mode == "drag":
            return
        first_entry = self.mode != "office"
        self.mode = "office"
        self.office_manual = manual
        self.behavior_ends = time.monotonic() + (45.0 if manual else 10.0)
        self.velocity = QPointF()
        self.pet.set_mirrored(False)
        self.pet.set_scene(OFFICE_SCENE, animated=False)
        self._keep_on_screen()
        if first_entry:
            self.say(line("office"))

    def _on_key_pressed(self, vk_code: int, label: str) -> None:
        if not self.settings.keyboard_reaction:
            return
        now = time.monotonic()
        self.last_key_time = now
        if label not in {"Shift", "Ctrl", "Alt", "Key"}:
            self.key_times.append(now)
        while self.key_times and now - self.key_times[0] > 3.2:
            self.key_times.popleft()
        if self.mode == "office":
            self.pet.flash_key(label, duration=0.52)
            self.behavior_ends = now + (45.0 if self.office_manual else 10.0)
        elif len(self.key_times) >= 6 and self.mode in {"idle", "animation", "walk"}:
            self._enter_office(manual=False)
            self.pet.flash_key(label, duration=0.52)
            self.key_times.clear()

    def _enable_leash(self, enabled: bool) -> None:
        self.settings.leash = bool(enabled)
        if enabled:
            rect = self.pet.geometry()
            self.leash_anchor = QPointF(rect.center().x() - min(140, rect.width() * 0.45), rect.bottom() - 10)
            self._update_tether()
            self.pet.raise_()
        else:
            self.tether.hide()
        self._save_settings()

    def _update_tether(self) -> None:
        if not self.settings.leash or self.leash_anchor.isNull():
            return
        rect = self.pet.geometry()
        target = QPointF(rect.center().x(), rect.center().y() + rect.height() * 0.22)
        self.tether.update_line(self.leash_anchor, target)
        self.pet.raise_()
        if self.chat and self.chat.isVisible():
            self.chat.raise_()

    def _apply_leash(self, pos: QPointF) -> QPointF:
        if not self.settings.leash or self.leash_anchor.isNull():
            return pos
        center = QPointF(pos.x() + self.pet.width() / 2, pos.y() + self.pet.height() * 0.65)
        delta = center - self.leash_anchor
        distance = math.hypot(delta.x(), delta.y())
        if distance <= self.leash_radius or distance == 0:
            return pos
        scale = self.leash_radius / distance
        limited = self.leash_anchor + delta * scale
        self.velocity *= -0.25
        return QPointF(limited.x() - self.pet.width() / 2, limited.y() - self.pet.height() * 0.65)

    def _toggle_walk(self, enabled: bool) -> None:
        self.settings.free_walk = bool(enabled)
        if not enabled and self.mode == "walk":
            self._return_idle(keep_position=True)
        self._save_settings()

    def _toggle_topmost(self, enabled: bool) -> None:
        self.settings.always_on_top = bool(enabled)
        self.pet.set_topmost(enabled)
        self.bubble.set_topmost(enabled)
        self.tether.set_topmost(enabled)
        if self.chat and self.chat.isVisible():
            self.chat.raise_()
        self._save_settings()

    def _toggle_autostart(self, enabled: bool) -> None:
        ok, error = set_autostart(enabled)
        if not ok:
            QMessageBox.warning(self.pet, "开机启动", f"设置失败：{error}")
            return
        self.settings.autostart = bool(enabled)
        self._save_settings()

    def say(self, text: str) -> None:
        if self.vision_in_flight:
            return
        if self.chat and self.chat.isVisible():
            self.chat.raise_()
            return
        self.bubble.show_message(cleaned_reply(text), self.pet.geometry())

    def _maybe_ai_event(self, event: str) -> None:
        now = time.monotonic()
        if not (self.settings.text_ai_enabled and self.settings.text_api_key and random.random() < 0.32):
            return
        if now - self.last_ai_event < 24:
            return
        self.last_ai_event = now
        self.ai.submit(
            "event",
            base_url=self.settings.text_base_url,
            api_key=self.settings.text_api_key,
            model=self.settings.text_model,
            messages=[{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": event_prompt(event)}],
            max_tokens=512,
            temperature=1.05,
            reasoning_effort=recommended_reasoning_effort(self.settings.text_base_url, self.settings.text_model),
            thinking=recommended_thinking(self.settings.text_base_url, self.settings.text_model),
        )

    def open_chat(self) -> None:
        self._touch()
        self.bubble.hide()
        if self.chat is None:
            self.chat = MiniChatDialog()
            self.chat.send_requested.connect(self._send_chat)
            self.chat.set_topmost(True)
        online = bool(self.settings.text_ai_enabled and self.settings.text_api_key)
        provider = self.settings.text_model if online else "本地活人台词"
        self.chat.set_connection_status(online, provider)
        self.chat.show_near(self.pet.geometry())

    def _send_chat(self, message: str) -> None:
        self.chat_history.append({"role": "user", "content": message})
        self.chat_history = self.chat_history[-12:]
        if not (self.settings.text_ai_enabled and self.settings.text_api_key):
            reply = local_chat_reply(message)
            self.chat_history.append({"role": "assistant", "content": reply})
            QTimer.singleShot(260, lambda: self._deliver_chat(reply))
            return
        self.ai.submit(
            "chat",
            base_url=self.settings.text_base_url,
            api_key=self.settings.text_api_key,
            model=self.settings.text_model,
            messages=[{"role": "system", "content": SYSTEM_PROMPT}, *self.chat_history],
            max_tokens=1024,
            temperature=0.9,
            reasoning_effort=recommended_reasoning_effort(self.settings.text_base_url, self.settings.text_model),
            thinking=recommended_thinking(self.settings.text_base_url, self.settings.text_model),
        )

    def _deliver_chat(self, reply: str) -> None:
        if self.chat:
            self.chat.append_message("安洁莉娜", reply)
            self.chat.set_busy(False)
            if self.chat.isVisible():
                return
        self.say(reply)

    def open_settings(self) -> None:
        dialog = SettingsDialog(self.settings, self.pet)
        if dialog.exec() != SettingsDialog.Accepted:
            return
        old_keyboard = self.settings.keyboard_reaction
        self.settings = dialog.value
        self.store.save(self.settings)
        if self.chat:
            online = bool(self.settings.text_ai_enabled and self.settings.text_api_key)
            self.chat.set_connection_status(online, self.settings.text_model if online else "本地活人台词")
        if old_keyboard != self.settings.keyboard_reaction:
            if self.settings.keyboard_reaction:
                self.keyboard.start()
            else:
                self.keyboard.stop()
        self._configure_periodic_vision()
        self.say("设置收到了。我会照博士选的方式陪着你。")

    def analyze_screen(self) -> None:
        self._touch()
        if not (self.settings.vision_enabled and self.settings.vision_api_key):
            QMessageBox.information(self.pet, "屏幕理解", "请先在“AI 与隐私设置”里启用屏幕理解并填写独立的视觉模型与 Key。")
            self.open_settings()
            return
        base = self.settings.vision_base_url.lower()
        model = self.settings.vision_model.lower()
        known_text_only = model in {"step-3.5-flash", "step-3.5-flash-2603", "step-router-v1"}
        if "step_plan" in base and known_text_only:
            QMessageBox.information(
                self.pet,
                "当前 Step Plan 暂无视觉输入",
                "你当前套餐列出的模型是文本/语音/图片生成模型，不包含视觉理解模型；"
                "step-router-v1 官方也明确不接受图片消息。以后套餐加入视觉模型后，只要在设置里改模型名即可使用。",
            )
            return
        answer = QMessageBox.question(
            self.pet,
            "发送一次屏幕截图？",
            "将截取桌宠所在的整块屏幕，缩小后发送给你配置的视觉模型。截图不保存到磁盘，也不会自动重复。是否继续？",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if answer != QMessageBox.Yes:
            return
        self.say(line("vision"))
        self._begin_screen_capture("vision-manual")

    def _configure_periodic_vision(self) -> None:
        self.periodic_vision_timer.stop()
        if not self.settings.vision_periodic_enabled:
            return
        if not (self.settings.vision_enabled and self.settings.vision_api_key):
            return
        base = self.settings.vision_base_url.lower()
        model = self.settings.vision_model.lower()
        if "step_plan" in base and model in {"step-3.5-flash", "step-3.5-flash-2603", "step-router-v1"}:
            return
        interval_ms = max(5, min(240, self.settings.vision_interval_minutes)) * 60_000
        self.periodic_vision_timer.start(interval_ms)

    def _periodic_screen_check(self) -> None:
        if self.vision_in_flight or self.mode == "drag" or self.destination_picker.isVisible():
            return
        if not (self.settings.vision_periodic_enabled and self.settings.vision_enabled and self.settings.vision_api_key):
            self._configure_periodic_vision()
            return
        self._begin_screen_capture("vision-periodic")

    def _begin_screen_capture(self, request_id: str) -> None:
        if self.vision_in_flight:
            return
        self.vision_in_flight = True
        self._pending_vision_request_id = request_id
        self._pending_vision_screen = QApplication.screenAt(self.pet.geometry().center()) or QApplication.primaryScreen()
        self._vision_chat_was_visible = bool(self.chat and self.chat.isVisible())
        self.pet.hide()
        self.bubble.hide()
        self.tether.hide()
        if self.chat:
            self.chat.hide()
        QTimer.singleShot(220, self._capture_and_send_screen)

    def _restore_after_screen_capture(self) -> None:
        self.pet.show()
        self.pet.raise_()
        self._update_tether()
        if self._vision_chat_was_visible and self.chat:
            self.chat.show_near(self.pet.geometry(), activate=False)
        self._vision_chat_was_visible = False

    def _capture_and_send_screen(self) -> None:
        screen = self._pending_vision_screen or QApplication.primaryScreen()
        request_id = self._pending_vision_request_id or "vision-manual"
        self._pending_vision_screen = None
        self._pending_vision_request_id = None
        try:
            if screen is None:
                raise RuntimeError("找不到可截图的屏幕")
            pixmap = screen.grabWindow(0)
            if pixmap.isNull():
                raise RuntimeError("Windows 没有返回屏幕图像")
            if pixmap.width() > 1600:
                pixmap = pixmap.scaledToWidth(1600, Qt.SmoothTransformation)
            data = QByteArray()
            buffer = QBuffer(data)
            if not buffer.open(QIODevice.WriteOnly):
                raise RuntimeError("无法创建内存截图缓冲区")
            saved = pixmap.save(buffer, "JPEG", 72)
            buffer.close()
            if not saved or data.isEmpty():
                raise RuntimeError("屏幕截图压缩失败")
            encoded = base64.b64encode(bytes(data)).decode("ascii")
        except Exception as exc:
            self.vision_in_flight = False
            self._restore_after_screen_capture()
            if request_id == "vision-manual":
                QMessageBox.warning(self.pet, "屏幕理解失败", str(exc))
            else:
                self.say("刚才没看清屏幕……下次我再轻轻看一眼。")
            return
        self._restore_after_screen_capture()
        content = [
            {"type": "text", "text": vision_prompt()},
            {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{encoded}", "detail": "low"}},
        ]
        self.ai.submit(
            request_id,
            base_url=self.settings.vision_base_url,
            api_key=self.settings.vision_api_key,
            model=self.settings.vision_model,
            messages=[{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": content}],
            max_tokens=1024,
            temperature=0.8,
            reasoning_effort=recommended_reasoning_effort(self.settings.vision_base_url, self.settings.vision_model),
            thinking=recommended_thinking(self.settings.vision_base_url, self.settings.vision_model),
        )

    def _on_ai_completed(self, request_id: str, text: str) -> None:
        reply = cleaned_reply(text)
        if request_id == "chat":
            self.chat_history.append({"role": "assistant", "content": reply})
            self.chat_history = self.chat_history[-12:]
            self._deliver_chat(reply)
            if self.chat:
                self.chat.set_connection_status(True, self.settings.text_model, verified=True)
        elif request_id.startswith("vision-") or request_id == "vision":
            self.vision_in_flight = False
            self.say(reply)
        else:
            self.say(reply)

    def _on_ai_failed(self, request_id: str, error: str) -> None:
        if request_id == "chat" and self.chat:
            fallback = "这次消息没送到网络那边……先让我在本地陪你吧。"
            self.chat_history.append({"role": "assistant", "content": fallback})
            self.chat_history = self.chat_history[-12:]
            self.chat.append_message("安洁莉娜", fallback)
            self.chat.append_message("系统", error[:240])
            self.chat.set_connection_error(error)
            self.chat.set_busy(False)
        elif request_id.startswith("vision-") or request_id == "vision":
            self.vision_in_flight = False
            if request_id in {"vision-manual", "vision"}:
                QMessageBox.warning(self.pet, "屏幕理解失败", error[:500])
            else:
                self.say("这次没能看清桌面，我会安静等下一次，不打扰博士。")
        else:
            self.say(line("error"))

    def _available_geometry(self, point: QPoint) -> QRect:
        screen = QApplication.screenAt(point + QPoint(self.pet.width() // 2, self.pet.height() // 2))
        return (screen or QApplication.primaryScreen()).availableGeometry()

    def _keep_on_screen(self) -> None:
        area = self._available_geometry(self.pet.pos())
        x = max(area.left(), min(area.right() - self.pet.width() + 1, self.pet.x()))
        y = max(area.top(), min(area.bottom() - self.pet.height() + 1, self.pet.y()))
        self.pet.move(x, y)

    def _touch(self) -> None:
        self.last_touch = time.monotonic()
        self.next_nudge = self.last_touch + random.uniform(150, 300)

    def _save_settings(self) -> None:
        self.settings.x = self.pet.x()
        self.settings.y = self.pet.y()
        self.store.save(self.settings)

    def quit(self) -> None:
        self._save_settings()
        self.tick_timer.stop()
        self.periodic_vision_timer.stop()
        self.keyboard.stop()
        self.ai.shutdown()
        self.tray.hide()
        self.destination_picker.close()
        if self.chat:
            self.chat.close()
        self.bubble.close()
        self.tether.close()
        self.pet.close()
        self.app.quit()
