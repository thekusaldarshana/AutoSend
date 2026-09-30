"""Settings: kept simple. Changes save the moment you make them."""
from __future__ import annotations

import os

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QCheckBox, QComboBox, QFileDialog, QGridLayout, QHBoxLayout, QLineEdit, QMessageBox,
                               QScrollArea, QSpinBox, QVBoxLayout, QWidget)

from .. import __version__
from ..core import paths
from ..core.antiban import PRESET_LABELS, PRESETS, Pace, estimate_seconds, human_duration, preset_name
from ..core.phone import pretty_phone
from ..core.whatsapp import CONNECTED
from ..services import AppContext
from . import theme
from .link import LinkDialog
from .widgets import Banner, Card, ChoiceCard, Page, Pill, button, hline, label

AUTO = "(detect automatically)"


class SettingsPage(Page):
    def __init__(self, ctx: AppContext, toast):
        super().__init__("Settings", "Everything here saves automatically.")
        self.ctx, self.toast = ctx, toast
        self._building = True
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.NoFrame)
        host = QWidget()
        host.setObjectName("page")
        col = QVBoxLayout(host)
        col.setContentsMargins(0, 0, 8, 0)
        col.setSpacing(16)
        scroll.setWidget(host)
        self.root.addWidget(scroll, 1)

        # ---- student list
        c1 = Card()
        c1.body.addWidget(label("Student list", "h2"))
        row = QHBoxLayout()
        self.path_lbl = label("", "muted", wrap=True)
        b_change = button("Change file…", "", "folder")
        b_open = button("Open in Excel", "", "excel")
        b_change.clicked.connect(self._change_excel)
        b_open.clicked.connect(lambda: self.ctx.excel_path and os.startfile(self.ctx.excel_path))
        row.addWidget(self.path_lbl, 1)
        row.addWidget(b_change)
        row.addWidget(b_open)
        c1.body.addLayout(row)
        g = QGridLayout()
        g.setHorizontalSpacing(14)
        g.setVerticalSpacing(8)
        self.phone_col = QComboBox()
        self.key_col = QComboBox()
        self.cc = QLineEdit()
        self.cc.setMaximumWidth(90)
        g.addWidget(label("WhatsApp number column"), 0, 0)
        g.addWidget(self.phone_col, 0, 1)
        g.addWidget(label("Student ID column"), 1, 0)
        g.addWidget(self.key_col, 1, 1)
        g.addWidget(label("Country code for numbers without one"), 2, 0)
        g.addWidget(self.cc, 2, 1, Qt.AlignLeft)
        g.setColumnStretch(1, 1)
        c1.body.addLayout(g)
        c1.body.addWidget(label("The student ID column tells AutoSend which row is which, so it still knows who was messaged "
                                "after you edit or re-order the Excel file.", "faint", wrap=True))
        col.addWidget(c1)

        # ---- appearance
        c_ap = Card()
        c_ap.body.addWidget(label("Appearance", "h2"))
        ar = QHBoxLayout()
        ar.setSpacing(12)
        self.themes = {}
        for key, title, desc in (("system", "Follow Windows", "Matches your computer's light or dark setting."),
                                 ("light", "Light", "Bright and clean."),
                                 ("dark", "Dark", "Easier on the eyes in the evening.")):
            card = ChoiceCard(key, title, desc, self._pick_theme)
            self.themes[key] = card
            ar.addWidget(card)
        c_ap.body.addLayout(ar)
        col.addWidget(c_ap)

        # ---- whatsapp
        c2 = Card()
        c2.body.addWidget(label("WhatsApp", "h2"))
        row = QHBoxLayout()
        self.wa_pill = Pill("", "mute")
        self.wa_lbl = label("", "muted")
        self.wa_link = button("Link / re-link", "", "link")
        self.wa_off = button("Disconnect", "danger")
        self.wa_link.clicked.connect(self._link)
        self.wa_off.clicked.connect(self._disconnect)
        row.addWidget(self.wa_pill)
        row.addWidget(self.wa_lbl, 1)
        row.addWidget(self.wa_link)
        row.addWidget(self.wa_off)
        c2.body.addLayout(row)
        col.addWidget(c2)

        # ---- speed
        c3 = Card()
        c3.body.addWidget(label("Sending speed", "h2"))
        c3.body.addWidget(label("AutoSend never sends at a steady beat. Every pause is random, and it takes longer breaks "
                                "between random-sized batches, like a person would.", "muted", wrap=True))
        pr = QHBoxLayout()
        pr.setSpacing(12)
        self.presets = {k: ChoiceCard(k, PRESET_LABELS[k][0], PRESET_LABELS[k][1], self._pick_preset) for k in PRESETS}
        for p in self.presets.values():
            pr.addWidget(p)
        c3.body.addLayout(pr)
        self.estimate = label("", "muted")
        c3.body.addWidget(self.estimate)
        self.adv_btn = button("Fine-tune ▾", "link")
        self.adv_btn.clicked.connect(self._toggle_adv)
        c3.body.addWidget(self.adv_btn, 0, Qt.AlignLeft)
        self.adv = QWidget()
        ag = QGridLayout(self.adv)
        ag.setContentsMargins(0, 0, 0, 0)
        ag.setHorizontalSpacing(10)
        ag.setVerticalSpacing(8)
        self.sp = {}

        def spin(key, lo, hi):
            s = QSpinBox()
            s.setRange(lo, hi)
            s.setMaximumWidth(90)
            s.valueChanged.connect(self._adv_changed)
            self.sp[key] = s
            return s

        ag.addWidget(label("Pause between messages (seconds)"), 0, 0)
        ag.addWidget(spin("gap_min", 1, 600), 0, 1)
        ag.addWidget(label("to"), 0, 2)
        ag.addWidget(spin("gap_max", 1, 900), 0, 3)
        ag.addWidget(label("Messages before a break"), 1, 0)
        ag.addWidget(spin("batch_min", 1, 500), 1, 1)
        ag.addWidget(label("to"), 1, 2)
        ag.addWidget(spin("batch_max", 1, 500), 1, 3)
        ag.addWidget(label("Break length (minutes)"), 2, 0)
        ag.addWidget(spin("break_min", 0, 240), 2, 1)
        ag.addWidget(label("to"), 2, 2)
        ag.addWidget(spin("break_max", 0, 240), 2, 3)
        ag.setColumnStretch(4, 1)
        self.typing = QCheckBox("Show “typing…” before each message")
        self.typing.toggled.connect(self._adv_changed)
        ag.addWidget(self.typing, 3, 0, 1, 4)
        self.cap_on = QCheckBox("Daily limit")
        self.cap = spin("daily_cap", 1, 5000)
        self.cap_on.toggled.connect(self._adv_changed)
        ag.addWidget(self.cap_on, 4, 0)
        ag.addWidget(self.cap, 4, 1)
        ag.addWidget(label("messages per day"), 4, 2, 1, 2)
        self.win_on = QCheckBox("Only send between")
        self.h1 = spin("window_start", 0, 23)
        self.h2 = spin("window_end", 1, 24)
        self.win_on.toggled.connect(self._adv_changed)
        ag.addWidget(self.win_on, 5, 0)
        ag.addWidget(self.h1, 5, 1)
        ag.addWidget(label("and"), 5, 2)
        ag.addWidget(self.h2, 5, 3)
        ag.addWidget(label("o'clock (24-hour)", "faint"), 5, 4)
        self.adv.setVisible(False)
        c3.body.addWidget(self.adv)
        col.addWidget(c3)

        # ---- about
        c4 = Card()
        c4.body.addWidget(label("About", "h2"))
        c4.body.addWidget(label(f"AutoSend {__version__}", "muted"))
        row = QHBoxLayout()
        b1 = button("Open data folder", "", "folder")
        b2 = button("Open error log", "", "info")
        b3 = button("Typing test", "", "edit", tip="See exactly which characters your keyboard sends. Useful if a letter looks wrong.")
        b3.clicked.connect(lambda: __import__("autosend.ui.typingtest", fromlist=["x"]).TypingTestDialog(self).exec())
        b1.clicked.connect(lambda: os.startfile(str(paths.data_dir())))
        b2.clicked.connect(lambda: os.startfile(str(paths.log_dir())))
        row.addWidget(b1)
        row.addWidget(b2)
        row.addWidget(b3)
        row.addStretch(1)
        c4.body.addLayout(row)
        col.addWidget(c4)
        col.addStretch(1)

        self.phone_col.activated.connect(self._cols_changed)
        self.key_col.activated.connect(self._cols_changed)
        self.cc.editingFinished.connect(self._cc_changed)
        ctx.wa.stateChanged.connect(lambda *_: self._wa())
        ctx.rosterUpdated.connect(lambda _d: self._fill())
        self._building = False

    def on_show(self):
        self._fill()
        self._wa()

    def _fill(self):
        self._building = True
        ctx = self.ctx
        self.path_lbl.setText(ctx.excel_path or "No file chosen")
        for combo, current in ((self.phone_col, ctx.phone_col), (self.key_col, ctx.key_col)):
            combo.clear()
            combo.addItem(AUTO)
            combo.addItems(ctx.columns)
            saved = ctx.db.get("phone_col" if combo is self.phone_col else "key_col") or ""
            combo.setCurrentIndex(max(0, combo.findText(saved)) if saved else 0)
        self.cc.setText(ctx.default_cc)
        mode = ctx.db.get("theme_mode", "system")
        for k, card in self.themes.items():
            card.set_active(k == mode)
        pace = ctx.pace()
        name = preset_name(pace)
        for k, p in self.presets.items():
            p.set_active(k == name)
        for key, s in self.sp.items():
            if key in ("daily_cap",):
                s.setValue(int(pace.daily_cap) or 100)
            else:
                s.setValue(int(getattr(pace, key)))
        self.typing.setChecked(pace.typing)
        self.cap_on.setChecked(pace.daily_cap > 0)
        self.win_on.setChecked(pace.window_on)
        self.cap.setEnabled(pace.daily_cap > 0)
        self.h1.setEnabled(pace.window_on)
        self.h2.setEnabled(pace.window_on)
        self.estimate.setText(f"At this speed, 100 messages take about {human_duration(estimate_seconds(pace, 100))}."
                              + ("" if name != "custom" else "  (custom settings)"))
        self._building = False

    def _wa(self):
        st = self.ctx.wa.state
        if st == CONNECTED:
            self.wa_pill.set("Connected", "ok")
            self.wa_lbl.setText(pretty_phone(self.ctx.wa.my_number))
        elif st == "need_qr":
            self.wa_pill.set("Not linked", "warn")
            self.wa_lbl.setText("Scan a code with your phone to link.")
        else:
            self.wa_pill.set("Connecting…" if st in ("starting", "reconnecting") else "Offline", "mute")
            self.wa_lbl.setText(self.ctx.wa.detail if st == "error" else "")
        self.wa_off.setVisible(st == CONNECTED)

    # ------------------------------------------------------------- handlers
    def _change_excel(self):
        start = os.path.dirname(self.ctx.excel_path) if self.ctx.excel_path else ""
        p, _ = QFileDialog.getOpenFileName(self, "Choose your Excel file", start, "Excel files (*.xlsx *.xlsm)")
        if p:
            self.ctx.set_excel_path(p)
            self._fill()
            self.toast.show_message("Excel file changed")

    def _cols_changed(self):
        if self._building:
            return
        pc = "" if self.phone_col.currentText() == AUTO else self.phone_col.currentText()
        kc = "" if self.key_col.currentText() == AUTO else self.key_col.currentText()
        self.ctx.set_column_override(kc, pc)
        self.toast.show_message("Saved")

    def _cc_changed(self):
        if self._building:
            return
        digits = "".join(ch for ch in self.cc.text() if ch.isdigit()) or "94"
        if digits != self.ctx.default_cc:
            self.ctx.db.set("country_code", digits)
            self.ctx.reload(force=True)
            self.toast.show_message("Saved")
        self.cc.setText(digits)

    def _pick_theme(self, key: str):
        from PySide6.QtWidgets import QApplication
        self.ctx.db.set("theme_mode", key)
        theme.apply(QApplication.instance(), key)
        self._fill()
        self.toast.show_message({"system": "Following your Windows setting", "light": "Light mode", "dark": "Dark mode"}[key])

    def _pick_preset(self, key: str):
        old = self.ctx.pace()
        p = Pace.from_dict({**PRESETS[key], "typing": old.typing, "daily_cap": old.daily_cap,
                            "window_on": old.window_on, "window_start": old.window_start, "window_end": old.window_end})
        self.ctx.set_pace(p)
        self._fill()
        self.toast.show_message(f"{PRESET_LABELS[key][0]} speed selected")

    def _toggle_adv(self):
        self.adv.setVisible(not self.adv.isVisible())
        self.adv_btn.setText("Fine-tune ▴" if self.adv.isVisible() else "Fine-tune ▾")

    def _adv_changed(self, *_):
        if self._building:
            return
        d = {k: s.value() for k, s in self.sp.items() if k != "daily_cap"}
        d["gap_max"] = max(d["gap_max"], d["gap_min"])
        d["batch_max"] = max(d["batch_max"], d["batch_min"])
        d["break_max"] = max(d["break_max"], d["break_min"])
        d.update(typing=self.typing.isChecked(), daily_cap=self.cap.value() if self.cap_on.isChecked() else 0,
                 window_on=self.win_on.isChecked())
        self.ctx.set_pace(Pace.from_dict(d))
        self._fill()

    def _link(self):
        if self.ctx.wa.state == CONNECTED:
            if QMessageBox.question(self, "Re-link", "Link a different WhatsApp account? The current one will be disconnected.",
                                    QMessageBox.Yes | QMessageBox.No, QMessageBox.No) != QMessageBox.Yes:
                return
            self.ctx.wa.relink()
        LinkDialog(self.ctx, self).exec()

    def _disconnect(self):
        if QMessageBox.question(self, "Disconnect", "Disconnect WhatsApp from AutoSend? You can link it again any time.",
                                QMessageBox.Yes | QMessageBox.No, QMessageBox.No) == QMessageBox.Yes:
            self.ctx.wa.logout()
            self.toast.show_message("Disconnected")
