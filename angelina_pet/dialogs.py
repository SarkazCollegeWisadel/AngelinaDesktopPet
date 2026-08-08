from __future__ import annotations

import html
from dataclasses import replace

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QMessageBox,
    QSpinBox,
    QTabWidget,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from .settings import AppSettings
from .ai import AIService, recommended_reasoning_effort, recommended_thinking
from .constants import DEEPSEEK_BASE_URL, DEEPSEEK_MODEL, DEFAULT_STEP_BASE_URL, DEFAULT_STEP_MODEL


class SettingsDialog(QDialog):
    def __init__(self, settings: AppSettings, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("安洁莉娜 · AI 与隐私设置")
        self.resize(560, 430)
        self.value = replace(settings)
        self._test_ai = AIService(self)
        self._test_ai.completed.connect(self._on_test_completed)
        self._test_ai.failed.connect(self._on_test_failed)
        self.finished.connect(lambda _: self._test_ai.shutdown())

        tabs = QTabWidget()
        tabs.addTab(self._text_tab(), "文本 AI")
        tabs.addTab(self._vision_tab(), "屏幕理解")
        tabs.addTab(self._behavior_tab(), "行为与隐私")

        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self._save)
        buttons.rejected.connect(self.reject)
        layout = QVBoxLayout(self)
        layout.addWidget(tabs)
        layout.addWidget(buttons)

    @staticmethod
    def _key_edit(value: str) -> QLineEdit:
        edit = QLineEdit(value)
        edit.setEchoMode(QLineEdit.Password)
        edit.setPlaceholderText("只在本机输入，不要粘贴到聊天中")
        return edit

    def _text_tab(self) -> QWidget:
        page = QWidget()
        form = QFormLayout(page)
        self.text_enabled = QCheckBox("启用联网文本回复")
        self.text_enabled.setChecked(self.value.text_ai_enabled)
        self.text_base = QLineEdit(self.value.text_base_url)
        self.text_model = QLineEdit(self.value.text_model)
        self.text_key = self._key_edit(self.value.text_api_key)
        form.addRow(self.text_enabled)
        form.addRow("Base URL", self.text_base)
        form.addRow("模型", self.text_model)
        form.addRow("API Key", self.text_key)
        presets = QHBoxLayout()
        step_button = QPushButton("使用 Step Plan 3.7")
        deepseek_button = QPushButton("使用 DeepSeek")
        self.test_text_button = QPushButton("测试连接")
        step_button.clicked.connect(self._use_step_text)
        deepseek_button.clicked.connect(self._use_deepseek_text)
        self.test_text_button.clicked.connect(self._test_text_connection)
        presets.addWidget(step_button)
        presets.addWidget(deepseek_button)
        presets.addWidget(self.test_text_button)
        form.addRow("快速配置", presets)
        self.text_test_status = QLabel("")
        self.text_test_status.setWordWrap(True)
        form.addRow("连接状态", self.text_test_status)
        note = QLabel("兼容 OpenAI Chat Completions。可填写 DeepSeek，也可改为 Step Plan 文本模型。\n未启用或接口失败时，桌宠会使用本地台词，不影响其他功能。")
        note.setWordWrap(True)
        form.addRow(note)
        return page

    def _vision_tab(self) -> QWidget:
        page = QWidget()
        form = QFormLayout(page)
        self.vision_enabled = QCheckBox("启用屏幕理解（手动或定时）")
        self.vision_enabled.setChecked(self.value.vision_enabled)
        self.vision_periodic = QCheckBox("定时看一眼桌面并主动搭话")
        self.vision_periodic.setChecked(self.value.vision_periodic_enabled)
        self.vision_interval = QSpinBox()
        self.vision_interval.setRange(5, 240)
        self.vision_interval.setSuffix(" 分钟")
        self.vision_interval.setValue(self.value.vision_interval_minutes)
        self.vision_interval.setEnabled(self.value.vision_periodic_enabled)
        self.vision_periodic.toggled.connect(self._periodic_vision_changed)
        self.vision_base = QLineEdit(self.value.vision_base_url)
        self.vision_model = QLineEdit(self.value.vision_model)
        self.vision_key = self._key_edit(self.value.vision_api_key)
        form.addRow(self.vision_enabled)
        periodic_row = QWidget()
        periodic_layout = QHBoxLayout(periodic_row)
        periodic_layout.setContentsMargins(0, 0, 0, 0)
        periodic_layout.addWidget(self.vision_periodic, 1)
        periodic_layout.addWidget(self.vision_interval)
        form.addRow(periodic_row)
        form.addRow("Base URL", self.vision_base)
        form.addRow("视觉模型", self.vision_model)
        form.addRow("API Key", self.vision_key)
        copy_button = QPushButton("复制文本 AI 的地址、模型和 Key")
        copy_button.clicked.connect(self._copy_text_to_vision)
        form.addRow("快速配置", copy_button)
        warning = QLabel(
            "Step Plan 的 step-3.7-flash 原生支持图片理解，可直接用于这个功能。"
            "请不要把视觉模型改成 step-router-v1：该路由明确不接受图片。手动观察会逐次确认；"
            "定时观察会按上方间隔自动发送整屏截图，不再逐次弹窗。截图仅在内存中压缩、不落盘，关闭开关即停止。"
        )
        warning.setWordWrap(True)
        warning.setStyleSheet("color:#8a4d39;")
        form.addRow(warning)
        return page

    def _periodic_vision_changed(self, enabled: bool) -> None:
        self.vision_interval.setEnabled(enabled)
        if enabled:
            self.vision_enabled.setChecked(True)

    def _use_step_text(self) -> None:
        self.text_enabled.setChecked(True)
        self.text_base.setText(DEFAULT_STEP_BASE_URL)
        self.text_model.setText(DEFAULT_STEP_MODEL)

    def _use_deepseek_text(self) -> None:
        self.text_enabled.setChecked(True)
        self.text_base.setText(DEEPSEEK_BASE_URL)
        self.text_model.setText(DEEPSEEK_MODEL)

    def _copy_text_to_vision(self) -> None:
        self.vision_enabled.setChecked(True)
        self.vision_base.setText(self.text_base.text())
        self.vision_model.setText(self.text_model.text())
        self.vision_key.setText(self.text_key.text())

    def _test_text_connection(self) -> None:
        base_url = self.text_base.text().strip()
        model = self.text_model.text().strip()
        api_key = self.text_key.text().strip()
        if not base_url or not model or not api_key:
            self.text_test_status.setStyleSheet("color:#a64b3c;")
            self.text_test_status.setText("请先填写 Base URL、模型和 API Key。")
            return
        self.test_text_button.setEnabled(False)
        self.text_test_status.setStyleSheet("color:#496b83;")
        self.text_test_status.setText("正在送出一封测试消息……")
        self._test_ai.submit(
            "settings-text-test",
            base_url=base_url,
            api_key=api_key,
            model=model,
            messages=[{"role": "user", "content": "只回复：连接正常"}],
            max_tokens=512,
            temperature=0.2,
            reasoning_effort=recommended_reasoning_effort(base_url, model),
            thinking=recommended_thinking(base_url, model),
            timeout=60.0,
        )

    def _on_test_completed(self, request_id: str, text: str) -> None:
        if request_id != "settings-text-test":
            return
        self.test_text_button.setEnabled(True)
        self.text_test_status.setStyleSheet("color:#39735b;")
        preview = " ".join(text.split())[:64]
        self.text_test_status.setText(f"连接成功 · {preview}")

    def _on_test_failed(self, request_id: str, error: str) -> None:
        if request_id != "settings-text-test":
            return
        self.test_text_button.setEnabled(True)
        self.text_test_status.setStyleSheet("color:#a64b3c;")
        self.text_test_status.setText(f"连接失败 · {error[:180]}")

    def _behavior_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        self.keyboard_reaction = QCheckBox("检测全局按键节奏，触发办公彩蛋（不记录输入内容）")
        self.keyboard_reaction.setChecked(self.value.keyboard_reaction)
        self.idle_nudges = QCheckBox("长时间没有互动时，让安洁莉娜主动搭话")
        self.idle_nudges.setChecked(self.value.idle_nudges)
        layout.addWidget(self.keyboard_reaction)
        layout.addWidget(self.idle_nudges)
        privacy = QLabel(
            "隐私说明：键盘监听只传递按键类别给本地动画，内存中只保留最近数秒的时间点；"
            "不拼接文字、不写日志、不发送到 AI。屏幕截图不会落盘；手动触发会确认，定时触发按你设置的间隔运行。API Key"
            " 使用当前 Windows 用户的 DPAPI 加密保存。"
        )
        privacy.setWordWrap(True)
        privacy.setAlignment(Qt.AlignTop)
        layout.addWidget(privacy)
        layout.addStretch()
        return page

    def _save(self) -> None:
        if self.text_enabled.isChecked() and not all(
            (self.text_base.text().strip(), self.text_model.text().strip(), self.text_key.text().strip())
        ):
            QMessageBox.warning(self, "文本 AI 配置不完整", "启用联网文本回复时，请填写 Base URL、模型和 API Key。")
            return
        vision_requested = self.vision_enabled.isChecked() or self.vision_periodic.isChecked()
        if vision_requested and not all(
            (self.vision_base.text().strip(), self.vision_model.text().strip(), self.vision_key.text().strip())
        ):
            QMessageBox.warning(self, "屏幕理解配置不完整", "启用屏幕理解时，请填写 Base URL、视觉模型和 API Key。")
            return
        self.value.text_ai_enabled = self.text_enabled.isChecked()
        self.value.text_base_url = self.text_base.text().strip()
        self.value.text_model = self.text_model.text().strip()
        self.value.text_api_key = self.text_key.text().strip()
        self.value.vision_enabled = vision_requested
        self.value.vision_periodic_enabled = self.vision_periodic.isChecked()
        self.value.vision_interval_minutes = self.vision_interval.value()
        self.value.vision_base_url = self.vision_base.text().strip()
        self.value.vision_model = self.vision_model.text().strip()
        self.value.vision_api_key = self.vision_key.text().strip()
        self.value.keyboard_reaction = self.keyboard_reaction.isChecked()
        self.value.idle_nudges = self.idle_nudges.isChecked()
        self.accept()


