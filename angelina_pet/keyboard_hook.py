from __future__ import annotations

import ctypes
import os
import threading
from ctypes import wintypes

from PySide6.QtCore import QObject, Signal


VK_NAMES = {
    0x08: "Backspace",
    0x09: "Tab",
    0x0D: "Enter",
    0x10: "Shift",
    0x11: "Ctrl",
    0x12: "Alt",
    0x1B: "Esc",
    0x20: "Space",
    0x21: "PgUp",
    0x22: "PgDn",
    0x23: "End",
    0x24: "Home",
    0x25: "←",
    0x26: "↑",
    0x27: "→",
    0x28: "↓",
    0x2E: "Delete",
}


def key_name(vk_code: int) -> str:
    if 0x30 <= vk_code <= 0x39 or 0x41 <= vk_code <= 0x5A:
        return chr(vk_code)
    if 0x70 <= vk_code <= 0x87:
        return f"F{vk_code - 0x6F}"
    return VK_NAMES.get(vk_code, "Key")


class KeyboardHook(QObject):
    key_pressed = Signal(int, str)
    error = Signal(str)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._thread: threading.Thread | None = None
        self._thread_id = 0
        self._ready = threading.Event()

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        if os.name != "nt":
            self.error.emit("全局键盘彩蛋仅支持 Windows")
            return
        self._ready.clear()
        self._thread = threading.Thread(target=self._run, name="angelina-keyboard", daemon=True)
        self._thread.start()
        self._ready.wait(timeout=1.5)

    def stop(self) -> None:
        thread = self._thread
        if self._thread_id and os.name == "nt":
            user32 = ctypes.windll.user32
            user32.PostThreadMessageW.argtypes = [wintypes.DWORD, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
            user32.PostThreadMessageW.restype = wintypes.BOOL
            user32.PostThreadMessageW(self._thread_id, 0x0012, 0, 0)  # WM_QUIT
        if thread and thread is not threading.current_thread():
            thread.join(timeout=0.8)
        if not thread or not thread.is_alive():
            self._thread = None
            self._thread_id = 0

    def _run(self) -> None:
        user32 = ctypes.windll.user32
        kernel32 = ctypes.windll.kernel32
        kernel32.GetModuleHandleW.argtypes = [wintypes.LPCWSTR]
        kernel32.GetModuleHandleW.restype = wintypes.HANDLE
        kernel32.GetCurrentThreadId.argtypes = []
        kernel32.GetCurrentThreadId.restype = wintypes.DWORD
        user32.CallNextHookEx.argtypes = [wintypes.HANDLE, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM]
        user32.CallNextHookEx.restype = wintypes.LPARAM

        class KBDLLHOOKSTRUCT(ctypes.Structure):
            _fields_ = [
                ("vkCode", wintypes.DWORD),
                ("scanCode", wintypes.DWORD),
                ("flags", wintypes.DWORD),
                ("time", wintypes.DWORD),
                ("dwExtraInfo", wintypes.WPARAM),
            ]

        callback_type = ctypes.WINFUNCTYPE(
            wintypes.LPARAM, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM
        )

        @callback_type
        def callback(code: int, wparam: int, lparam: int) -> int:
            if code >= 0 and wparam in (0x0100, 0x0104):  # WM_KEYDOWN / WM_SYSKEYDOWN
                data = ctypes.cast(lparam, ctypes.POINTER(KBDLLHOOKSTRUCT)).contents
                self.key_pressed.emit(int(data.vkCode), key_name(int(data.vkCode)))
            return user32.CallNextHookEx(None, code, wparam, lparam)

        user32.SetWindowsHookExW.restype = wintypes.HANDLE
        user32.SetWindowsHookExW.argtypes = [ctypes.c_int, callback_type, wintypes.HANDLE, wintypes.DWORD]
        user32.UnhookWindowsHookEx.argtypes = [wintypes.HANDLE]
        user32.UnhookWindowsHookEx.restype = wintypes.BOOL
        user32.GetMessageW.argtypes = [ctypes.POINTER(wintypes.MSG), wintypes.HANDLE, wintypes.UINT, wintypes.UINT]
        user32.GetMessageW.restype = wintypes.BOOL
        hook = user32.SetWindowsHookExW(13, callback, kernel32.GetModuleHandleW(None), 0)
        if not hook:
            self.error.emit("无法安装全局键盘监听；键盘彩蛋仍可从右键菜单手动打开")
            self._ready.set()
            return
        self._thread_id = kernel32.GetCurrentThreadId()
        self._ready.set()
        message = wintypes.MSG()
        while user32.GetMessageW(ctypes.byref(message), None, 0, 0) > 0:
            user32.TranslateMessage(ctypes.byref(message))
            user32.DispatchMessageW(ctypes.byref(message))
        user32.UnhookWindowsHookEx(hook)
        self._thread_id = 0
