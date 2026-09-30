"""Helakuru-style typing: injected characters + Backspace must land in the box in the right order.

These replay the exact Windows messages Helakuru produced on the developer's machine (see autosend/ui/inputfix.py).
"""
import ctypes
import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
import pytest
from PySide6.QtWidgets import QApplication, QLineEdit, QPlainTextEdit

app = QApplication.instance() or QApplication([])
from autosend.ui import inputfix as fx

GENERIC = b"windows_generic_MSG"
WM_KEYDOWN, WM_KEYUP = 0x100, 0x101
ZWJ = "‍"


class Typist:
    """Feeds fake Windows messages into the filter, like the real message loop does."""

    def __init__(self, monkeypatch, widget):
        self.widget = widget
        self.filter = fx.PacketTyping()
        self.pending_char = None
        monkeypatch.setattr(fx.QApplication, "focusWidget", staticmethod(lambda: widget))
        monkeypatch.setattr(fx, "_packet_char", lambda msg: self.pending_char)
        self.held = set()                                            # virtual keys currently held down
        monkeypatch.setattr(fx, "_key_down", lambda vk: vk in self.held)

    def send(self, message, wparam, event=GENERIC):
        m = fx._MSG()
        m.message, m.wParam, m.lParam = message, wparam, 0x40000001          # note: "key was already down" is set
        return self.filter.nativeEventFilter(event, ctypes.addressof(m))

    def char(self, ch):                       # one injected character
        self.pending_char = ord(ch) if isinstance(ch, str) else ch
        return self.send(WM_KEYDOWN, fx.VK_PACKET)

    def text(self, s):
        for ch in s:
            assert self.char(ch) == (True, 0)

    def backspace(self):
        return self.send(WM_KEYDOWN, fx.VK_BACK)


@pytest.fixture(params=[QPlainTextEdit, QLineEdit], ids=["multi-line box", "single-line box"])
def typist(request, monkeypatch):
    w = request.param()
    w.show()
    read = (lambda: w.toPlainText()) if isinstance(w, QPlainTextEdit) else (lambda: w.text())
    t = Typist(monkeypatch, w)
    t.read = read
    return t


def test_m_types_one_letter_and_a_virama_not_two_letters(typist):
    typist.text("ම්")               # Helakuru's answer for the key "m": ම then ්
    assert typist.read() == "ම්"    # before the fix this came out as ම ම


def test_a_word_with_replacements_matches_what_helakuru_intends(typist):
    # k -> ක්   r -> ්‍ර (ZWJ + ර + ්)   i -> Backspace, then ි   y -> ය්   a -> Backspace
    typist.text("ක්")
    typist.text(ZWJ + "ර්")
    typist.backspace(); typist.text("ි")
    typist.text("ය්")
    typist.backspace()
    assert typist.read() == "ක්" + ZWJ + "රිය"        # ක්‍රිය


def test_backspace_is_applied_before_the_character_that_follows_it(typist):
    typist.text("ර්")               # ර්
    typist.backspace()
    typist.text("ි")                     # ි
    assert typist.read() == "රි"    # not ර් with the ි deleted again


def test_ordinary_backspace_is_left_alone(typist):
    assert typist.backspace() == (False, 0)                       # nothing was typed by a tool: Qt handles it as usual
    typist.text("x")
    typist.held = {fx.VK_CONTROL}                                 # Ctrl+Backspace (delete a word): never touched
    assert typist.backspace() == (False, 0)
    typist.held = {fx.VK_MENU}                                    # Alt held: never touched
    assert typist.backspace() == (False, 0)


def test_backspace_goes_back_to_normal_after_a_pause(typist, monkeypatch):
    typist.text("ab")
    t0 = fx.time.monotonic()
    monkeypatch.setattr(fx.time, "monotonic", lambda: t0 + fx.HELPER_WINDOW + 1)
    assert typist.backspace() == (False, 0)


def test_characters_outside_the_basic_plane_arrive_whole(typist):
    assert typist.char(0xD83D) == (True, 0)                       # first half of 😀
    assert typist.char(0xDE00) == (True, 0)
    assert typist.read() == "\U0001F600"


def test_control_characters_are_not_typed(typist):
    assert typist.char(0x07) == (True, 0)
    assert typist.read() == ""


def test_key_release_of_an_injected_character_is_ignored(typist):
    assert typist.send(WM_KEYUP, fx.VK_PACKET) == (True, 0)
    assert typist.read() == ""


def test_other_messages_and_other_event_types_pass_through(typist):
    assert typist.send(WM_KEYDOWN, 0x41) == (False, 0)            # the letter A
    assert typist.send(WM_KEYDOWN, fx.VK_PACKET, event=b"windows_dispatcher_MSG") == (False, 0)


def test_a_broken_message_never_crashes_the_app(typist, monkeypatch):
    monkeypatch.setattr(fx, "_packet_char", lambda msg: (_ for _ in ()).throw(RuntimeError("boom")))
    assert typist.send(WM_KEYDOWN, fx.VK_PACKET) == (False, 0)


def test_capital_letters_work_backspace_is_applied_even_while_shift_is_held(typist):
    """wAda: after w (ව්) the capital A sends Backspace + ැ while Shift is down. This used to leave ව්ඩ."""
    typist.text("ව්")                                  # ව්
    typist.held = {0x10}                                          # Shift down for the capital A
    assert typist.backspace() == (True, 0)
    typist.text("ැ")                                         # ැ
    typist.held = set()
    typist.text("ඩ්")                                  # d -> ඩ්
    typist.backspace()                                            # a -> remove the virama
    assert typist.read() == "වැඩ"                 # වැඩ


def test_long_ae_pilla_pAAna_gives_pen(typist):
    """pAAna -> පෑන : each capital A replaces the previous vowel sign, with Shift held during the Backspace."""
    typist.text("ප්")                                    # p -> ප්
    typist.held = {0x10}
    typist.backspace(); typist.text("ැ")                      # A -> ැ
    typist.backspace(); typist.text("ෑ")                      # A -> ෑ (long form)
    typist.held = set()
    typist.text("න්")                                    # n -> න්
    typist.backspace()                                             # a -> drop the virama
    assert typist.read() == "පෑන"                   # පෑන