class ChatDialog(QDialog):
    send_requested = Signal(str)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("和安洁莉娜聊天")
        self.resize(470, 520)
        self.setStyleSheet(
            "QDialog{background:#fff8ee;}"
            "QTextBrowser{background:#fffdf8;border:2px solid #e6a080;border-radius:14px;padding:8px;color:#443038;}"
            "QLineEdit{background:white;border:2px solid #e6a080;border-radius:12px;padding:9px;color:#443038;}"
            "QPushButton{background:#d96f5c;color:white;border:0;border-radius:12px;padding:9px 18px;font-weight:600;}"
            "QPushButton:disabled{background:#d8b8ae;}"
        )
        self.status = QLabel()
        self.status.setStyleSheet("color:#7b5964;padding:3px 8px;background:#f7e7d4;border-radius:9px;")
        self.view = QTextBrowser()
        self.view.setOpenExternalLinks(False)
        self.input = QLineEdit()
        self.input.setPlaceholderText("和安洁莉娜说点什么……")
        self.send = QPushButton("发送")
        self.send.clicked.connect(self._send)
        self.input.returnPressed.connect(self._send)
        row = QHBoxLayout()
        row.addWidget(self.input, 1)
        row.addWidget(self.send)
        layout = QVBoxLayout(self)
        layout.addWidget(self.status)
        layout.addWidget(self.view, 1)
        layout.addLayout(row)
        self.append_message("安洁莉娜", "博士，今天想聊些什么？")
        self.set_connection_status(False, "本地活人台词")

    def set_connection_status(self, online: bool, provider: str, verified: bool = False) -> None:
        dot = "●" if online else "○"
        if online:
            state = "连接正常" if verified else "已配置"
            label = f"{dot} {state}：{provider}"
        else:
            label = f"{dot} {provider}（右键桌宠可启用 Step Plan）"
        self.status.setText(label)
        self.status.setStyleSheet(
            "color:#496b63;padding:4px 9px;background:#e4f2e8;border-radius:9px;"
            if online
            else "color:#7b5964;padding:4px 9px;background:#f7e7d4;border-radius:9px;"
        )

    def set_connection_error(self, error: str) -> None:
        self.status.setText(f"× 连接失败：{' '.join(error.split())[:110]}")
        self.status.setStyleSheet("color:#973f36;padding:4px 9px;background:#f9ded6;border-radius:9px;")

    def _send(self) -> None:
        text = self.input.text().strip()
        if not text:
            return
        self.input.clear()
        self.append_message("博士", text)
        self.set_busy(True)
        self.send_requested.emit(text)

    def append_message(self, author: str, text: str) -> None:
        color = "#9b5363" if author == "安洁莉娜" else "#496b83"
        self.view.append(
            f'<p><b style="color:{color}">{html.escape(author)}</b><br>{html.escape(text).replace(chr(10), "<br>")}</p>'
        )
        self.view.verticalScrollBar().setValue(self.view.verticalScrollBar().maximum())

    def set_busy(self, busy: bool) -> None:
        self.input.setEnabled(not busy)
        self.send.setEnabled(not busy)
        if not busy:
            self.input.setFocus()
