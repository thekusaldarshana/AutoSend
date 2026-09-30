"""Makes phonetic Sinhala typing tools (Helakuru and similar) work in AutoSend.

Those tools type by injecting characters as "Unicode packet" keystrokes (virtual key 0xE7), one right after the other
without a key-release in between. Qt mistakes the second and later ones for key auto-repeat and repeats the *first*
character instead of typing the new one. Typing `m` (which should give ම්) gave මම, and every key after that piled up
the same letter.

Windows delivers the correct character for each packet in its WM_CHAR message. So we take that character, type it into
the focused box ourselves, and keep Qt's confused key handling out of it. Ordinary typing is not touched.
"""
from __future__ import annotations

import ctypes
import sys
import time
from ctypes import wintypes

from PySide6.QtCore import QAbstractNativeEventFilter, QEvent, Qt
from PySide6.QtGui import QInputMethodEvent, QKeyEvent
from PySide6.QtWidgets import QApplication

WM_KEYDOWN, WM_KEYUP, WM_CHAR, WM_SYSKEYDOWN, WM_SYSKEYUP = 0x100, 0x101, 0x102, 0x104, 0x105
VK_PACKET = 0xE7
VK_BACK = 0x08
VK_CONTROL, VK_MENU = 0x11, 0x12
HELPER_WINDOW = 1.5      # seconds after an injected character during which its Backspace is applied in order


class _MSG(ctypes.Structure):
    _fields_ = [("hwnd", wintypes.HWND), ("message", wintypes.UINT), ("wParam", wintypes.WPARAM),
                ("lParam", wintypes.LPARAM), ("time", wintypes.DWORD), ("pt", wintypes.POINT)]


def commit_text(text: str) -> bool:
    """Type text into whatever box has the keyboard focus. False if nothing can take it."""
    w = QApplication.focusWidget()
    if w is None or not text:
        return False
    ev = QInputMethodEvent()
    ev.setCommitString(text)
    QApplication.sendEvent(w, ev)
    return True


_user32 = ctypes.windll.user32 if sys.platform == "win32" else None
PM_REMOVE = 0x0001
_ALLOWED_INVISIBLE = (chr(0x200D), chr(0x200C), chr(9))       # zero-width joiner, non-joiner, tab


def send_backspace() -> bool:
    w = QApplication.focusWidget()
    if w is None:
        return False
    for kind in (QEvent.KeyPress, QEvent.KeyRelease):
        QApplication.sendEvent(w, QKeyEvent(kind, Qt.Key_Backspace, Qt.NoModifier))
    return True


def _key_down(vk: int) -> bool:
    return bool(_user32.GetKeyState(vk) & 0x8000)


def _word_modifier_down() -> bool:
    """Ctrl or Alt held: that Backspace means something else (delete a word, ...), so leave it to Qt.
    Shift is deliberately not in this list: Shift+Backspace is a plain Backspace, and Helakuru's capital letters
    (like the A in wAda that makes ැ) send their Backspace while Shift is still held down."""
    return _key_down(VK_CONTROL) or _key_down(VK_MENU)


def _packet_char(msg: _MSG) -> int | None:
    """Ask Windows which character this injected keystroke stands for (it turns it into a WM_CHAR message)."""
    _user32.TranslateMessage(ctypes.byref(msg))
    out = _MSG()
    if _user32.PeekMessageW(ctypes.byref(out), msg.hwnd, WM_CHAR, WM_CHAR, PM_REMOVE):
        return int(out.wParam) & 0xFFFF
    return None


class PacketTyping(QAbstractNativeEventFilter):
    def __init__(self):
        super().__init__()
        self._high = 0                   # first half of a surrogate pair (characters outside the basic plane)
        self._last_packet = 0.0          # when an injected character was last typed

    def nativeEventFilter(self, event_type, message):
        try:
            if bytes(event_type) != b"windows_generic_MSG":
                return False, 0
            m = _MSG.from_address(int(message))
            if m.wParam == VK_BACK and m.message == WM_KEYDOWN and time.monotonic() - self._last_packet < HELPER_WINDOW                     and not _word_modifier_down():
                # Helakuru deletes what it typed before re-typing it. Apply that Backspace right now, in order,
                # instead of letting Qt queue it behind the characters that follow.
                return (True, 0) if send_backspace() else (False, 0)
            if m.wParam != VK_PACKET or m.message not in (WM_KEYDOWN, WM_SYSKEYDOWN, WM_KEYUP, WM_SYSKEYUP):
                return False, 0
            if m.message in (WM_KEYUP, WM_SYSKEYUP):
                return True, 0                                  # nothing to do for the release of an injected character
            c = _packet_char(m)
            if c is None:
                return True, 0
            if 0xD800 <= c < 0xDC00:                            # wait for the second half
                self._high = c
                return True, 0
            if self._high and 0xDC00 <= c < 0xE000:
                text = chr(0x10000 + ((self._high - 0xD800) << 10) + (c - 0xDC00))
            else:
                text = chr(c)
            self._high = 0
            if text.isprintable() or text in _ALLOWED_INVISIBLE:      # joiners are needed for Sinhala conjuncts
                commit_text(text)
                self._last_packet = time.monotonic()
            return True, 0
        except Exception:                # never let a typing helper break the app
            self._high = 0
        return False, 0


_installed: list[PacketTyping] = []


def install(app) -> bool:
    """Install the fix on Windows. Returns True if it was installed."""
    if sys.platform != "win32" or _installed:
        return False
    f = PacketTyping()
    app.installNativeEventFilter(f)
    _installed.append(f)                 # keep a reference so it isn't garbage collected
    return True
