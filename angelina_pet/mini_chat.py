from __future__ import annotations

from collections import deque

from PySide6.QtCore import QPoint, QRect, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QGuiApplication, QPainter, QPainterPath, QPen, QPolygonF
from PySide6.QtWidgets import (
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)


class MiniChatDialog(QDialog):
    """A compact, pet-anchored chat window that retains two recent turns."""

    send_requested = Signal(str)

    _WINDOW_WIDTH = 388
    _WINDOW_HEIGHT = 268
    _TAIL_HEIGHT = 13

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("miniChatDialog")
        self.setWindowTitle("和安洁莉娜说说话")
        self.setWindowFlags(Qt.Tool | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WA_DeleteOnClose, False)
        self.setFixedSize(self._WINDOW_WIDTH, self._WINDOW_HEIGHT)
        self.setFont(QFont("Microsoft YaHei UI", 9))

        self._messages: deque[tuple[str, str]] = deque(maxlen=4)
        self._tail_on_top = True
        self._tail_anchor_x = self.width() / 2
        self._topmost = True

        self._panel = QWidget(self)
        self._panel.setObjectName("chatPanel")
        self._build_ui()
        self._apply_style()
        self._update_panel_geometry()

        self.append_message("安洁莉娜", "博士，想和我说点什么呢？")
        self.set_connection_status(False, "本地台词")

    def _build_ui(self) -> None:
        root = QVBoxLayout(self._panel)
        root.setContentsMargins(8, 6, 8, 7)
        root.setSpacing(5)

        header = QHBoxLayout()
        header.setContentsMargins(0, 0, 0, 0)
        header.setSpacing(6)

        avatar = QLabel("安")
        avatar.setObjectName("avatar")
        avatar.setAlignment(Qt.AlignCenter)
        avatar.setFixedSize(28, 28)
        header.addWidget(avatar)

        title = QLabel("安洁莉娜")
        title.setObjectName("title")
        header.addWidget(title)

        self.status = QLabel()
        self.status.setObjectName("connectionStatus")
        self.status.setAlignment(Qt.AlignCenter)
        self.status.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Fixed)
        header.addWidget(self.status)
        header.addStretch(1)

        close_button = QPushButton("×")
        close_button.setObjectName("closeButton")
        close_button.setToolTip("收起聊天")
        close_button.setFixedSize(27, 27)
        close_button.clicked.connect(self.hide)
        header.addWidget(close_button)
        root.addLayout(header)

        self.system_hint = QLabel()
        self.system_hint.setObjectName("systemHint")
        self.system_hint.setTextFormat(Qt.PlainText)
        self.system_hint.setToolTip("")
        self.system_hint.setVisible(False)
        root.addWidget(self.system_hint)

        self.message_scroll = QScrollArea()
        self.message_scroll.setObjectName("messageScroll")
        self.message_scroll.setWidgetResizable(True)
        self.message_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.message_scroll.setFrameShape(QFrame.NoFrame)
        self.message_scroll.viewport().setAutoFillBackground(False)

        self.message_host = QWidget()
        self.message_host.setObjectName("messageHost")
        self.message_layout = QVBoxLayout(self.message_host)
        self.message_layout.setContentsMargins(2, 2, 4, 2)
        self.message_layout.setSpacing(5)
        self.message_layout.addStretch(1)
        self.message_scroll.setWidget(self.message_host)
        root.addWidget(self.message_scroll, 1)

        input_row = QHBoxLayout()
        input_row.setContentsMargins(0, 0, 0, 0)
        input_row.setSpacing(6)
        self.input = QLineEdit()
        self.input.setObjectName("chatInput")
        self.input.setPlaceholderText("对安洁莉娜说点什么……")
        self.input.setClearButtonEnabled(True)
        self.input.returnPressed.connect(self._send)
        input_row.addWidget(self.input, 1)

        self.send = QPushButton("发送")
        self.send.setObjectName("sendButton")
        self.send.setCursor(Qt.PointingHandCursor)
        self.send.setFixedWidth(66)
        self.send.clicked.connect(self._send)
        input_row.addWidget(self.send)
        root.addLayout(input_row)

    def _apply_style(self) -> None:
        self.setStyleSheet(
            "QWidget#chatPanel{background:transparent;color:#493741;}"
            "QLabel#avatar{background:#ef8c79;color:#fffaf0;border:2px solid #fff4df;"
            "border-radius:14px;font-size:13px;font-weight:700;}"
            "QLabel#title{color:#7c4857;font-size:13px;font-weight:700;}"
            "QLabel#connectionStatus{padding:3px 7px;border-radius:8px;font-size:9px;}"
            "QLabel#systemHint{background:#fff0ca;color:#806047;border:1px solid #edc27a;"
            "border-radius:8px;padding:3px 7px;font-size:9px;}"
            "QScrollArea#messageScroll,QWidget#messageHost{background:transparent;border:0;}"
            "QLineEdit#chatInput{background:#fffdf7;color:#46363d;border:2px solid #efaa91;"
            "border-radius:14px;padding:7px 10px;selection-background-color:#74a8cb;}"
            "QLineEdit#chatInput:focus{border-color:#df776b;background:#ffffff;}"
            "QPushButton#sendButton{background:#e67f6e;color:white;border:0;border-radius:14px;"
            "padding:7px 10px;font-weight:700;}"
            "QPushButton#sendButton:hover{background:#d96b60;}"
            "QPushButton#sendButton:pressed{background:#c55e58;padding-top:9px;}"
            "QPushButton#sendButton:disabled{background:#dcbab0;color:#fff8f0;}"
            "QPushButton#closeButton{background:#f4d8ca;color:#8b5660;border:0;"
            "border-radius:13px;font-size:17px;font-weight:700;}"
            "QPushButton#closeButton:hover{background:#efb8aa;color:#733f4b;}"
            "QScrollBar:vertical{background:transparent;width:6px;margin:2px 0;}"
            "QScrollBar::handle:vertical{background:#a9c8db;border-radius:3px;min-height:22px;}"
            "QScrollBar::add-line:vertical,QScrollBar::sub-line:vertical{height:0;}"
        )

    def paintEvent(self, event) -> None:  # noqa: N802 - Qt API
        del event
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)

        if self._tail_on_top:
            body = QRectF(6, self._TAIL_HEIGHT, self.width() - 12, self.height() - self._TAIL_HEIGHT - 6)
            base_y = body.top() + 1
            tail = QPolygonF(
                [
                    QPoint(int(self._tail_anchor_x - 12), int(base_y + 1)),
                    QPoint(int(self._tail_anchor_x), 3),
                    QPoint(int(self._tail_anchor_x + 13), int(base_y + 1)),
                ]
            )
        else:
            body = QRectF(6, 6, self.width() - 12, self.height() - self._TAIL_HEIGHT - 6)
            base_y = body.bottom() - 1
            tail = QPolygonF(
                [
                    QPoint(int(self._tail_anchor_x - 12), int(base_y - 1)),
                    QPoint(int(self._tail_anchor_x), self.height() - 3),
                    QPoint(int(self._tail_anchor_x + 13), int(base_y - 1)),
                ]
            )

        shadow = body.translated(0, 3)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(75, 46, 55, 44))
        painter.drawRoundedRect(shadow, 22, 22)

        body_path = QPainterPath()
        body_path.addRoundedRect(body, 22, 22)
        painter.setBrush(QColor("#fff8e9"))
        painter.setPen(QPen(QColor("#e89b84"), 2))
        painter.drawPath(body_path)

        # Paint the tail after the body so its fill hides the base seam.
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor("#fff8e9"))
        painter.drawPolygon(tail)
        painter.setPen(QPen(QColor("#e89b84"), 2))
        points = list(tail)
        painter.drawLine(points[0], points[1])
        painter.drawLine(points[1], points[2])

        # Small candy-like decorations keep the frame close to the source palette.
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor("#78a9c8"))
        painter.drawEllipse(body.right() - 44, body.top() + 12, 7, 7)
        painter.setBrush(QColor("#efb05f"))
        painter.drawEllipse(body.right() - 32, body.top() + 11, 5, 5)

    def resizeEvent(self, event) -> None:  # noqa: N802 - Qt API
        super().resizeEvent(event)
        self._update_panel_geometry()

    def _update_panel_geometry(self) -> None:
        body_top = self._TAIL_HEIGHT if self._tail_on_top else 6
        body_bottom = self.height() - (self._TAIL_HEIGHT if not self._tail_on_top else 6)
        self._panel.setGeometry(14, body_top + 5, self.width() - 28, body_bottom - body_top - 10)
        self.update()

    def _send(self) -> None:
        text = self.input.text().strip()
        if not text:
            return
        self.input.clear()
        self.append_message("博士", text)
        self.set_busy(True)
        self.send_requested.emit(text)

    def append_message(self, author: str, text: str) -> None:
        """Append one message; system entries become a non-historic status hint."""
        clean_author = str(author).strip() or "消息"
        clean_text = str(text).strip()
        if not clean_text:
            return
        if clean_author == "系统":
            compact = " ".join(clean_text.split())
            self.system_hint.setText(f"✶ {compact[:100]}")
            self.system_hint.setToolTip(clean_text)
            self.system_hint.setVisible(True)
            return

        self._messages.append((clean_author, clean_text))
        self._rebuild_messages()

    def _rebuild_messages(self) -> None:
        while self.message_layout.count():
            item = self.message_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

        self.message_layout.addStretch(1)
        for author, text in self._messages:
            is_pet = author == "安洁莉娜"
            row_widget = QWidget()
            row_widget.setObjectName("messageRow")
            row = QHBoxLayout(row_widget)
            row.setContentsMargins(0, 0, 0, 0)

            bubble = QFrame()
            bubble.setObjectName("petBubble" if is_pet else "doctorBubble")
            bubble.setMaximumWidth(286)
            bubble.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Preferred)
            bubble_layout = QVBoxLayout(bubble)
            bubble_layout.setContentsMargins(9, 5, 9, 6)
            bubble_layout.setSpacing(1)

            author_label = QLabel(author)
            author_label.setObjectName("messageAuthor")
            author_label.setTextFormat(Qt.PlainText)
            text_label = QLabel(text)
            text_label.setObjectName("messageText")
            text_label.setTextFormat(Qt.PlainText)
            text_label.setWordWrap(True)
            text_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
            bubble_layout.addWidget(author_label)
            bubble_layout.addWidget(text_label)

            if is_pet:
                row.addWidget(bubble)
                row.addStretch(1)
                bubble.setStyleSheet(
                    "QFrame#petBubble{background:#fff0dc;border:1px solid #eca68d;border-radius:12px;}"
                    "QLabel#messageAuthor{color:#a15365;font-size:9px;font-weight:700;}"
                    "QLabel#messageText{color:#493741;font-size:10px;}"
                )
            else:
                row.addStretch(1)
                row.addWidget(bubble)
                bubble.setStyleSheet(
                    "QFrame#doctorBubble{background:#dcecf4;border:1px solid #8db8cf;border-radius:12px;}"
                    "QLabel#messageAuthor{color:#47758f;font-size:9px;font-weight:700;}"
                    "QLabel#messageText{color:#354a59;font-size:10px;}"
                )
            self.message_layout.addWidget(row_widget)

        QTimer.singleShot(
            0,
            lambda: self.message_scroll.verticalScrollBar().setValue(
                self.message_scroll.verticalScrollBar().maximum()
            ),
        )

    def set_busy(self, busy: bool) -> None:
        self.input.setEnabled(not busy)
        self.send.setEnabled(not busy)
        self.send.setText("想一想…" if busy else "发送")
        if not busy:
            self.input.setFocus(Qt.OtherFocusReason)

    def set_connection_status(self, online: bool, provider: str, verified: bool = False) -> None:
        provider_text = " ".join(str(provider).split())[:24]
        if online:
            state = "已连接" if verified else "已配置"
            self.status.setText(f"● {state} · {provider_text}")
            self.status.setStyleSheet(
                "background:#dcefe5;color:#47705f;border:1px solid #a9d1bc;"
                "padding:3px 7px;border-radius:8px;font-size:9px;"
            )
        else:
            self.status.setText(f"○ {provider_text}")
            self.status.setStyleSheet(
                "background:#f4e4d5;color:#805e64;border:1px solid #e7c7b3;"
                "padding:3px 7px;border-radius:8px;font-size:9px;"
            )
        self.status.setToolTip(str(provider))

    def set_connection_error(self, error: str) -> None:
        compact = " ".join(str(error).split())
        self.status.setText("× 连接失败")
        self.status.setStyleSheet(
            "background:#f8dcd5;color:#983f3c;border:1px solid #e8a79c;"
            "padding:3px 7px;border-radius:8px;font-size:9px;"
        )
        self.status.setToolTip(str(error))
        if compact:
            self.system_hint.setText(f"✶ {compact[:100]}")
            self.system_hint.setToolTip(str(error))
            self.system_hint.setVisible(True)

    def set_topmost(self, topmost: bool) -> None:
        topmost = bool(topmost)
        if self._topmost == topmost:
            return
        was_visible = self.isVisible()
        self._topmost = topmost
        self.setWindowFlag(Qt.WindowStaysOnTopHint, topmost)
        if was_visible:
            self.show()
            self.raise_()

    def show_near(self, pet_rect: QRect | QRectF, activate: bool = True) -> None:
        """Show below the pet, or above it when the current screen has less room."""
        self._position_near(pet_rect)
        self.setAttribute(Qt.WA_ShowWithoutActivating, not activate)
        self.show()
        self.raise_()
        if activate:
            self.activateWindow()
            self.input.setFocus(Qt.OtherFocusReason)

    def follow(self, pet_rect: QRect | QRectF) -> None:
        """Keep an already visible chat bubble attached while the pet moves."""
        if self.isVisible():
            self._position_near(pet_rect)

    def _position_near(self, pet_rect: QRect | QRectF) -> None:
        rect = pet_rect.toAlignedRect() if isinstance(pet_rect, QRectF) else QRect(pet_rect)
        screen = QGuiApplication.screenAt(rect.center()) or QGuiApplication.primaryScreen()
        if screen is None:
            return
        available = screen.availableGeometry()
        gap = 9
        room_below = available.bottom() - rect.bottom()
        room_above = rect.top() - available.top()
        place_below = room_below >= self.height() + gap or room_below >= room_above

        x = rect.center().x() - self.width() // 2
        x = max(available.left(), min(x, available.right() - self.width() + 1))
        if place_below:
            y = rect.bottom() + gap
        else:
            y = rect.top() - self.height() - gap
        y = max(available.top(), min(y, available.bottom() - self.height() + 1))

        self._tail_on_top = place_below
        self._tail_anchor_x = float(max(42, min(rect.center().x() - x, self.width() - 42)))
        self._update_panel_geometry()
        self.move(x, y)
