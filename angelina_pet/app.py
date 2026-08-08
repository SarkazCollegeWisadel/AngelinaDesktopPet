from __future__ import annotations

import ctypes
import os
import sys

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QMessageBox

from .constants import APP_ID, APP_NAME, ORGANIZATION
from .controller import PetController


def _single_instance_mutex():
    if os.name != "nt":
        return None, False
    kernel32 = ctypes.windll.kernel32
    kernel32.CreateMutexW.restype = ctypes.c_void_p
    handle = kernel32.CreateMutexW(None, False, f"Local\\{APP_ID}")
    already_running = kernel32.GetLastError() == 183
    return handle, already_running


def run() -> int:
    QApplication.setOrganizationName(ORGANIZATION)
    QApplication.setApplicationName(APP_NAME)
    QApplication.setHighDpiScaleFactorRoundingPolicy(Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
    app = QApplication(sys.argv)
    handle, already_running = _single_instance_mutex()
    if already_running:
        QMessageBox.information(None, APP_NAME, "安洁莉娜已经在桌面上啦。可以在系统托盘找到她。")
        return 0
    try:
        controller = PetController(app)
    except Exception as exc:
        QMessageBox.critical(None, APP_NAME, f"启动失败：\n{exc}")
        return 1
    app.aboutToQuit.connect(controller._save_settings)
    result = app.exec()
    if handle and os.name == "nt":
        ctypes.windll.kernel32.CloseHandle(handle)
    return result
