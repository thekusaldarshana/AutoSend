"""Look and feel: light + dark palettes, icons, and one stylesheet for the whole app.

Colours live in the palettes below. `apply()` switches between them at run time:
the stylesheet and Qt palette are rebuilt, and every icon that was created with `set_glyph()`
is recoloured, so nothing needs a restart.
"""
from __future__ import annotations

from PySide6.QtCore import QObject, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QFont, QIcon, QPainter, QPainterPath, QPalette, QPen, QPixmap
from PySide6.QtWidgets import QAbstractButton, QLabel, QWidget

from ..core import paths

LIGHT = dict(
    bg="#F3F5F4", surface="#FFFFFF", hover="#F3F5F4", border="#E2E8E5", border_strong="#CBD5D0", sep="#F0F3F1",
    text="#111B21", muted="#5F707A", faint="#94A3A0",
    primary="#0FA958", primary_hover="#0C9450", primary_press="#0A7F45", primary_soft="#E6F6EC",
    primary_text="#0A6B3A", primary_border="#BFE8CF", primary_disabled="#B7DFC8", chip_hover="#D5F0DF",
    danger="#CC281C", danger_soft="#FDECEA", danger_border="#F5C2BD", danger_btn_border="#F0B7B1",
    warn="#B54708", warn_soft="#FEF3E2", warn_border="#F6D9AE",
    info="#175CD3", info_soft="#E8F0FE", mute_bg="#EEF1EF", row_alt="#FAFBFA",
    chat_bg="#EFE7DD", bubble="#D9FDD3", bubble_fg="#111B21", tooltip_bg="#111B21", tooltip_fg="#FFFFFF",
)

DARK = dict(
    bg="#0F1512", surface="#17211C", hover="#1F2C25", border="#25332C", border_strong="#36463E", sep="#202C26",
    text="#E7EFEA", muted="#9AAEA3", faint="#71857A",
    primary="#0FA958", primary_hover="#14B865", primary_press="#0C9450", primary_soft="#173525",
    primary_text="#6BE3A2", primary_border="#1F5A3A", primary_disabled="#2A5A40", chip_hover="#1E4A31",
    danger="#FF8378", danger_soft="#3B1E1D", danger_border="#6B2E2A", danger_btn_border="#7A3B37",
    warn="#FDB53A", warn_soft="#382A12", warn_border="#5C4315",
    info="#82B4FF", info_soft="#15243F", mute_bg="#22302A", row_alt="#141D18",
    chat_bg="#0B141A", bubble="#005C4B", bubble_fg="#E9EDEF", tooltip_bg="#2B3B33", tooltip_fg="#E7EFEA",
)

C: dict[str, str] = dict(LIGHT)          # the live palette; every screen reads colours from here
MODE = {"dark": False}

UI_FAMILIES = ["Segoe UI Variable Text", "Segoe UI", "Noto Sans Sinhala", "Nirmala UI", "Iskoola Pota"]
ICON_FAMILIES = ["Segoe Fluent Icons", "Segoe MDL2 Assets"]

GLYPHS = dict(
    home="", students="", message="", vars="", history="", settings="",
    send="", play="", pause="", stop="", refresh="", folder="",
    photo="", add="", delete="", edit="", check="", cancel="",
    search="", link="", excel="", export="", warn="", info="",
    phone="", bold="", italic="", strike="", copy="", save="",
    contact="", list="", library="", back="", chevron="", clock="",
    emoji="", appearance="",
)


class _Signals(QObject):
    changed = Signal()


signals = _Signals()


# ------------------------------------------------------------------ fonts
def app_font(size: float = 10.0) -> QFont:
    f = QFont()
    f.setFamilies(UI_FAMILIES)
    f.setPointSizeF(size)
    return f


def mono_message_font(size: float = 11.0) -> QFont:
    f = QFont()
    f.setFamilies(["Segoe UI", "Noto Sans Sinhala", "Nirmala UI", "Iskoola Pota"])
    f.setPointSizeF(size)
    return f


# ------------------------------------------------------------------ icons
def role_color(role: str) -> str:
    return "#FFFFFF" if role == "white" else C.get(role, C["text"])


def glyph_pixmap(name: str, color: str, size: int = 18, dpr: float = 2.0) -> QPixmap:
    px = QPixmap(int(size * dpr), int(size * dpr))
    px.setDevicePixelRatio(dpr)
    px.fill(Qt.transparent)
    p = QPainter(px)
    p.setRenderHint(QPainter.TextAntialiasing)
    f = QFont()
    f.setFamilies(ICON_FAMILIES)
    f.setPixelSize(int(size * 0.92))
    p.setFont(f)
    p.setPen(QColor(color))
    p.drawText(QRectF(0, 0, size, size), Qt.AlignCenter, GLYPHS.get(name, "?"))
    p.end()
    return px


