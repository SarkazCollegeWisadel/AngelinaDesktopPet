from __future__ import annotations

from PySide6.QtCore import QPoint, QPointF, QRect, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QFontMetrics, QLinearGradient, QMouseEvent, QPainter, QPainterPath, QPen, QPolygonF
from PySide6.QtWidgets import QApplication, QWidget


class SpeechBubble(QWidget):
    clicked = Signal()

    def __init__(self) -> None:
        super().__init__(None)
        self._text = ""
        self._pet_rect = QRectF()
        self._tail = "bottom"
        self._pressed = False
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self.hide)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setWindowFlag(Qt.FramelessWindowHint, True)
        self.setWindowFlag(Qt.Tool, True)
        self.setWindowFlag(Qt.WindowDoesNotAcceptFocus, True)
        self.setCursor(Qt.PointingHandCursor)
        self.setToolTip("点击和安洁莉娜聊天")
        self.resize(320, 140)

    def set_topmost(self, enabled: bool) -> None:
        visible = self.isVisible()
        self.setWindowFlag(Qt.WindowStaysOnTopHint, enabled)
        if visible:
            self.show()

    def show_message(self, text: str, pet_rect, duration_ms: int | None = None) -> None:
        self._text = " ".join(text.strip().split())[:180]
        self._pet_rect = QRectF(pet_rect)
        font = QFont("Microsoft YaHei UI", 10)
        metrics = QFontMetrics(font)
        bounds = metrics.boundingRect(QRect(0, 0, 270, 2000), Qt.TextWordWrap, self._text)
        self.resize(320, max(120, min(330, 110 + bounds.height())))
        self._position_near_pet()
        self.show()
        self.raise_()
        # Enough time to read, notice the hint and click. A new message resets
        # the timer, so dialogue never disappears mid-sentence.
        timeout = duration_ms or max(9000, min(26000, 7000 + len(self._text) * 220))
        self._timer.start(timeout)
        self.update()

    def follow(self, pet_rect) -> None:
        self._pet_rect = QRectF(pet_rect)
        if self.isVisible():
            self._position_near_pet()

    def _position_near_pet(self) -> None:
        screen = QApplication.screenAt(self._pet_rect.center().toPoint()) or QApplication.primaryScreen()
        area = screen.availableGeometry()
        margin = 12
        candidates = [
            ("bottom", QPoint(int(self._pet_rect.center().x() - self.width() / 2), int(self._pet_rect.top() - self.height() - margin))),
            ("left", QPoint(int(self._pet_rect.right() + margin), int(self._pet_rect.center().y() - self.height() / 2))),
            ("right", QPoint(int(self._pet_rect.left() - self.width() - margin), int(self._pet_rect.center().y() - self.height() / 2))),
        ]
        for tail, point in candidates:
            rect = QRectF(point.x(), point.y(), self.width(), self.height())
            if area.contains(rect.toRect()) and not rect.intersects(self._pet_rect):
                self._tail = tail
                self.move(point)
                self.update()
                return
        # Clamp every candidate to the screen and pick the one with the least
        # overlap. This keeps a large pet near the screen edge readable too.
        best: tuple[float, str, QPoint] | None = None
        for tail, point in candidates:
            x = max(area.left(), min(area.right() - self.width(), point.x()))
            y = max(area.top(), min(area.bottom() - self.height(), point.y()))
            rect = QRectF(x, y, self.width(), self.height())
            overlap = rect.intersected(self._pet_rect)
            overlap_area = max(0.0, overlap.width()) * max(0.0, overlap.height())
            candidate = (overlap_area, tail, QPoint(x, y))
            if best is None or candidate[0] < best[0]:
                best = candidate
        assert best is not None
        self._tail = best[1]
        self.move(best[2])
        self.update()

    def _body_rect(self) -> QRectF:
        if self._tail == "left":
            return QRectF(15, 7, self.width() - 23, self.height() - 15)
        if self._tail == "right":
            return QRectF(7, 7, self.width() - 23, self.height() - 15)
        return QRectF(7, 7, self.width() - 14, self.height() - 22)

    def paintEvent(self, event) -> None:  # noqa: N802 - Qt API
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        body = self._body_rect()
        if self._pressed:
            body.translate(0, 2)

        shadow = QPainterPath()
        shadow.addRoundedRect(body.translated(0, 4), 20, 20)
        painter.fillPath(shadow, QColor(58, 38, 48, 48))

        gradient = QLinearGradient(body.topLeft(), body.bottomRight())
        gradient.setColorAt(0.0, QColor(255, 253, 248, 255))
        gradient.setColorAt(1.0, QColor(255, 239, 220, 255))
        path = QPainterPath()
        path.addRoundedRect(body, 20, 20)
        painter.fillPath(path, gradient)
        painter.setPen(QPen(QColor(116, 74, 86), 2.2))
        painter.drawPath(path)

        # Tail points at the pet but stays inside this top-level window.
        if self._tail == "left":
            anchor = body.left()
            tail = QPolygonF((QPointF(anchor + 1, body.center().y() - 10), QPointF(2, body.center().y()), QPointF(anchor + 1, body.center().y() + 10)))
        elif self._tail == "right":
            anchor = body.right()
            tail = QPolygonF((QPointF(anchor - 1, body.center().y() - 10), QPointF(self.width() - 2, body.center().y()), QPointF(anchor - 1, body.center().y() + 10)))
        else:
            anchor = body.bottom()
            tail = QPolygonF((QPointF(body.center().x() - 12, anchor - 1), QPointF(body.center().x() + 3, self.height() - 2), QPointF(body.center().x() + 15, anchor - 1)))
        painter.setBrush(QColor(255, 240, 222))
        painter.setPen(QPen(QColor(116, 74, 86), 2.0))
        painter.drawPolygon(tail)

        # Fox-ear title tab and a tiny blue/orange status pair borrow the color
        # relationship from the supplied UI while keeping the original line art.
        tab = QRectF(body.left() + 16, body.top() + 10, 108, 29)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(217, 111, 92))
        painter.drawRoundedRect(tab, 14, 14)
        painter.setPen(QColor(255, 255, 255))
        title_font = QFont("Microsoft YaHei UI", 9)
        title_font.setBold(True)
        painter.setFont(title_font)
        painter.drawText(tab, Qt.AlignCenter, "安洁莉娜")
        painter.setBrush(QColor(31, 111, 190))
        painter.setPen(Qt.NoPen)
        painter.drawEllipse(QPointF(body.right() - 30, body.top() + 24), 5, 5)
        painter.setBrush(QColor(255, 174, 66))
        painter.drawEllipse(QPointF(body.right() - 16, body.top() + 24), 5, 5)

        text_rect = body.adjusted(19, 47, -19, -27)
        font = QFont("Microsoft YaHei UI", 10)
        painter.setFont(font)
        painter.setPen(QColor(68, 47, 55))
        painter.drawText(text_rect, Qt.TextWordWrap | Qt.AlignVCenter, self._text)

        hint_font = QFont("Microsoft YaHei UI", 8)
        painter.setFont(hint_font)
        painter.setPen(QColor(145, 94, 91))
        hint = QRectF(body.left() + 19, body.bottom() - 26, body.width() - 38, 18)
        painter.drawText(hint, Qt.AlignRight | Qt.AlignVCenter, "点击气泡和我聊天  ›")

    def mousePressEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if event.button() == Qt.LeftButton:
            self._pressed = True
            self.update()
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if event.button() == Qt.LeftButton:
            was_pressed = self._pressed
            self._pressed = False
            self.update()
            if was_pressed and self.rect().contains(event.position().toPoint()):
                self._timer.stop()
                self.hide()
                self.clicked.emit()
            event.accept()
            return
        super().mouseReleaseEvent(event)
