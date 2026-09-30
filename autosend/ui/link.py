"""Linking WhatsApp (QR code) and the first-run welcome guide."""
from __future__ import annotations

import os
import shutil

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (QDialog, QFileDialog, QHBoxLayout, QLabel, QStackedWidget, QVBoxLayout, QWidget)

from ..core import paths
from ..core.excel import write_starter_workbook
from ..core.phone import pretty_phone
from ..core.whatsapp import CONNECTED, ERROR, IDLE, LOGGED_OUT, NEED_QR, STARTING
from ..services import AppContext
from . import theme
from .widgets import Banner, button, label


class LinkPanel(QWidget):
    """Steps + QR code. Emits nothing; watches the WhatsApp service and updates itself."""

    def __init__(self, ctx: AppContext, on_connected=None):
        super().__init__()
        self.ctx = ctx
        self._on_connected = on_connected
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(28)

        steps = QVBoxLayout()
        steps.setSpacing(14)
        steps.addWidget(label("Link your WhatsApp", "h2"))
        for n, t in enumerate((
            "Open WhatsApp on your phone.",
            "Tap the ⋮ menu (Android) or Settings (iPhone), then Linked devices.",
            "Tap “Link a device” and point your phone at the code on this screen.",
        ), 1):
            row = QHBoxLayout()
            row.setSpacing(12)
            badge = QLabel(str(n))
            badge.setFixedSize(28, 28)
            badge.setAlignment(Qt.AlignCenter)
            badge.setObjectName("stepBadge")
            txt = label(t, wrap=True)
            row.addWidget(badge, 0, Qt.AlignTop)
            row.addWidget(txt, 1)
            steps.addLayout(row)
        steps.addSpacing(6)
        self.status = Banner("Getting ready…", "info")
        steps.addWidget(self.status)
        steps.addStretch(1)
        lay.addLayout(steps, 1)

        self.qr_box = QLabel()
        self.qr_box.setFixedSize(280, 280)
        self.qr_box.setAlignment(Qt.AlignCenter)
        self.qr_box.setObjectName("qrBox")
        lay.addWidget(self.qr_box, 0, Qt.AlignTop)

        ctx.wa.qrReady.connect(self._qr)
        ctx.wa.stateChanged.connect(self._state)
        self._state(ctx.wa.state, ctx.wa.detail)
        if ctx.wa.last_qr:
            self._qr(ctx.wa.last_qr)

    def showEvent(self, e):
        super().showEvent(e)
        if self.ctx.wa.state in (IDLE, ERROR):
            self.ctx.wa.start()
        elif self.ctx.wa.state == LOGGED_OUT:
            self.ctx.wa.relink()

    def _qr_state(self, state: str):
        self.qr_box.setProperty("state", state)
        self.qr_box.style().unpolish(self.qr_box)
        self.qr_box.style().polish(self.qr_box)

    def _qr(self, png: bytes):
        pm = QPixmap()
        pm.loadFromData(png)
        self.qr_box.setPixmap(pm.scaled(256, 256, Qt.KeepAspectRatio, Qt.FastTransformation))

    def _state(self, state: str, detail: str):
        if state == CONNECTED:
            self.qr_box.clear()
            self.qr_box.setText("✓")
            self._qr_state("ok")
            self.status.set(f"Connected as {pretty_phone(detail) or 'your WhatsApp'}. You're all set.", "ok")
            if self._on_connected:
                QTimer.singleShot(900, self._on_connected)
        elif state == NEED_QR:
            self._qr_state("")
            self.status.set("Waiting for you to scan the code. It refreshes by itself.", "info")
        elif state == ERROR:
            self.status.set(detail or "Could not connect. Check your internet connection.", "bad")
        elif state == LOGGED_OUT:
            self.status.set("WhatsApp was unlinked from the phone. A new code is on its way…", "warn")
        else:
            self.status.set("Getting ready. This takes a few seconds…", "info")