_icon_cache: dict[tuple, QIcon] = {}


def icon(name: str, color: str | None = None, size: int = 18) -> QIcon:
    color = color or C["text"]
    k = (name, color, size)
    if k not in _icon_cache:
        _icon_cache[k] = QIcon(glyph_pixmap(name, color, size))
    return _icon_cache[k]


def _apply_glyph(w: QWidget) -> None:
    name, role, size = w.property("glyph"), w.property("glyphRole") or "text", int(w.property("glyphSize") or 18)
    if not name:
        return
    color = role_color(role)
    if isinstance(w, QLabel):
        w.setPixmap(glyph_pixmap(name, color, size))
    elif isinstance(w, QAbstractButton):
        w.setIcon(icon(name, color, size))


def set_glyph(w: QWidget, name: str, role: str = "text", size: int = 18) -> None:
    """Put an icon on a button or label. `role` is a palette colour name ('text', 'muted', 'primary_text', 'white', ...).
    The icon is recoloured automatically when the theme changes."""
    w.setProperty("glyph", name)
    w.setProperty("glyphRole", role)
    w.setProperty("glyphSize", size)
    _apply_glyph(w)


def refresh_glyphs(root: QWidget) -> None:
    for w in root.findChildren(QWidget):
        if w.property("glyph"):
            _apply_glyph(w)


