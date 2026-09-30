"""Small reusable building blocks so every screen looks the same."""
from __future__ import annotations

from PySide6.QtCore import QEasingCurve, QPropertyAnimation, Qt, QTimer, Signal
from PySide6.QtGui import QCursor
from PySide6.QtWidgets import (QFrame, QGraphicsOpacityEffect, QHBoxLayout, QLabel, QPushButton, QSizePolicy,
                               QVBoxLayout, QWidget)

from . import theme


def label(text: str = "", kind: str = "", wrap: bool = False, selectable: bool = False) -> QLabel:
    lb = QLabel(text)
    if kind:
        lb.setObjectName(kind)
    lb.setWordWrap(wrap)
    if selectable:
        lb.setTextInteractionFlags(Qt.TextSelectableByMouse)
    return lb


def button(text: str = "", variant: str = "", icon: str | None = None, size: str = "", tip: str = "",
           icon_color: str | None = None) -> QPushButton:
    b = QPushButton(text)
    if variant:
        b.setProperty("variant", variant)
    if size:
        b.setProperty("size", size)
    if icon:
        role = icon_color or ("white" if variant == "primary" else "danger" if variant == "danger"
                              else "muted" if variant == "ghost" else "text")
        theme.set_glyph(b, icon, role, 18)
    if tip:
        b.setToolTip(tip)
    b.setCursor(QCursor(Qt.PointingHandCursor))
    return b


def repolish(w: QWidget) -> None:
    w.style().unpolish(w)
    w.style().polish(w)
    w.update()


class Card(QFrame):
    def __init__(self, pad: int = 20, spacing: int = 12, flat: bool = False):
        super().__init__()
        self.setObjectName("cardFlat" if flat else "card")
        self.body = QVBoxLayout(self)
        self.body.setContentsMargins(pad, pad, pad, pad)
        self.body.setSpacing(spacing)


class Pill(QLabel):
    def __init__(self, text: str = "", kind: str = "mute"):
        super().__init__(text)
        self.set(text, kind)
        self.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Fixed)

    def set(self, text: str, kind: str) -> None:
        self.setText(text)
        self.setProperty("pill", kind)
        repolish(self)


class Banner(QFrame):
    """Coloured message strip (info / ok / warn / bad) with optional action button."""
    clicked = Signal()

    def __init__(self, text: str = "", kind: str = "info", icon: str = "info", action: str = ""):
        super().__init__()
        self.setObjectName("banner")
        lay = QHBoxLayout(self)
        lay.setContentsMargins(14, 10, 14, 10)
        lay.setSpacing(10)
        self.icon = QLabel()
        self.text = QLabel(text)
        self.text.setWordWrap(True)
        self.text.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.action = button(action, "link")
        self.action.clicked.connect(self.clicked)
        self.action.setVisible(bool(action))
        lay.addWidget(self.icon, 0, Qt.AlignTop)
        lay.addWidget(self.text, 1)
        lay.addWidget(self.action)
        self.set(text, kind, icon)

    def set(self, text: str, kind: str = "info", icon: str | None = None) -> None:
        self.text.setText(text)
        self.setProperty("kind", kind)
        role = dict(info="info", ok="primary_text", warn="warn", bad="danger")[kind]
        glyph = icon or dict(info="info", ok="check", warn="warn", bad="warn")[kind]
        theme.set_glyph(self.icon, glyph, role, 18)
        repolish(self)


