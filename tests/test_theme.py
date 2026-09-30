import os
import re
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ["AUTOSEND_DATA"] = tempfile.mkdtemp()
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
import pytest
from PySide6.QtWidgets import QApplication, QLabel, QPushButton

app = QApplication.instance() or QApplication([])
from autosend.ui import theme


def lum(h: str) -> float:
    h = h.lstrip("#")
    r, g, b = (int(h[i:i + 2], 16) / 255 for i in (0, 2, 4))
    f = lambda c: c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b)


def ratio(a: str, b: str) -> float:
    la, lb = sorted((lum(a), lum(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


def test_palettes_have_the_same_tokens():
    assert set(theme.LIGHT) == set(theme.DARK)
    for pal in (theme.LIGHT, theme.DARK):
        assert all(re.fullmatch(r"#[0-9A-Fa-f]{6}", v) for v in pal.values())


PAIRS = [   # (foreground, background, minimum contrast)
    ("text", "bg", 7), ("text", "surface", 7), ("muted", "surface", 4.5), ("muted", "bg", 4.5),
    ("primary_text", "primary_soft", 4.5), ("primary_text", "surface", 4.5),
    ("danger", "danger_soft", 4.5), ("danger", "surface", 4.5), ("warn", "warn_soft", 4.5),
    ("info", "info_soft", 4.5), ("bubble_fg", "bubble", 4.5), ("tooltip_fg", "tooltip_bg", 7),
]


@pytest.mark.parametrize("name,pal", [("light", theme.LIGHT), ("dark", theme.DARK)])
def test_contrast(name, pal):
    for fg, bg, need in PAIRS:
        r = ratio(pal[fg], pal[bg])
        assert r >= need, f"{name}: {fg} on {bg} is {r:.2f}, needs {need}"
    # white text on the green button (bold, so the large-text bar of 3:1 applies)
    assert ratio("#FFFFFF", pal["primary"]) >= 3.0


def test_live_switch_recolours_everything():
    lab, btn = QLabel(), QPushButton()
    theme.apply(app, "light")
    theme.set_glyph(lab, "check", "primary_text", 20)
    theme.set_glyph(btn, "send", "text", 18)
    before = lab.pixmap().toImage().pixelColor(10, 10).name(), btn.icon().pixmap(18, 18).toImage().pixelColor(9, 9).name()
    light_css = app.styleSheet()
    assert theme.MODE["dark"] is False and theme.C["bg"] == theme.LIGHT["bg"]

    fired = []
    theme.signals.changed.connect(lambda: fired.append(1))
    theme.apply(app, "dark")
    assert theme.MODE["dark"] is True and theme.C["bg"] == theme.DARK["bg"] and fired
    assert app.styleSheet() != light_css and theme.DARK["bg"].lower() in app.styleSheet().lower()
    parent = QLabel()
    lab.setParent(parent)
    btn.setParent(parent)
    theme.refresh_glyphs(parent)
    assert theme.C["primary_text"] == theme.DARK["primary_text"]
    assert lab.property("glyphRole") == "primary_text"

    theme.apply(app, "light")                                # and back again
    assert theme.MODE["dark"] is False and app.styleSheet() == light_css


def test_explicit_modes_ignore_windows_setting():
    assert theme.apply(app, "dark") is True
    assert theme.apply(app, "light") is False
    assert theme.apply(app, "nonsense") in (True, False)     # unknown value falls back to following the system
    theme.apply(app, "light")


def test_no_hard_coded_colours_outside_the_theme():
    """New screens must use theme tokens, or dark mode would show light patches."""
    root = Path(__file__).resolve().parents[1] / "autosend"
    allowed = {"#8696A0", "#111B21"}                         # preview placeholder grey; dark QR modules (must stay dark on white)
    offenders = []
    for f in root.rglob("*.py"):
        if f.name == "theme.py":
            continue
        text = f.read_text(encoding="utf-8")
        for m in re.finditer(r"#[0-9A-Fa-f]{6}\b", text):
            if m.group(0).upper() not in allowed and m.group(0).upper() != "#FFFFFF":
                offenders.append(f"{f.name}: {m.group(0)}")
        if "setStyleSheet(" in text and f.name != "main.py":
            offenders.append(f"{f.name}: setStyleSheet")
    assert not offenders, offenders