# ------------------------------------------------------------- checkboxes
def _make_check_assets() -> dict[str, str]:
    """Checkbox pictures for the current palette (mode-specific filenames avoid stale image caching)."""
    d = paths.sub_dir("cache")
    tag = "dark" if MODE["dark"] else "light"
    out = {}
    for name, fill, border, tick in (
        ("cb_off", C["surface"], C["border_strong"], False),
        ("cb_on", C["primary"], C["primary"], True),
        ("cb_off_hover", C["primary_soft"], C["primary"], False),
    ):
        f = d / f"{name}_{tag}.png"
        px = QPixmap(36, 36)
        px.fill(Qt.transparent)
        p = QPainter(px)
        p.setRenderHint(QPainter.Antialiasing)
        p.setPen(QPen(QColor(border), 3))
        p.setBrush(QColor(fill))
        p.drawRoundedRect(QRectF(3, 3, 30, 30), 8, 8)
        if tick:
            p.setPen(QPen(QColor("white"), 4.2, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
            path = QPainterPath()
            path.moveTo(10, 18.5)
            path.lineTo(15.5, 24)
            path.lineTo(26, 12)
            p.drawPath(path)
        p.end()
        px.save(str(f), "PNG")
        out[name] = f.as_posix()
    for name, fill, border, dot in (("rb_off", C["surface"], C["border_strong"], False),
                                    ("rb_on", C["surface"], C["primary"], True)):
        f = d / f"{name}_{tag}.png"
        px = QPixmap(36, 36)
        px.fill(Qt.transparent)
        p = QPainter(px)
        p.setRenderHint(QPainter.Antialiasing)
        p.setPen(QPen(QColor(border), 3))
        p.setBrush(QColor(fill))
        p.drawEllipse(QRectF(3, 3, 30, 30))
        if dot:
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(C["primary"]))
            p.drawEllipse(QRectF(10, 10, 16, 16))
        p.end()
        px.save(str(f), "PNG")
        out[name] = f.as_posix()
    return out


# ------------------------------------------------------------- stylesheet
def build_qss() -> str:
    a = _make_check_assets()
    c = C
    return f"""
* {{ outline: 0; }}
QWidget {{ color: {c['text']}; }}
QMainWindow, QDialog, #page {{ background: {c['bg']}; }}
QToolTip {{ background: {c['tooltip_bg']}; color: {c['tooltip_fg']}; border: 0; padding: 6px 8px; border-radius: 6px; }}

/* ---------- sidebar ---------- */
#sidebar {{ background: {c['surface']}; border-right: 1px solid {c['border']}; }}
#brand {{ font-size: 17pt; font-weight: 700; color: {c['text']}; }}
#brandSub {{ color: {c['muted']}; font-size: 9pt; }}
QLabel#logo {{ background: {c['primary']}; border-radius: 11px; }}
QPushButton#nav {{ text-align: left; padding: 11px 14px; border: 0; border-radius: 10px; background: transparent;
    color: {c['muted']}; font-size: 10.5pt; font-weight: 600; }}
QPushButton#nav:hover {{ background: {c['hover']}; color: {c['text']}; }}
QPushButton#nav:checked {{ background: {c['primary_soft']}; color: {c['primary_text']}; }}
#waChip {{ border: 1px solid {c['border']}; border-radius: 12px; background: {c['hover']}; }}
#waChip[state="ok"] {{ background: {c['primary_soft']}; border-color: {c['primary_border']}; }}
#waChip[state="warn"] {{ background: {c['warn_soft']}; border-color: {c['warn_border']}; }}
#waChip[state="bad"] {{ background: {c['danger_soft']}; border-color: {c['danger_border']}; }}
QLabel#chipDot {{ font-size: 12pt; color: {c['warn']}; }}
QLabel#chipDot[state="ok"] {{ color: {c['primary']}; }}
QLabel#chipDot[state="warn"] {{ color: {c['warn']}; }}
QLabel#chipDot[state="bad"] {{ color: {c['danger']}; }}

/* ---------- text ---------- */
QLabel {{ background: transparent; }}
QLabel#h1 {{ font-size: 20pt; font-weight: 700; }}
QLabel#h2 {{ font-size: 13pt; font-weight: 700; }}
QLabel#h3 {{ font-size: 10.5pt; font-weight: 700; }}
QLabel#muted {{ color: {c['muted']}; }}
QLabel#faint {{ color: {c['faint']}; }}
QLabel#big {{ font-size: 26pt; font-weight: 700; }}
QLabel#stat {{ font-size: 22pt; font-weight: 700; }}
QLabel[pill] {{ border-radius: 10px; padding: 3px 10px; font-weight: 600; font-size: 9pt; }}
QLabel[pill="ok"] {{ background: {c['primary_soft']}; color: {c['primary_text']}; }}
QLabel[pill="bad"] {{ background: {c['danger_soft']}; color: {c['danger']}; }}
QLabel[pill="warn"] {{ background: {c['warn_soft']}; color: {c['warn']}; }}
QLabel[pill="info"] {{ background: {c['info_soft']}; color: {c['info']}; }}
QLabel[pill="mute"] {{ background: {c['mute_bg']}; color: {c['muted']}; }}
QLabel#stepBadge {{ background: {c['primary_soft']}; color: {c['primary_text']}; border-radius: 14px; font-weight: 700; }}
QLabel#qrBox {{ background: white; border: 1px solid {c['border']}; border-radius: 16px; }}
QLabel#qrBox[state="ok"] {{ background: {c['primary_soft']}; color: {c['primary']}; font-size: 90pt;
    border: 1px solid {c['primary_border']}; }}

/* ---------- cards ---------- */
QFrame#card {{ background: {c['surface']}; border: 1px solid {c['border']}; border-radius: 14px; }}
QFrame#cardFlat {{ background: {c['surface']}; border: 1px solid {c['border']}; border-radius: 10px; }}
QFrame#choiceCard {{ background: {c['surface']}; border: 2px solid {c['border']}; border-radius: 12px; }}
QFrame#choiceCard[active="true"] {{ background: {c['primary_soft']}; border: 2px solid {c['primary']}; }}
QFrame#banner {{ border-radius: 12px; border: 1px solid {c['border']}; background: {c['info_soft']}; }}
QFrame#banner[kind="warn"] {{ background: {c['warn_soft']}; border-color: {c['warn_border']}; }}
QFrame#banner[kind="bad"] {{ background: {c['danger_soft']}; border-color: {c['danger_border']}; }}
QFrame#banner[kind="ok"] {{ background: {c['primary_soft']}; border-color: {c['primary_border']}; }}
QFrame#hr {{ background: {c['border']}; max-height: 1px; min-height: 1px; border: 0; }}
QWidget#chatHolder {{ background: {c['chat_bg']}; border-radius: 12px; }}

/* ---------- buttons ---------- */
QPushButton {{ padding: 9px 16px; border-radius: 10px; border: 1px solid {c['border_strong']};
    background: {c['surface']}; font-weight: 600; }}
QPushButton:hover {{ background: {c['hover']}; border-color: {c['faint']}; }}
QPushButton:pressed {{ background: {c['border']}; }}
QPushButton:disabled {{ color: {c['faint']}; background: {c['bg']}; border-color: {c['border']}; }}
QPushButton[variant="primary"] {{ background: {c['primary']}; color: white; border: 1px solid {c['primary']}; }}
QPushButton[variant="primary"]:hover {{ background: {c['primary_hover']}; border-color: {c['primary_hover']}; }}
QPushButton[variant="primary"]:pressed {{ background: {c['primary_press']}; }}
QPushButton[variant="primary"]:disabled {{ background: {c['primary_disabled']}; border-color: {c['primary_disabled']}; color: white; }}
QPushButton[variant="danger"] {{ background: {c['surface']}; color: {c['danger']}; border-color: {c['danger_btn_border']}; }}
QPushButton[variant="danger"]:hover {{ background: {c['danger_soft']}; }}
QPushButton[variant="ghost"] {{ border: 0; background: transparent; color: {c['muted']}; padding: 8px 10px; }}
QPushButton[variant="ghost"]:hover {{ background: {c['hover']}; color: {c['text']}; }}
QPushButton[variant="link"] {{ border: 0; background: transparent; color: {c['primary_text']}; padding: 2px 4px; }}
QPushButton[variant="link"]:hover {{ text-decoration: underline; background: transparent; }}
QPushButton[size="lg"] {{ padding: 14px 26px; font-size: 12pt; border-radius: 12px; }}
QPushButton[chip="true"] {{ padding: 5px 11px; border-radius: 14px; background: {c['primary_soft']};
    color: {c['primary_text']}; border: 1px solid {c['primary_border']}; }}
QPushButton[chip="true"]:hover {{ background: {c['chip_hover']}; }}
QToolButton {{ border: 0; padding: 7px; border-radius: 8px; background: transparent; }}
QToolButton:hover {{ background: {c['hover']}; }}
QToolButton:checked {{ background: {c['primary_soft']}; }}

/* ---------- inputs ---------- */
QLineEdit, QSpinBox, QComboBox, QDateEdit, QTimeEdit {{ padding: 9px 12px; border: 1px solid {c['border_strong']};
    border-radius: 10px; background: {c['surface']}; selection-background-color: {c['primary']}; selection-color: white; }}
QLineEdit:focus, QSpinBox:focus, QComboBox:focus, QPlainTextEdit:focus {{ border: 1.5px solid {c['primary']}; }}
QLineEdit:disabled {{ background: {c['bg']}; color: {c['faint']}; }}
QComboBox::drop-down {{ border: 0; width: 26px; }}
QComboBox QAbstractItemView {{ border: 1px solid {c['border']}; background: {c['surface']}; padding: 4px;
    selection-background-color: {c['primary_soft']}; selection-color: {c['primary_text']}; outline: 0; }}
QSpinBox::up-button, QSpinBox::down-button {{ width: 0; border: 0; }}
QPlainTextEdit, QTextEdit {{ padding: 12px; border: 1px solid {c['border_strong']}; border-radius: 12px;
    background: {c['surface']}; selection-background-color: {c['primary']}; selection-color: white; }}
QCheckBox {{ spacing: 9px; }}
QCheckBox::indicator {{ width: 18px; height: 18px; image: url({a['cb_off']}); }}
QCheckBox::indicator:hover {{ image: url({a['cb_off_hover']}); }}
QCheckBox::indicator:checked {{ image: url({a['cb_on']}); }}
QRadioButton {{ spacing: 8px; }}
QRadioButton::indicator {{ width: 18px; height: 18px; image: url({a['rb_off']}); }}
QRadioButton::indicator:checked {{ image: url({a['rb_on']}); }}

/* ---------- tables & lists ---------- */
QTableView, QTableWidget, QTreeView, QListWidget {{ background: {c['surface']}; border: 1px solid {c['border']}; border-radius: 12px;
    gridline-color: transparent; selection-background-color: {c['primary_soft']}; selection-color: {c['text']};
    alternate-background-color: {c['row_alt']}; }}
QTableView::item {{ padding: 6px 10px; border-bottom: 1px solid {c['sep']}; }}
QTableView::item:selected {{ background: {c['primary_soft']}; color: {c['text']}; }}
QTableView::indicator {{ width: 18px; height: 18px; image: url({a['cb_off']}); }}
QTableView::indicator:checked {{ image: url({a['cb_on']}); }}
QHeaderView {{ qproperty-defaultAlignment: 'AlignLeft | AlignVCenter'; background: {c['surface']}; }}
QHeaderView::section {{ background: {c['surface']}; color: {c['muted']}; padding: 10px; border: 0;
    border-bottom: 1px solid {c['border']}; font-weight: 600; }}
QTableCornerButton::section {{ background: {c['surface']}; border: 0; }}
QListWidget::item {{ padding: 10px 12px; border-radius: 8px; }}
QListWidget::item:selected {{ background: {c['primary_soft']}; color: {c['primary_text']}; }}

/* ---------- misc ---------- */
QScrollBar:vertical {{ background: transparent; width: 10px; margin: 2px; }}
QScrollBar::handle:vertical {{ background: {c['border_strong']}; border-radius: 4px; min-height: 30px; }}
QScrollBar::handle:vertical:hover {{ background: {c['faint']}; }}
QScrollBar:horizontal {{ background: transparent; height: 10px; margin: 2px; }}
QScrollBar::handle:horizontal {{ background: {c['border_strong']}; border-radius: 4px; min-width: 30px; }}
QScrollBar::add-line, QScrollBar::sub-line {{ width: 0; height: 0; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}
QScrollArea {{ border: 0; background: transparent; }}
QScrollArea > QWidget > QWidget {{ background: transparent; }}
QProgressBar {{ background: {c['border']}; border: 0; border-radius: 6px; height: 12px; text-align: center; color: transparent; }}
QProgressBar::chunk {{ background: {c['primary']}; border-radius: 6px; }}
QMenu {{ background: {c['surface']}; border: 1px solid {c['border']}; border-radius: 10px; padding: 6px; }}
QMenu::item {{ padding: 8px 18px; border-radius: 6px; }}
QMenu::item:selected {{ background: {c['primary_soft']}; color: {c['primary_text']}; }}
QMenu::separator {{ height: 1px; background: {c['border']}; margin: 4px 8px; }}
QMessageBox {{ background: {c['surface']}; }}
QTabBar::tab {{ padding: 8px 16px; border: 0; color: {c['muted']}; font-weight: 600; }}
QTabBar::tab:selected {{ color: {c['primary_text']}; border-bottom: 2px solid {c['primary']}; }}
QFrame#phone {{ background: {c['chat_bg']}; border-radius: 16px; border: 1px solid {c['border']}; }}
QLabel#bubble {{ background: {c['bubble']}; color: {c['bubble_fg']}; border-radius: 10px; padding: 10px 12px; }}
QLabel#toast {{ background: {c['tooltip_bg']}; color: {c['tooltip_fg']}; padding: 11px 18px; border-radius: 12px; font-weight: 600; }}
"""


def build_palette() -> QPalette:
    c = C
    p = QPalette()
    q = QColor
    for role, col in (
        (QPalette.Window, c["bg"]), (QPalette.WindowText, c["text"]), (QPalette.Base, c["surface"]),
        (QPalette.AlternateBase, c["row_alt"]), (QPalette.Text, c["text"]), (QPalette.Button, c["surface"]),
        (QPalette.ButtonText, c["text"]), (QPalette.Highlight, c["primary"]), (QPalette.HighlightedText, "#FFFFFF"),
        (QPalette.ToolTipBase, c["tooltip_bg"]), (QPalette.ToolTipText, c["tooltip_fg"]),
        (QPalette.PlaceholderText, c["faint"]), (QPalette.Link, c["primary_text"]), (QPalette.BrightText, "#FFFFFF"),
    ):
        p.setColor(role, q(col))
    for role in (QPalette.WindowText, QPalette.Text, QPalette.ButtonText):
        p.setColor(QPalette.Disabled, role, q(c["faint"]))
    return p


# --------------------------------------------------------------- switching
MODES = ("system", "light", "dark")


def system_is_dark(app) -> bool:
    try:
        return app.styleHints().colorScheme() == Qt.ColorScheme.Dark
    except Exception:
        return False


def apply(app, mode: str = "system") -> bool:
    """Switch the whole app to 'light', 'dark' or 'system'. Returns True if dark is now showing."""
    if mode not in MODES:
        mode = "system"
    hints = app.styleHints()
    try:                              # dark/light window title bars follow this
        hints.setColorScheme({"light": Qt.ColorScheme.Light, "dark": Qt.ColorScheme.Dark}.get(mode, Qt.ColorScheme.Unknown))
    except Exception:
        pass
    dark = mode == "dark" or (mode == "system" and system_is_dark(app))
    MODE["dark"] = dark
    C.clear()
    C.update(DARK if dark else LIGHT)
    app.setPalette(build_palette())
    app.setStyleSheet(build_qss())
    signals.changed.emit()
    return dark
