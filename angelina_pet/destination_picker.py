from __future__ import annotations

from PySide6.QtCore import QPoint, QPointF, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QCursor, QFont, QKeyEvent, QMouseEvent, QPainter, QPen
from PySide6.QtWidgets import QApplication, QWidget


class DestinationPicker(QWidget):
    """Short-lived, desktop-sized overlay used to choose a global position."""

    selected = Signal(QPoint)
    cancelled = Signal()

    def __init__(self, topmost: bool = True) -> None:
        super().__init__(None)
        self._active = False
        self._cursor_pos = QPoint()
        self._hint_center = QPoint()
        self._hint_text = "点击桌面选择目的地  ·  Esc 取消"

        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_NoSystemBackground)
        self.setWindowFlag(Qt.FramelessWindowHint, True)
        self.setWindowFlag(Qt.Tool, True)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setMouseTracking(True)
        self.setCursor(Qt.CrossCursor)
        self.set_topmost(topmost)

    def set_topmost(self, enabled: bool) -> None:
        """Change the picker window's topmost state, preserving visibility."""

        visible = self.isVisible()
        self.setWindowFlag(Qt.WindowStaysOnTopHint, bool(enabled))
        if visible:
            self.show()
            self.raise_()

    def show_picker(self, anchor_point: QPoint | None = None, hint_text: str | None = None) -> None:
        """Cover the virtual desktop and begin selecting a destination.

        ``anchor_point`` is a global coordinate used as the initial reticle
        position. When omitted, the current global mouse position is used.
        """

        primary = QApplication.primaryScreen()
        if primary is None:
            return

        virtual = primary.virtualGeometry()
        global_anchor = QPoint(anchor_point) if anchor_point is not None else QCursor.pos()
        self._hint_text = (hint_text or "点击桌面选择目的地  ·  Esc 取消").strip()
        screen = QApplication.screenAt(global_anchor) or primary
        screen_geometry = screen.availableGeometry()

        self.setGeometry(virtual)
        self._cursor_pos = global_anchor - virtual.topLeft()
        self._hint_center = QPoint(
            screen_geometry.center().x() - virtual.left(),
            screen_geometry.top() - virtual.top() + 52,
        )
        self._active = True
        self.show()
        self.raise_()
        self.activateWindow()
        self.setFocus(Qt.ActiveWindowFocusReason)
        self.update()

        # Windows can defer activation of a freshly shown Tool window until
        # the next event-loop pass. Requesting focus once more keeps Esc
        # cancellation reliable without grabbing the user's keyboard.
        QTimer.singleShot(0, self._request_focus)

    def _request_focus(self) -> None:
        if not self._active or not self.isVisible():
            return
        self.activateWindow()
        self.setFocus(Qt.ActiveWindowFocusReason)

    def _select(self, global_point: QPoint) -> None:
        if not self._active:
            return
        self._active = False
        self.hide()
        self.selected.emit(QPoint(global_point))

    def _cancel(self) -> None:
        if not self._active:
            return
        self._active = False
        self.hide()
        self.cancelled.emit()

    def mouseMoveEvent(self, event: QMouseEvent) -> None:  # noqa: N802 - Qt API
        self._cursor_pos = event.position().toPoint()
        self.update()
        event.accept()

    def mousePressEvent(self, event: QMouseEvent) -> None:  # noqa: N802 - Qt API
        if event.button() == Qt.LeftButton:
            self._select(event.globalPosition().toPoint())
            event.accept()
            return
        if event.button() == Qt.RightButton:
            self._cancel()
            event.accept()
            return
        super().mousePressEvent(event)

    def keyPressEvent(self, event: QKeyEvent) -> None:  # noqa: N802 - Qt API
        if event.key() == Qt.Key_Escape:
            self._cancel()
            event.accept()
            return
        super().keyPressEvent(event)

    def focusOutEvent(self, event) -> None:  # noqa: N802 - Qt API
        super().focusOutEvent(event)
        # If another application takes focus (for example through Alt+Tab),
        # dismiss this full-desktop overlay so it can never strand the user.
        if self._active and self.isVisible():
            QTimer.singleShot(0, self._cancel_if_inactive)

    def _cancel_if_inactive(self) -> None:
        if self._active and self.isVisible() and not self.isActiveWindow():
            self._cancel()

    def paintEvent(self, event) -> None:  # noqa: N802 - Qt API
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        # A very light blue veil makes the selection mode legible while the
        # desktop remains fully visible underneath it.
        painter.fillRect(self.rect(), QColor(31, 111, 190, 22))

        hint_width = 300.0
        hint_height = 42.0
        hint = QRectF(
            self._hint_center.x() - hint_width / 2,
            self._hint_center.y() - hint_height / 2,
            hint_width,
            hint_height,
        )
        painter.setPen(QPen(QColor(116, 74, 86, 215), 1.6))
        painter.setBrush(QColor(255, 248, 238, 235))
        painter.drawRoundedRect(hint, hint_height / 2, hint_height / 2)
        font = QFont("Microsoft YaHei UI", 10)
        font.setBold(True)
        painter.setFont(font)
        painter.setPen(QColor(91, 68, 79, 245))
        painter.drawText(hint, Qt.AlignCenter, self._hint_text)

        center = QPointF(self._cursor_pos)
        painter.setBrush(Qt.NoBrush)
        painter.setPen(QPen(QColor(255, 248, 238, 245), 5.0))
        painter.drawEllipse(center, 22.0, 22.0)
        painter.setPen(QPen(QColor(217, 111, 92, 250), 2.2))
        painter.drawEllipse(center, 22.0, 22.0)
        painter.setPen(QPen(QColor(31, 111, 190, 245), 2.0))
        painter.drawEllipse(center, 8.0, 8.0)

        arm_inner = 27.0
        arm_outer = 38.0
        painter.setPen(QPen(QColor(116, 74, 86, 235), 2.0, Qt.SolidLine, Qt.RoundCap))
        painter.drawLine(QPointF(center.x() - arm_outer, center.y()), QPointF(center.x() - arm_inner, center.y()))
        painter.drawLine(QPointF(center.x() + arm_inner, center.y()), QPointF(center.x() + arm_outer, center.y()))
        painter.drawLine(QPointF(center.x(), center.y() - arm_outer), QPointF(center.x(), center.y() - arm_inner))
        painter.drawLine(QPointF(center.x(), center.y() + arm_inner), QPointF(center.x(), center.y() + arm_outer))
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(255, 174, 66, 255))
        painter.drawEllipse(center, 3.2, 3.2)
