from __future__ import annotations

import math
import time

from PySide6.QtCore import QPoint, QPointF, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QContextMenuEvent, QFont, QMouseEvent, QPainter, QPen, QWheelEvent
from PySide6.QtWidgets import QWidget

from .assets import AssetStore, Clip
from .constants import DEFAULT_HEIGHT, MAX_HEIGHT, MIN_HEIGHT


class PetWindow(QWidget):
    clicked = Signal()
    drag_started = Signal()
    dragged = Signal(QPoint)
    drag_released = Signal(float, float)
    context_requested = Signal(QPoint)
    height_requested = Signal(int)
    geometry_changed = Signal()

    def __init__(self, assets: AssetStore, height: int = DEFAULT_HEIGHT, topmost: bool = True) -> None:
        super().__init__(None)
        self.assets = assets
        self.pet_height = max(MIN_HEIGHT, min(MAX_HEIGHT, height))
        self.scene_name = ""
        self.clip: Clip | None = None
        self.frame_index = 0
        self.effect_scale_x = 1.0
        self.effect_scale_y = 1.0
        self.effect_rotation = 0.0
        self.mirrored = False
        self.office_key = ""
        self.office_key_started = 0.0
        self.office_key_until = 0.0
        self.office_key_duration = 0.52
        self.office_key_side = -1.0
        self.office_mouse_started = 0.0
        self.office_mouse_until = 0.0
        self.office_mouse_duration = 0.48
        self.office_spark_started = 0.0
        self.office_spark_until = 0.0
        self.office_spark_side = -1.0
        self.office_scene_started = 0.0
        self._press_global = QPoint()
        self._window_at_press = QPoint()
        self._drag_samples: list[tuple[float, QPoint]] = []
        self._dragging = False
        self._frame_timer = QTimer(self)
        self._frame_timer.setSingleShot(True)
        self._frame_timer.timeout.connect(self._advance_frame)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_NoSystemBackground)
        self.setMouseTracking(True)
        self.setWindowFlag(Qt.FramelessWindowHint, True)
        self.setWindowFlag(Qt.Tool, True)
        self.set_topmost(topmost)

    def set_topmost(self, enabled: bool) -> None:
        visible = self.isVisible()
        self.setWindowFlag(Qt.WindowStaysOnTopHint, enabled)
        if visible:
            self.show()
            self.raise_()

    def set_scene(self, name: str, animated: bool = True) -> None:
        if self.scene_name == name and self.clip is not None:
            desired = self.assets.clip(name, animated)
            if desired is self.clip:
                return
        old_bottom_center = QPoint(self.x() + self.width() // 2, self.y() + self.height())
        self.scene_name = name
        if name == "办公":
            self.office_scene_started = time.monotonic()
            self.office_key = ""
            self.office_key_started = 0.0
            self.office_key_until = 0.0
            self.office_mouse_started = 0.0
            self.office_mouse_until = 0.0
            self.office_spark_started = 0.0
            self.office_spark_until = 0.0
            self.office_spark_side = -1.0
        self.clip = self.assets.clip(name, animated)
        self.frame_index = 0
        self._resize_for_clip(old_bottom_center)
        self._schedule_frame()
        self.update()

    def set_pet_height(self, value: int) -> None:
        value = max(MIN_HEIGHT, min(MAX_HEIGHT, int(value)))
        if value == self.pet_height:
            return
        bottom_center = QPoint(self.x() + self.width() // 2, self.y() + self.height())
        self.pet_height = value
        self._resize_for_clip(bottom_center)
        self.height_requested.emit(value)

    def set_effect(self, scale_x: float = 1.0, scale_y: float = 1.0, rotation: float = 0.0) -> None:
        self.effect_scale_x = scale_x
        self.effect_scale_y = scale_y
        self.effect_rotation = rotation
        self.update()

    def set_mirrored(self, enabled: bool) -> None:
        enabled = bool(enabled)
        if self.mirrored == enabled:
            return
        self.mirrored = enabled
        self.update()

    def flash_key(self, label: str, duration: float = 0.52) -> None:
        now = time.monotonic()
        self.office_key = label[:10]
        self.office_key_started = now
        self.office_key_duration = max(0.12, duration)
        self.office_key_until = now + self.office_key_duration
        self.office_key_side = self._office_key_side(label)
        self._trigger_office_spark(now, self.office_key_side)
        self.update()

    def flash_mouse(self, duration: float = 0.48) -> None:
        now = time.monotonic()
        self.office_mouse_started = now
        self.office_mouse_duration = max(0.12, duration)
        self.office_mouse_until = now + self.office_mouse_duration
        self._trigger_office_spark(now, 1.0)
        self.update()

    def _trigger_office_spark(self, now: float, side: float) -> None:
        # A fresh burst pops in quickly. Repeated input extends the same burst
        # instead of restarting its phase, so fast typing looks continuous.
        if now >= self.office_spark_until:
            self.office_spark_started = now
        self.office_spark_until = now + 1.05
        self.office_spark_side = -1.0 if side < 0.0 else 1.0

    @staticmethod
    def _office_key_side(label: str) -> float:
        """Return the hand side suggested by a key, for a tiny weight shift."""
        key = label.upper()
        if key and key[0] in "QWERTASDFGZXCVB":
            return -1.0
        return 1.0

    @staticmethod
    def _office_bounce(now: float, started: float, duration: float) -> float:
        if started <= 0.0 or duration <= 0.0:
            return 0.0
        progress = (now - started) / duration
        if progress < 0.0 or progress >= 1.0:
            return 0.0
        # One soft impulse per input. This deliberately does not oscillate,
        # which avoids the old continuous, mechanical-looking vibration.
        return math.sin(progress * math.pi) * (1.0 - progress * 0.18)

    def office_motion_state(self, now: float | None = None) -> dict[str, float]:
        """Expose the procedural office pose in a compact, testable form."""
        now = time.monotonic() if now is None else now
        elapsed = max(0.0, now - self.office_scene_started)
        key_bounce = self._office_bounce(
            now, self.office_key_started, self.office_key_duration
        )
        mouse_bounce = self._office_bounce(
            now, self.office_mouse_started, self.office_mouse_duration
        )
        if key_bounce >= mouse_bounce:
            bounce = key_bounce
            input_side = self.office_key_side
        else:
            bounce = mouse_bounce
            input_side = 1.0

        # Natural idle motion is intentionally asynchronous and tiny. The
        # desk reads as planted while Angelina's weight subtly wanders.
        idle_weight = max(0.0, 1.0 - bounce * 1.7)
        shift_x = math.sin(elapsed * 0.57) * 0.0015 * idle_weight
        shift_y = math.sin(elapsed * 1.31 + 0.35) * 0.0022 * idle_weight
        rotation = math.sin(elapsed * 0.43 + 0.8) * 0.10 * idle_weight

        # A short Q-like response, biased toward the hand/mouse that acted.
        shift_x += input_side * bounce * 0.0038
        shift_y -= bounce * 0.0072
        rotation += input_side * bounce * 0.34

        # Input feedback is kept separate from the low-frequency skit so its
        # visibility can be asserted independently and consecutive input can
        # naturally hold it on screen.
        input_spark = 0.0
        if self.office_spark_started > 0.0 and now < self.office_spark_until:
            spark_age = max(0.0, now - self.office_spark_started)
            spark_remaining = max(0.0, self.office_spark_until - now)
            fade_in = min(1.0, spark_age / 0.055)
            fade_out = min(1.0, spark_remaining / 0.28)
            input_spark = fade_in * fade_out

        # Low-frequency micro skits now use a shorter cycle so the ambient
        # sparkle is discoverable even when the user is not typing.
        skit_phase = elapsed % 14.0
        long_skit_phase = elapsed % 19.0
        celebration = 0.0
        if 5.0 <= skit_phase < 7.2:
            celebration = math.sin((skit_phase - 5.0) / 2.2 * math.pi)
        if 11.4 <= long_skit_phase < 13.2:
            celebration = max(
                celebration,
                math.sin((long_skit_phase - 11.4) / 1.8 * math.pi),
            )
        stretch = 0.0
        if 10.3 <= skit_phase < 12.0:
            stretch = math.sin((skit_phase - 10.3) / 1.7 * math.pi)
        if 16.0 <= long_skit_phase < 17.7:
            stretch = max(
                stretch,
                math.sin((long_skit_phase - 16.0) / 1.7 * math.pi),
            )
        if stretch > 0.0:
            shift_y -= stretch * 0.0016
            rotation -= stretch * 0.08

        blink = 0.0
        if bounce < 0.08:
            blink_phase = elapsed % 6.7
            if 4.86 <= blink_phase < 5.10:
                blink = math.sin((blink_phase - 4.86) / 0.24 * math.pi)
            # An occasional double blink keeps the timing from feeling like a
            # metronome without introducing random, hard-to-test painting.
            cycle_index = int(elapsed / 6.7)
            if cycle_index % 4 == 3 and 5.24 <= blink_phase < 5.42:
                blink = max(
                    blink,
                    math.sin((blink_phase - 5.24) / 0.18 * math.pi),
                )
        return {
            "shift_x": shift_x,
            "shift_y": shift_y,
            "rotation": rotation,
            "bounce": bounce,
            "blink": blink,
            "celebration": celebration,
            "input_spark": input_spark,
            "input_spark_side": self.office_spark_side,
            "spark_twinkle": 0.88 + math.sin(elapsed * 10.5) * 0.12,
            "stretch": stretch,
        }

    def current_pixmap(self):
        if not self.clip or not self.clip.frames:
            return None
        return self.clip.frames[self.frame_index % len(self.clip.frames)]

    def _resize_for_clip(self, bottom_center: QPoint) -> None:
        if not self.clip:
            return
        padding = max(8, round(self.pet_height * 0.055))
        content_height = max(60, self.pet_height - padding * 2)
        content_width = max(80, round(content_height * self.clip.aspect_ratio))
        self.resize(content_width + padding * 2, self.pet_height)
        if bottom_center.x() or bottom_center.y():
            self.move(bottom_center.x() - self.width() // 2, bottom_center.y() - self.height())
        self.geometry_changed.emit()

    def _schedule_frame(self) -> None:
        self._frame_timer.stop()
        if self.clip and len(self.clip.frames) > 1:
            delay = self.clip.durations[self.frame_index % len(self.clip.durations)]
            self._frame_timer.start(max(40, delay))

    def _advance_frame(self) -> None:
        if not self.clip:
            return
        self.frame_index = (self.frame_index + 1) % len(self.clip.frames)
        self.update()
        self._schedule_frame()

    def _content_rect(self) -> QRectF:
        padding = max(8, round(self.pet_height * 0.055))
        return QRectF(padding, padding, self.width() - padding * 2, self.height() - padding * 2)

    def paintEvent(self, event) -> None:  # noqa: N802 - Qt API
        pixmap = self.current_pixmap()
        if pixmap is None:
            return
        painter = QPainter(self)
        painter.setCompositionMode(QPainter.CompositionMode_Source)
        painter.fillRect(self.rect(), QColor(0, 0, 0, 0))
        painter.setCompositionMode(QPainter.CompositionMode_SourceOver)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setRenderHint(QPainter.SmoothPixmapTransform)
        rect = self._content_rect()
        center = rect.center()
        now = time.monotonic()
        office_state: dict[str, float] | None = None
        motion_x = 0.0
        motion_y = 0.0
        motion_rotation = 0.0
        if self.scene_name == "办公":
            office_state = self.office_motion_state(now)
            motion_x = office_state["shift_x"] * rect.width()
            motion_y = office_state["shift_y"] * rect.height()
            motion_rotation = office_state["rotation"]
        painter.translate(center.x() + motion_x, center.y() + motion_y)
        painter.rotate(self.effect_rotation + motion_rotation)
        sx = -self.effect_scale_x if self.mirrored else self.effect_scale_x
        painter.scale(sx, self.effect_scale_y)
        painter.translate(-center)
        painter.drawPixmap(rect, pixmap, QRectF(pixmap.rect()))
        painter.resetTransform()
        if office_state is not None:
            # Controls and local decoration use the identical transform so a
            # highlighted key remains glued to the illustrated keyboard.
            painter.translate(center.x() + motion_x, center.y() + motion_y)
            painter.rotate(self.effect_rotation + motion_rotation)
            painter.scale(sx, self.effect_scale_y)
            painter.translate(-center)
            self._draw_office_controls(painter, rect, now)
            self._draw_office_blink(painter, rect, office_state["blink"])
            self._draw_office_ambient(painter, rect, office_state)
            painter.resetTransform()

    def _draw_office_blink(self, painter: QPainter, rect: QRectF, amount: float) -> None:
        if amount < 0.22:
            return
        painter.save()
        painter.setRenderHint(QPainter.Antialiasing)
        # The processed office illustration has a slightly taller-than-wide
        # source canvas, hence these positions intentionally are not centred
        # around 0.5/0.5.
        eye_width = rect.width() * 0.066
        eye_height = rect.height() * 0.069
        eye_y = rect.top() + rect.height() * 0.282
        lid_height = eye_height * min(1.0, amount)
        skin = QColor(255, 250, 245, round(255 * min(1.0, amount * 1.25)))
        line = QColor(102, 62, 61, round(230 * min(1.0, amount * 1.25)))
        for center_x in (0.486, 0.610):
            eye = QRectF(
                rect.left() + rect.width() * center_x - eye_width / 2,
                eye_y - lid_height / 2,
                eye_width,
                lid_height,
            )
            painter.setPen(Qt.NoPen)
            painter.setBrush(skin)
            painter.drawRoundedRect(eye, eye_width / 2, lid_height / 2)
            arc = QRectF(
                eye.left(),
                eye.center().y() - eye_height * 0.12,
                eye.width(),
                eye_height * 0.42,
            )
            painter.setPen(QPen(line, max(1.0, rect.height() * 0.0042)))
            painter.setBrush(Qt.NoBrush)
            painter.drawArc(arc, 20 * 16, 140 * 16)
        painter.restore()

    def _draw_office_ambient(
        self, painter: QPainter, rect: QRectF, state: dict[str, float]
    ) -> None:
        celebration = state["celebration"]
        input_spark = state["input_spark"]
        stretch = state["stretch"]
        sparkle = max(celebration, input_spark)
        if sparkle <= 0.03 and stretch <= 0.03:
            return
        painter.save()
        painter.setRenderHint(QPainter.Antialiasing)
        if sparkle > 0.03:
            # Keep the cluster in the clear air above the monitor/left curl:
            # it never covers the face, keyboard or key-name capsule. The
            # right-hand input variant shifts upward rather than onto the
            # character's large right ponytail.
            is_input = input_spark >= celebration
            side = state["input_spark_side"] if is_input else -1.0
            base_x = 0.125 if side < 0.0 else 0.185
            base_y = 0.225 if side < 0.0 else 0.165
            alpha = round((250 if is_input else 235) * sparkle)
            twinkle = state["spark_twinkle"]
            points = (
                (base_x, base_y, 0.037),
                (base_x + 0.070, base_y + 0.058, 0.027),
                (base_x - 0.032, base_y + 0.105, 0.022),
            )
            for x, y, radius in points:
                center = QPointF(
                    rect.left() + rect.width() * x,
                    rect.top() + rect.height() * y,
                )
                size = max(
                    5.0,
                    rect.height() * radius * (0.82 + sparkle * 0.18) * twinkle,
                )
                painter.setPen(
                    QPen(
                        QColor(218, 119, 80, alpha),
                        max(1.6, rect.height() * 0.006),
                        Qt.SolidLine,
                        Qt.RoundCap,
                    )
                )
                painter.drawLine(
                    QPointF(center.x() - size, center.y()),
                    QPointF(center.x() + size, center.y()),
                )
                painter.drawLine(
                    QPointF(center.x(), center.y() - size),
                    QPointF(center.x(), center.y() + size),
                )
                # Diagonal rays make the response read as a star rather than
                # a plus sign, especially at the 300px minimum use case.
                diagonal = size * 0.54
                painter.setPen(
                    QPen(
                        QColor(255, 202, 91, round(alpha * 0.92)),
                        max(1.25, rect.height() * 0.0045),
                        Qt.SolidLine,
                        Qt.RoundCap,
                    )
                )
                painter.drawLine(
                    QPointF(center.x() - diagonal, center.y() - diagonal),
                    QPointF(center.x() + diagonal, center.y() + diagonal),
                )
                painter.drawLine(
                    QPointF(center.x() + diagonal, center.y() - diagonal),
                    QPointF(center.x() - diagonal, center.y() + diagonal),
                )
                painter.setBrush(QColor(255, 239, 164, alpha))
                painter.setPen(Qt.NoPen)
                painter.drawEllipse(center, max(1.7, size * 0.30), max(1.7, size * 0.30))
        if stretch > 0.03:
            alpha = round(175 * stretch)
            painter.setBrush(Qt.NoBrush)
            painter.setPen(
                QPen(
                    QColor(31, 111, 190, alpha),
                    max(1.0, rect.height() * 0.004),
                    Qt.SolidLine,
                    Qt.RoundCap,
                )
            )
            for index in range(3):
                arc = QRectF(
                    rect.left() + rect.width() * (0.665 + index * 0.032),
                    rect.top() + rect.height() * (0.115 - index * 0.010),
                    rect.width() * 0.070,
                    rect.height() * 0.046,
                )
                painter.drawArc(arc, 22 * 16, 118 * 16)
        painter.restore()

    def _draw_office_controls(self, painter: QPainter, rect: QRectF, now: float) -> None:
        # Coordinates match the mini keyboard and cat-paw mouse in office-v2.
        keyboard = QRectF(
            rect.left() + rect.width() * 0.280,
            rect.top() + rect.height() * 0.560,
            rect.width() * 0.205,
            rect.height() * 0.120,
        )
        mouse = QRectF(
            rect.left() + rect.width() * 0.525,
            rect.top() + rect.height() * 0.595,
            rect.width() * 0.130,
            rect.height() * 0.130,
        )
        painter.save()
        painter.setOpacity(1.0)
        active = self.office_key.upper() if now < self.office_key_until else ""
        painter.setRenderHint(QPainter.Antialiasing)
        if active:
            label = {
                "BACKSPACE": "Bksp",
                "ENTER": "Enter",
                "SHIFT": "Shift",
                "SPACE": "Space",
            }.get(active, active if len(active) <= 3 else active[:3])
            tag_height = max(14.0, rect.height() * 0.048)
            tag_width = max(38.0, len(label) * tag_height * 0.60 + 16.0)
            if len(label) > 1:
                tag_width = max(48.0, tag_width)
            tag = QRectF(
                keyboard.center().x() - tag_width / 2,
                keyboard.bottom() + 3.0,
                tag_width,
                tag_height,
            )
            painter.setPen(QPen(QColor(255, 248, 238, 230), 1))
            painter.setBrush(QColor(31, 111, 190, 225))
            painter.drawRoundedRect(tag, tag.height() / 2, tag.height() / 2)
            painter.setPen(QColor(255, 255, 255))
            font = QFont("Microsoft YaHei UI")
            font.setPixelSize(max(8, round(tag_height * 0.52)))
            font.setBold(True)
            painter.setFont(font)
            painter.drawText(tag, Qt.AlignCenter, label)

        if now < self.office_mouse_until:
            click = QRectF(mouse.left(), mouse.top(), mouse.width() * 0.52, mouse.height() * 0.48)
            painter.setPen(QPen(QColor(255, 248, 220, 245), max(1.0, rect.height() * 0.003)))
            painter.setBrush(QColor(255, 174, 66, 175))
            painter.drawRoundedRect(click.translated(0, rect.height() * 0.006), 5, 5)
            phase = max(0.0, min(1.0, (self.office_mouse_until - now) / 0.48))
            ring = mouse.adjusted(-mouse.width() * (1.0 - phase), -mouse.height() * (1.0 - phase), mouse.width() * (1.0 - phase), mouse.height() * (1.0 - phase))
            painter.setPen(QPen(QColor(31, 111, 190, round(220 * phase)), max(1.0, rect.height() * 0.004)))
            painter.setBrush(Qt.NoBrush)
            painter.drawEllipse(ring)
        painter.restore()

    def mousePressEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if event.button() == Qt.LeftButton:
            self._press_global = event.globalPosition().toPoint()
            self._window_at_press = self.pos()
            self._dragging = False
            self._drag_samples = [(time.monotonic(), self._press_global)]
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if event.buttons() & Qt.LeftButton:
            current = event.globalPosition().toPoint()
            delta = current - self._press_global
            if not self._dragging and delta.manhattanLength() >= 5:
                self._dragging = True
                self.drag_started.emit()
            if self._dragging:
                target = self._window_at_press + delta
                self.move(target)
                now = time.monotonic()
                self._drag_samples.append((now, current))
                self._drag_samples = [(t, p) for t, p in self._drag_samples if now - t <= 0.14]
                self.dragged.emit(target)
                self.geometry_changed.emit()
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if event.button() == Qt.LeftButton:
            if self._dragging:
                vx = vy = 0.0
                if len(self._drag_samples) >= 2:
                    first_t, first_p = self._drag_samples[0]
                    last_t, last_p = self._drag_samples[-1]
                    elapsed = max(0.01, last_t - first_t)
                    vx = (last_p.x() - first_p.x()) / elapsed
                    vy = (last_p.y() - first_p.y()) / elapsed
                self.drag_released.emit(vx, vy)
            else:
                self.clicked.emit()
            self._drag_samples.clear()
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def wheelEvent(self, event: QWheelEvent) -> None:  # noqa: N802
        steps = event.angleDelta().y() / 120.0
        if steps:
            factor = math.pow(1.09, steps)
            self.set_pet_height(round(self.pet_height * factor))
            event.accept()

    def contextMenuEvent(self, event: QContextMenuEvent) -> None:  # noqa: N802
        self.context_requested.emit(event.globalPos())
        event.accept()

    def moveEvent(self, event) -> None:  # noqa: N802
        super().moveEvent(event)
        self.geometry_changed.emit()


class TetherOverlay(QWidget):
    def __init__(self, topmost: bool = True) -> None:
        super().__init__(None)
        self.anchor = QPointF()
        self.target = QPointF()
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.setWindowFlag(Qt.FramelessWindowHint, True)
        self.setWindowFlag(Qt.Tool, True)
        self.setWindowFlag(Qt.WindowTransparentForInput, True)
        self.set_topmost(topmost)

    def set_topmost(self, enabled: bool) -> None:
        visible = self.isVisible()
        self.setWindowFlag(Qt.WindowStaysOnTopHint, enabled)
        if visible:
            self.show()

    def update_line(self, anchor: QPointF, target: QPointF) -> None:
        self.anchor = QPointF(anchor)
        self.target = QPointF(target)
        margin = 18
        left = int(min(anchor.x(), target.x())) - margin
        top = int(min(anchor.y(), target.y())) - margin
        right = int(max(anchor.x(), target.x())) + margin
        bottom = int(max(anchor.y(), target.y())) + margin
        self.setGeometry(left, top, max(36, right - left), max(36, bottom - top))
        self.show()
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        a = self.anchor - QPointF(self.x(), self.y())
        b = self.target - QPointF(self.x(), self.y())
        dx, dy = b.x() - a.x(), b.y() - a.y()
        distance = max(1.0, math.hypot(dx, dy))
        count = max(2, int(distance / 10))
        painter.setPen(QPen(QColor(91, 68, 79, 220), 2.1))
        for index in range(count + 1):
            t = index / count
            x = a.x() + dx * t
            y = a.y() + dy * t + math.sin(t * math.pi) * min(22, distance * 0.08)
            painter.drawEllipse(QPointF(x, y), 3.6, 2.4)
        painter.setBrush(QColor(220, 119, 91, 240))
        painter.drawEllipse(a, 7, 7)