class LinkDialog(QDialog):
    def __init__(self, ctx: AppContext, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Link WhatsApp")
        self.setMinimumWidth(760)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(28, 26, 28, 22)
        lay.setSpacing(16)
        self.panel = LinkPanel(ctx, self.accept)
        lay.addWidget(self.panel)
        row = QHBoxLayout()
        row.addStretch(1)
        close = button("Close")
        close.clicked.connect(self.reject)
        row.addWidget(close)
        lay.addLayout(row)


class WelcomeWizard(QDialog):
    """Three friendly steps: pick the student file, link WhatsApp, done."""

    def __init__(self, ctx: AppContext, parent=None):
        super().__init__(parent)
        self.ctx = ctx
        self.setWindowTitle("Welcome to AutoSend")
        self.setMinimumSize(820, 520)
        self.setModal(True)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(34, 30, 34, 24)
        outer.setSpacing(14)
        self.dots = label("", "faint")
        outer.addWidget(self.dots)
        self.stack = QStackedWidget()
        outer.addWidget(self.stack, 1)
        self.nav = QHBoxLayout()
        self.skip = button("Skip for now", "ghost")
        self.skip.clicked.connect(self.next_step)
        self.nav.addStretch(1)
        self.nav.addWidget(self.skip)
        outer.addLayout(self.nav)

        # step 1: welcome + excel
        s1 = QWidget()
        l1 = QVBoxLayout(s1)
        l1.setSpacing(12)
        l1.addWidget(label("Welcome to AutoSend", "h1"))
        l1.addWidget(label("Send personal WhatsApp messages to every parent in a few clicks, straight from your Excel list. "
                           "First, tell AutoSend where your student list is.", "muted", wrap=True))
        l1.addSpacing(8)
        self.excel_state = Banner("No file chosen yet.", "info")
        l1.addWidget(self.excel_state)
        pick = button("Choose my Excel file…", "primary", "folder", "lg")
        pick.clicked.connect(self.pick_excel)
        starter = button("I don't have one yet. Create a starter file", "ghost", "excel")
        starter.clicked.connect(self.make_starter)
        l1.addWidget(pick, 0, Qt.AlignLeft)
        l1.addWidget(starter, 0, Qt.AlignLeft)
        l1.addStretch(1)
        self.stack.addWidget(s1)

        # step 2: whatsapp
        s2 = QWidget()
        l2 = QVBoxLayout(s2)
        self.link = LinkPanel(ctx, self.next_step)
        l2.addWidget(self.link)
        l2.addStretch(1)
        self.stack.addWidget(s2)

        # step 3: done
        s3 = QWidget()
        l3 = QVBoxLayout(s3)
        l3.setSpacing(12)
        l3.addWidget(label("You're all set 🎉", "h1"))
        self.done_txt = label("", "muted", wrap=True)
        l3.addWidget(self.done_txt)
        l3.addSpacing(10)
        go = button("Start using AutoSend", "primary", "send", "lg")
        go.clicked.connect(self.accept)
        l3.addWidget(go, 0, Qt.AlignLeft)
        l3.addStretch(1)
        self.stack.addWidget(s3)

        self.next_btn = button("Next", "primary")
        self.next_btn.clicked.connect(self.next_step)
        self.next_btn.setEnabled(False)
        self.nav.addWidget(self.next_btn)
        self._render()

    def _render(self):
        i = self.stack.currentIndex()
        self.dots.setText(f"Step {i + 1} of 3")
        self.skip.setVisible(i == 1)
        self.next_btn.setVisible(i == 0)
        if i == 2:
            n = len(self.ctx.students())
            self.done_txt.setText(
                (f"{n} students found in your Excel file. " if n else "") +
                ("WhatsApp is linked. " if self.ctx.wa.ready else "You can link WhatsApp later from the Send screen. ") +
                "Next, write your message and press Start sending.")

    def next_step(self):
        i = self.stack.currentIndex()
        if i < 2:
            self.stack.setCurrentIndex(i + 1)
            self._render()

    def _chosen(self, path: str):
        self.ctx.set_excel_path(path)
        n = len(self.ctx.students())
        if self.ctx.problem:
            self.excel_state.set(self.ctx.problem, "bad")
            self.next_btn.setEnabled(False)
        else:
            self.excel_state.set(f"{os.path.basename(path)}: {n} students found.", "ok")
            self.next_btn.setEnabled(True)

    def pick_excel(self):
        p, _ = QFileDialog.getOpenFileName(self, "Choose your Excel file", str(paths.documents_dir().parent),
                                           "Excel files (*.xlsx *.xlsm)")
        if p:
            self._chosen(p)

    def make_starter(self):
        d = paths.documents_dir()
        d.mkdir(parents=True, exist_ok=True)
        target = d / "Students.xlsx"
        if not target.exists():
            write_starter_workbook(str(target))
        self._chosen(str(target))
        os.startfile(str(target))
