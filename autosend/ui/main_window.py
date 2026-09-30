"""The main window: sidebar + pages."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (QFrame, QHBoxLayout, QLabel, QMainWindow, QMessageBox, QPushButton, QStackedWidget,
                               QVBoxLayout, QWidget)

from .. import __version__
from ..core import paths
from ..core.phone import pretty_phone
from ..core.whatsapp import CONNECTED, ERROR, LOGGED_OUT, NEED_QR
from ..services import AppContext
from . import theme
from .history import HistoryPage
from .home import HomePage
from .lists import ListsPage
from .link import LinkDialog
from .message import MessagePage
from .settings import SettingsPage
from .students import StudentsPage
from .templates import TemplatesPage
from .variables import VariablesPage
from .widgets import Toast, repolish

NAV = [("home", "Send", "send"), ("students", "Students", "students"), ("lists", "Lists", "list"),
       ("templates", "Templates", "library"), ("message", "Message", "message"),
       ("variables", "Variables", "vars"), ("history", "History", "history"), ("settings", "Settings", "settings")]


class MainWindow(QMainWindow):
    def __init__(self, ctx: AppContext):
        super().__init__()
        self.ctx = ctx
        self.setWindowTitle("AutoSend")
        self.setMinimumSize(1040, 700)
        self.resize(1240, 800)
        ico = paths.resource_path("assets/icon.ico")
        if ico.exists():
            self.setWindowIcon(QIcon(str(ico)))

        central = QWidget()
        self.setCentralWidget(central)
        root = QHBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ------------------------------------------------------------ sidebar
        side = QFrame()
        side.setObjectName("sidebar")
        side.setFixedWidth(248)
        sv = QVBoxLayout(side)
        sv.setContentsMargins(16, 22, 16, 16)
        sv.setSpacing(4)
        brand = QHBoxLayout()
        logo = QLabel()
        logo.setObjectName("logo")
        theme.set_glyph(logo, "send", "white", 22)
        logo.setFixedSize(38, 38)
        logo.setAlignment(Qt.AlignCenter)
        bt = QVBoxLayout()
        bt.setSpacing(0)
        t = QLabel("AutoSend")
        t.setObjectName("brand")
        s = QLabel("WhatsApp, automated")
        s.setObjectName("brandSub")
        bt.addWidget(t)
        bt.addWidget(s)
        brand.addWidget(logo)
        brand.addSpacing(8)
        brand.addLayout(bt)
        brand.addStretch(1)
        sv.addLayout(brand)
        sv.addSpacing(22)

        self.stack = QStackedWidget()
        self.toast = Toast(central)
        self.navs: dict[str, QPushButton] = {}
        self.pages: dict[str, QWidget] = {}
        self.pages["home"] = HomePage(ctx, self.toast, self.goto)
        self.pages["students"] = StudentsPage(ctx, self.toast)
        self.pages["lists"] = ListsPage(ctx, self.toast, self.goto)
        self.pages["message"] = MessagePage(ctx, self.toast, self.goto)
        self.pages["templates"] = TemplatesPage(ctx, self.toast, self.goto, self.open_template)
        self.pages["variables"] = VariablesPage(ctx, self.toast)
        self.pages["history"] = HistoryPage(ctx, self.toast)
        self.pages["settings"] = SettingsPage(ctx, self.toast)
        for key, text, glyph in NAV:
            b = QPushButton("  " + text)
            b.setObjectName("nav")
            b.setCheckable(True)
            b.setCursor(Qt.PointingHandCursor)
            theme.set_glyph(b, glyph, "muted", 20)
            b.clicked.connect(lambda _=False, k=key: self.goto(k))
            sv.addWidget(b)
            self.navs[key] = b
            self.stack.addWidget(self.pages[key])
        sv.addStretch(1)

        self.chip = QFrame()
        self.chip.setObjectName("waChip")
        cl = QHBoxLayout(self.chip)
        cl.setContentsMargins(12, 10, 12, 10)
        self.chip_dot = QLabel("●")
        self.chip_dot.setObjectName("chipDot")
        self.chip_text = QLabel("")
        self.chip_text.setWordWrap(True)
        cl.addWidget(self.chip_dot, 0, Qt.AlignTop)
        cl.addWidget(self.chip_text, 1)
        self.chip.setCursor(Qt.PointingHandCursor)
        self.chip.mousePressEvent = lambda e: self._chip_clicked()
        sv.addWidget(self.chip)
        ver = QLabel(f"Version {__version__}")
        ver.setObjectName("faint")
        sv.addWidget(ver)

        root.addWidget(side)
        root.addWidget(self.stack, 1)

        self._current = "home"
        theme.signals.changed.connect(self._theme_changed)
        ctx.wa.stateChanged.connect(self._wa_state)
        self._wa_state(ctx.wa.state, ctx.wa.detail)
        self.goto("home")

    # --------------------------------------------------------------- nav
    def open_template(self, tid: int):
        self.pages["message"].open_template(tid)
        self.goto("message")

    def goto(self, key: str):
        for k, b in self.navs.items():
            b.setChecked(k == key)
            theme.set_glyph(b, dict((n[0], n[2]) for n in NAV)[k], "primary_text" if k == key else "muted", 20)
        self._current = key
        page = self.pages[key]
        self.stack.setCurrentWidget(page)
        if hasattr(page, "on_show"):
            page.on_show()

    def _theme_changed(self):
        theme.refresh_glyphs(self)
        self._wa_state(self.ctx.wa.state, self.ctx.wa.detail)
        self.goto(self._current)

    # ---------------------------------------------------------- WhatsApp chip
    def _wa_state(self, state: str, detail: str):
        kind, text = "warn", "Connecting to WhatsApp…"
        if state == CONNECTED:
            kind, text = "ok", "WhatsApp connected\n" + (pretty_phone(detail) or "")
        elif state == NEED_QR:
            kind, text = "warn", "WhatsApp not linked\nClick to link"
        elif state in (ERROR, LOGGED_OUT):
            kind, text = "bad", "WhatsApp disconnected\nClick to fix"
        elif state == "reconnecting":
            text = "Reconnecting…"
        for w in (self.chip, self.chip_dot):
            w.setProperty("state", kind)
            repolish(w)
        self.chip_text.setText(text.strip())

    def _chip_clicked(self):
        if self.ctx.wa.state != CONNECTED:
            LinkDialog(self.ctx, self).exec()

    # ------------------------------------------------------------- lifecycle
    def resizeEvent(self, e):
        super().resizeEvent(e)

    def closeEvent(self, e):
        if self.ctx.sender.active and self.ctx.sender.state in ("running", "waiting"):
            r = QMessageBox.question(
                self, "Sending in progress",
                "AutoSend is still sending messages.\n\nIf you close now, sending pauses. Nobody will get a message twice "
                "and you can resume next time.\n\nClose anyway?", QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
            if r != QMessageBox.Yes:
                e.ignore()
                return
        e.accept()