class Toast(QLabel):
    """A short-lived message that floats at the bottom of the window."""

    def __init__(self, parent: QWidget):
        super().__init__(parent)
        self.setObjectName("toast")
        self.hide()
        self._fx = QGraphicsOpacityEffect(self)
        self.setGraphicsEffect(self._fx)
        self._anim = QPropertyAnimation(self._fx, b"opacity", self)
        self._anim.setDuration(220)
        self._hiding = False
        self._anim.finished.connect(self._anim_done)
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self._fade_out)

    def show_message(self, text: str, ms: int = 3200) -> None:
        self.setText(text)
        self.adjustSize()
        p = self.parentWidget()
        self.move((p.width() - self.width()) // 2, p.height() - self.height() - 28)
        self.raise_()
        self.show()
        self._anim.stop()
        self._anim.setStartValue(0.0)
        self._anim.setEndValue(1.0)
        self._anim.setEasingCurve(QEasingCurve.OutCubic)
        self._hiding = False
        self._anim.start()
        self._timer.start(ms)

    def _fade_out(self) -> None:
        self._anim.stop()
        self._anim.setStartValue(1.0)
        self._anim.setEndValue(0.0)
        self._hiding = True
        self._anim.start()

    def _anim_done(self) -> None:
        if self._hiding:
            self.hide()


class PageHeader(QWidget):
    def __init__(self, title: str, subtitle: str = ""):
        super().__init__()
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        col = QVBoxLayout()
        col.setSpacing(2)
        self.title = label(title, "h1")
        self.subtitle = label(subtitle, "muted", wrap=True)
        col.addWidget(self.title)
        if subtitle:
            col.addWidget(self.subtitle)
        lay.addLayout(col, 1)
        self.actions = QHBoxLayout()
        self.actions.setSpacing(8)
        lay.addLayout(self.actions)


class Page(QWidget):
    """Standard page: padded column with a header."""

    def __init__(self, title: str, subtitle: str = ""):
        super().__init__()
        self.setObjectName("page")
        self.root = QVBoxLayout(self)
        self.root.setContentsMargins(32, 28, 32, 24)
        self.root.setSpacing(16)
        self.header = PageHeader(title, subtitle)
        self.root.addWidget(self.header)

    def on_show(self) -> None:
        """Called every time the page becomes visible."""


def hline() -> QFrame:
    f = QFrame()
    f.setObjectName("hr")
    f.setFixedHeight(1)
    return f


def status_kind(status: str) -> tuple[str, str]:
    return {
        "pending": ("Waiting", "mute"), "sent": ("Sent", "ok"), "failed": ("Failed", "bad"),
        "skipped": ("Skipped", "warn"), "": ("", "mute"),
    }.get(status, (status.title(), "mute"))


from PySide6.QtCore import QMargins, QPoint, QRect, QSize  # noqa: E402
from PySide6.QtWidgets import QLayout  # noqa: E402


class FlowLayout(QLayout):
    """Lays widgets left-to-right and wraps to the next line (for the variable chips)."""

    def __init__(self, parent=None, hspacing: int = 8, vspacing: int = 8):
        super().__init__(parent)
        self._items = []
        self._h, self._v = hspacing, vspacing
        self.setContentsMargins(0, 0, 0, 0)

    def addItem(self, item):
        self._items.append(item)

    def count(self):
        return len(self._items)

    def itemAt(self, i):
        return self._items[i] if 0 <= i < len(self._items) else None

    def takeAt(self, i):
        return self._items.pop(i) if 0 <= i < len(self._items) else None

    def expandingDirections(self):
        return Qt.Orientation(0)

    def hasHeightForWidth(self):
        return True

    def heightForWidth(self, w):
        return self._layout(QRect(0, 0, w, 0), True)

    def setGeometry(self, rect):
        super().setGeometry(rect)
        self._layout(rect, False)

    def sizeHint(self):
        return self.minimumSize()

    def minimumSize(self):
        s = QSize()
        for it in self._items:
            s = s.expandedTo(it.minimumSize())
        m = self.contentsMargins()
        return s + QSize(m.left() + m.right(), m.top() + m.bottom())

    def _layout(self, rect, test):
        m = self.contentsMargins()
        r = rect.adjusted(m.left(), m.top(), -m.right(), -m.bottom())
        x, y, line_h = r.x(), r.y(), 0
        for it in self._items:
            if it.widget() is not None and not it.widget().isVisible() and not it.widget().isVisibleTo(it.widget().parentWidget()):
                continue
            w, h = it.sizeHint().width(), it.sizeHint().height()
            if x + w > r.right() + 1 and line_h > 0:
                x = r.x()
                y += line_h + self._v
                line_h = 0
            if not test:
                it.setGeometry(QRect(QPoint(x, y), it.sizeHint()))
            x += w + self._h
            line_h = max(line_h, h)
        return y + line_h - rect.y() + m.bottom()

    def clear(self):
        while self._items:
            it = self._items.pop()
            if it.widget():
                it.widget().deleteLater()


class ChoiceCard(QFrame):
    """A selectable card (used for speed presets and the appearance choice)."""

    def __init__(self, key: str, title: str, desc: str, on_pick):
        super().__init__()
        self.key = key
        self.setObjectName("choiceCard")
        self._pick = on_pick
        lay = QVBoxLayout(self)
        lay.setContentsMargins(14, 12, 14, 12)
        lay.setSpacing(2)
        lay.addWidget(label(title, "h3"))
        lay.addWidget(label(desc, "muted", wrap=True))
        self.setCursor(QCursor(Qt.PointingHandCursor))
        self.set_active(False)

    def mousePressEvent(self, e):
        self._pick(self.key)

    def set_active(self, on: bool) -> None:
        self.setProperty("active", "true" if on else "false")
        repolish(self)
