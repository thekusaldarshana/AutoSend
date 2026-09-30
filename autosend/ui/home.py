"""Send screen: readiness checklist, start button, and the live progress view."""
from __future__ import annotations

import os
import time
from datetime import datetime, timedelta

from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (QComboBox, QDialog, QHBoxLayout, QLabel, QListWidget, QProgressBar, QStackedWidget,
                               QVBoxLayout, QWidget)

from ..core import antiban
from ..core.phone import pretty_phone
from ..core.templating import render, used_names
from ..core.waformat import to_html
from ..core.whatsapp import CONNECTED
from ..services import AppContext
from . import theme
from .link import LinkDialog
from .widgets import Banner, Card, Page, Pill, button, hline, label

STATE_PILL = {"running": ("Sending", "ok"), "paused": ("Paused", "warn"), "waiting": ("Waiting", "info"),
              "finished": ("Finished", "ok"), "stopped": ("Stopped", "warn"), "idle": ("Ready", "mute")}


class ConfirmSend(QDialog):
    def __init__(self, parent, n: int, tname: str, sample_text: str, image_path: str, est: float,
                 shared_numbers: int, no_wa: int, audience: str = ""):
        super().__init__(parent)
        self.setWindowTitle("Ready to send?")
        self.setMinimumWidth(560)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(26, 24, 26, 20)
        lay.setSpacing(12)
        lay.addWidget(label(f"Send to {n} parent{'s' if n != 1 else ''}?", "h2"))
        facts = ([f"To: {audience}"] if audience else []) + [
                 f"Message: “{tname}”" + ("  ·  with a photo" if image_path else ""),
                 f"About {antiban.human_duration(est)} to finish. Keep this computer on and connected to the internet.",
                 "AutoSend spaces messages out like a person would, with short random pauses and occasional breaks."]
        if image_path and len(sample_text) > 1000:
            facts.append("This message is long, so the photo is sent first and the text follows as a second message.")
        if shared_numbers:
            facts.append(f"{shared_numbers} number(s) belong to more than one student and will get one message per student.")
        if no_wa:
            facts.append(f"{no_wa} number(s) were already found not to be on WhatsApp and will be skipped.")
        for f in facts:
            lay.addWidget(label("•  " + f, "muted", wrap=True))
        lay.addWidget(label("First message will look like this:", "h3"))
        b = QLabel(to_html(sample_text))
        b.setObjectName("bubble")
        b.setWordWrap(True)
        b.setTextFormat(Qt.RichText)
        b.setFont(theme.mono_message_font(10.5))
        holder = QWidget()
        holder.setObjectName("chatHolder")
        holder.setAttribute(Qt.WA_StyledBackground, True)
        hl = QVBoxLayout(holder)
        hl.setContentsMargins(14, 14, 14, 14)
        if image_path:
            pic = QLabel()
            pm = QPixmap(image_path)
            if not pm.isNull():
                pic.setPixmap(pm.scaledToWidth(min(280, pm.width()), Qt.SmoothTransformation))
                hl.addWidget(pic, 0, Qt.AlignTop | Qt.AlignLeft)
        hl.addWidget(b, 0, Qt.AlignTop | Qt.AlignLeft)
        hl.addStretch(1)
        from PySide6.QtWidgets import QScrollArea
        sc = QScrollArea()
        sc.setWidgetResizable(True)
        sc.setWidget(holder)
        sc.setMaximumHeight(320)
        lay.addWidget(sc)
        row = QHBoxLayout()
        row.addStretch(1)
        no = button("Cancel")
        no.clicked.connect(self.reject)
        yes = button(f"Send {n} message{'s' if n != 1 else ''}", "primary", "send")
        yes.clicked.connect(self.accept)
        row.addWidget(no)
        row.addWidget(yes)
        lay.addLayout(row)


class HomePage(Page):
    def __init__(self, ctx: AppContext, toast, goto):
        super().__init__("Send", "Check everything is ready, then press Start.")
        self.ctx, self.toast, self.goto = ctx, toast, goto
        self.cid: int | None = None
        self._actions: dict = {}
        self.stack = QStackedWidget()
        self.root.addWidget(self.stack, 1)
        self.stack.addWidget(self._build_idle())
        self.stack.addWidget(self._build_run())

        s = ctx.sender
        s.stateChanged.connect(self._on_state)
        s.progress.connect(self._on_progress)
        s.countdown.connect(self._on_countdown)
        s.activity.connect(self._on_activity)
        ctx.rosterUpdated.connect(lambda _d: self.refresh())
        ctx.rosterProblem.connect(lambda _m: self.refresh())
        ctx.settingsChanged.connect(self.refresh)
        ctx.variablesChanged.connect(self.refresh)
        ctx.wa.stateChanged.connect(lambda *_: self.refresh())

    # ------------------------------------------------------------ idle view
    def _build_idle(self) -> QWidget:
        w = QWidget()
        v = QVBoxLayout(w)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(16)

        self.resume_banner = Banner("", "info", "clock", "Resume")
        self.resume_banner.clicked.connect(self.resume_run)
        self.resume_banner.setVisible(False)
        v.addWidget(self.resume_banner)

        stats = QHBoxLayout()
        stats.setSpacing(14)
        self.stat_students = self._stat("Students in Excel")
        self.stat_ready = self._stat("Will receive a message")
        self.stat_time = self._stat("Estimated time")
        for c in (self.stat_students, self.stat_ready, self.stat_time):
            stats.addWidget(c[0])
        v.addLayout(stats)

        chk = Card(pad=20, spacing=6)
        chk.body.addWidget(label("Before you send", "h2"))
        self.items = []
        for key, title in (("excel", "Student list"), ("wa", "WhatsApp"), ("msg", "Message")):
            row = QHBoxLayout()
            row.setSpacing(12)
            ic = QLabel()
            ic.setFixedWidth(24)
            t = QVBoxLayout()
            t.setSpacing(0)
            head = label(title, "h3")
            sub = label("", "muted")
            t.addWidget(head)
            t.addWidget(sub)
            act = button("", "link")
            act.clicked.connect(lambda _=False, k=key: self._run_action(k))
            row.addWidget(ic)
            row.addLayout(t, 1)
            row.addWidget(act)
            chk.body.addLayout(row)
            if key != "msg":
                chk.body.addWidget(hline())
            self.items.append((key, ic, sub, act))
        v.addWidget(chk)

        go = Card(pad=22)
        pick = QHBoxLayout()
        pick.setSpacing(12)
        col_a = QVBoxLayout()
        col_a.setSpacing(4)
        col_a.addWidget(label("Send to", "h3"))
        self.aud = QComboBox()
        self.aud.setMinimumWidth(260)
        col_a.addWidget(self.aud)
        col_m = QVBoxLayout()
        col_m.setSpacing(4)
        col_m.addWidget(label("Message", "h3"))
        self.msg_combo = QComboBox()
        self.msg_combo.setMinimumWidth(260)
        col_m.addWidget(self.msg_combo)
        pick.addLayout(col_a)
        pick.addLayout(col_m)
        pick.addStretch(1)
        go.body.addLayout(pick)
        go.body.addWidget(hline())
        row = QHBoxLayout()
        col = QVBoxLayout()
        self.go_title = label("", "h2")
        self.go_sub = label("", "muted", wrap=True)
        col.addWidget(self.go_title)
        col.addWidget(self.go_sub)
        row.addLayout(col, 1)
        self.quick_btn = button("Quick send", "", "message", "lg", tip="Type a message and send it right away. Not saved as a template.")
        self.quick_btn.clicked.connect(self.quick_send)
        row.addWidget(self.quick_btn)
        self.start_btn = button("Start sending", "primary", "send", "lg")
        self.start_btn.clicked.connect(self.start_new)
        row.addWidget(self.start_btn)
        go.body.addLayout(row)
        v.addWidget(go)
        v.addStretch(1)
        self.aud.activated.connect(self._audience_picked)
        self.msg_combo.activated.connect(self._message_picked)
        return w

    def _stat(self, title: str):
        c = Card(pad=18, spacing=2)
        val = label("–", "stat")
        c.body.addWidget(label(title, "muted"))
        c.body.addWidget(val)
        return c, val

    # ------------------------------------------------------------- run view
    def _build_run(self) -> QWidget:
        c = Card(pad=24, spacing=14)
        top = QHBoxLayout()
        self.run_title = label("Sending messages", "h2")
        self.state_pill = Pill("Sending", "ok")
        top.addWidget(self.run_title)
        top.addWidget(self.state_pill)
        top.addStretch(1)
        c.body.addLayout(top)

        self.big = label("0 of 0", "big")
        c.body.addWidget(self.big)
        self.bar = QProgressBar()
        self.bar.setTextVisible(False)
        self.bar.setFixedHeight(12)
        c.body.addWidget(self.bar)
        self.eta = label("", "muted")
        c.body.addWidget(self.eta)
        self.count_lbl = label("", "muted")
        c.body.addWidget(self.count_lbl)
        self.msg_banner = Banner("", "info")
        self.msg_banner.setVisible(False)
        c.body.addWidget(self.msg_banner)

        btns = QHBoxLayout()
        self.pause_btn = button("Pause", "", "pause")
        self.pause_btn.clicked.connect(self.toggle_pause)
        self.stop_btn = button("Stop", "danger", "stop")
        self.stop_btn.clicked.connect(self.stop_run)
        self.retry_btn = button("Retry failed", "", "refresh")
        self.retry_btn.clicked.connect(self.retry_failed)
        self.hist_btn = button("View details", "", "history")
        self.hist_btn.clicked.connect(lambda: self.goto("history"))
        self.new_btn = button("Back to start", "primary")
        self.new_btn.clicked.connect(self.back_to_idle)
        for b in (self.pause_btn, self.stop_btn, self.retry_btn, self.hist_btn, self.new_btn):
            btns.addWidget(b)
        btns.addStretch(1)
        c.body.addLayout(btns)

        c.body.addWidget(hline())
        c.body.addWidget(label("Live activity", "h3"))
        self.log = QListWidget()
        self.log.setMinimumHeight(140)
        c.body.addWidget(self.log, 1)
        return c

    # ------------------------------------------------------------- readiness
    def on_show(self):
        self.refresh()

    def _template(self):
        tid = self.msg_combo.currentData() if self.msg_combo.count() else None
        t = self.ctx.db.get_template(tid) if tid else None
        return t or (self.ctx.db.list_templates() or [None])[0]

    def _audience_list(self) -> dict | None:
        lid = self.aud.currentData() if self.aud.count() else 0
        return self.ctx.db.get_list(lid) if lid else None

    def recipients(self) -> list:
        lst = self._audience_list()
        if lst is None:
            return [p for p in self.ctx.recipients() if p.kind == "student" and p.selected and p.sendable]
        return [p for p in self.ctx.people_in(lst) if p.sendable]

    def _audience_label(self) -> str:
        lst = self._audience_list()
        return f"list “{lst['name']}”" if lst else "students ticked on the Students screen"

    def _audience_picked(self, *_):
        lst = self._audience_list()
        self.ctx.db.set("audience", lst["id"] if lst else 0)
        self.refresh()

    def _message_picked(self, *_):
        self.ctx.db.set("send_template", self.msg_combo.currentData())
        self.refresh()

    def _fill_pickers(self):
        want = self.ctx.db.get("audience", 0) or 0
        self.aud.blockSignals(True)
        self.aud.clear()
        n_sel = sum(1 for p in self.ctx.recipients() if p.kind == "student" and p.selected and p.sendable)
        self.aud.addItem(f"Students I ticked ({n_sel})", 0)
        everyone = self.ctx.recipients()
        for l in self.ctx.db.list_lists():
            n = sum(1 for p in self.ctx.people_in(l, everyone) if p.sendable)
            self.aud.addItem(f"{'⚡ ' if l['kind'] == 'smart' else ''}{l['name']} ({n})", l["id"])
        idx = self.aud.findData(want)
        self.aud.setCurrentIndex(max(0, idx))
        self.aud.blockSignals(False)

        keep = self.msg_combo.currentData()
        self.msg_combo.blockSignals(True)
        self.msg_combo.clear()
        for t in self.ctx.db.list_templates():
            self.msg_combo.addItem(t["name"], t["id"])
        chosen = self.ctx.db.get("send_template")
        pick = next((x for x in (chosen, keep, self.ctx.db.get("active_template"))
                     if x is not None and self.msg_combo.findData(x) >= 0), None)
        self.msg_combo.setCurrentIndex(max(0, self.msg_combo.findData(pick)))
        self.msg_combo.blockSignals(False)

    def refresh(self):
        if self.ctx.sender.active or self.stack.currentIndex() == 1:
            return
        self._fill_pickers()
        students = self.ctx.students()
        rec = self.recipients()
        pace = self.ctx.pace()
        self.stat_students[1].setText(str(len(students)))
        self.stat_ready[1].setText(str(len(rec)))
        self.stat_time[1].setText(antiban.human_duration(antiban.estimate_seconds(pace, len(rec))) if rec else "–")

        t = self._template()
        vs = {v.name.lower() for v in self.ctx.variables()}
        unknown = [n for n in used_names(t["body"]) if n.lower() not in vs] if t else []

        state = {}
        # excel
        if not self.ctx.excel_path:
            state["excel"] = (False, "No Excel file chosen yet.", "Choose file", lambda: self.goto("students"))
        elif self.ctx.problem:
            state["excel"] = (False, self.ctx.problem, "Open", lambda: self.goto("students"))
        else:
            state["excel"] = (True, f"{os.path.basename(self.ctx.excel_path)}: {len(students)} students", "View", lambda: self.goto("students"))
        # whatsapp
        if self.ctx.wa.state == CONNECTED:
            state["wa"] = (True, "Linked as " + (pretty_phone(self.ctx.wa.my_number) or "your WhatsApp"), "", None)
        else:
            state["wa"] = (False, "Not linked yet. Scan a code with your phone.", "Link WhatsApp", self.link_wa)
        # message
        if not t or not t["body"].strip():
            state["msg"] = (False, "Your message is empty.", "Write message", lambda: self.goto("message"))
        elif unknown:
            state["msg"] = (False, "Contains an unknown detail: " + ", ".join("{" + u + "}" for u in unknown), "Fix", lambda: self.goto("message"))
        else:
            state["msg"] = (True, f"“{t['name']}”" + ("  ·  with photo" if t["image_path"] else ""), "Edit", lambda: self.goto("message"))

        all_ok = True
        for key, ic, sub, act in self.items:
            ok, text, act_text, fn = state[key]
            all_ok &= ok
            theme.set_glyph(ic, "check" if ok else "warn", "primary" if ok else "warn", 20)
            sub.setText(text)
            act.setText(act_text)
            act.setVisible(bool(act_text))
            self._actions[key] = fn

        open_c = self.ctx.db.open_campaign()
        if open_c:
            c = self.ctx.db.counts(open_c["id"])
            self.resume_banner.set(f"You have an unfinished run: {c['sent']} of {c['total']} already sent. "
                                   "Resume it and no one will get a message twice.", "info", "clock")
            self.resume_banner.action.setText("Resume")
            self.resume_banner.setVisible(True)
        else:
            self.resume_banner.setVisible(False)

        can = all_ok and len(rec) > 0
        self.start_btn.setEnabled(can)
        self.quick_btn.setEnabled(bool(state["excel"][0] and state["wa"][0] and rec))
        self.start_btn.setText("Start a new run" if open_c else "Start sending")
        if not all_ok:
            self.go_title.setText("Almost there")
            self.go_sub.setText("Finish the steps above and the Start button will light up.")
        elif not rec:
            self.go_title.setText("No one is selected")
            self.go_sub.setText("Nobody in this group has a usable WhatsApp number yet. Pick a different group, or tick students on the Students screen.")
        else:
            self.go_title.setText(f"Ready to message {len(rec)} parent{'s' if len(rec) != 1 else ''}")
            self.go_sub.setText("You can pause or stop at any time. Progress is saved.")

    def _run_action(self, key: str):
        fn = self._actions.get(key)
        if fn:
            fn()

    def link_wa(self):
        LinkDialog(self.ctx, self).exec()
        self.refresh()

    # --------------------------------------------------------------- actions
    def start_new(self):
        rec = self.recipients()
        t = self._template()
        if not rec or not t:
            return
        vs = self.ctx.variables()
        first = render(t["body"], vs, rec[0].values)
        phones = [p.phone for p in rec]
        shared = len(phones) - len(set(phones))
        no_wa = sum(1 for p in rec if p.wa_state == "no")
        est = antiban.estimate_seconds(self.ctx.pace(), len(rec) - no_wa)
        dlg = ConfirmSend(self, len(rec), t["name"], first.text, t["image_path"], est, shared, no_wa,
                          self._audience_label())
        if dlg.exec() != QDialog.Accepted:
            return
        self.ctx.db.close_stale_campaigns()
        lst = self._audience_list()
        cname = t["name"] + (f"  →  {lst['name']}" if lst else "")
        cid = self.ctx.db.create_campaign(cname, t["body"], t["image_path"], [(p.ref, p.label, p.phone, p.group) for p in rec])
        self._begin(cid)

    def quick_send(self):
        rec = self.recipients()
        if not rec:
            return
        from .quicksend import QuickSendDialog
        dlg = QuickSendDialog(self.ctx, rec, self._audience_label(), self)
        if dlg.exec() != QDialog.Accepted:
            return
        self.ctx.db.close_stale_campaigns()
        lst = self._audience_list()
        cname = "Quick message" + (f"  →  {lst['name']}" if lst else "")
        cid = self.ctx.db.create_campaign(cname, dlg.text, dlg.image_path, [(p.ref, p.label, p.phone, p.group) for p in rec])
        self._begin(cid)

    def resume_run(self):
        c = self.ctx.db.open_campaign()
        if c:
            self._begin(c["id"])

    def _begin(self, cid: int):
        if not self.ctx.wa.ready:
            self.link_wa()
            if not self.ctx.wa.ready:
                return
        self.cid = cid
        self.log.clear()
        self.stack.setCurrentIndex(1)
        self._set_run_buttons("running")
        self.run_title.setText("Sending messages")
        self.msg_banner.setVisible(False)
        self._on_progress(cid, self.ctx.db.counts(cid))
        self.ctx.sender.start(cid)

    def toggle_pause(self):
        if self.ctx.sender.state == "paused":
            self.ctx.sender.resume()
        else:
            self.ctx.sender.pause()

    def stop_run(self):
        from PySide6.QtWidgets import QMessageBox
        if QMessageBox.question(self, "Stop sending", "Stop now? Messages already sent stay sent, and you can resume later.",
                                QMessageBox.Yes | QMessageBox.No, QMessageBox.No) == QMessageBox.Yes:
            self.ctx.sender.stop()

    def retry_failed(self):
        if self.cid and self.ctx.db.requeue(self.cid, ("failed",)):
            self._begin(self.cid)

    def back_to_idle(self):
        self.stack.setCurrentIndex(0)
        self.refresh()

    # ---------------------------------------------------------- live updates
    def _set_run_buttons(self, state: str):
        active = state in ("running", "paused", "waiting")
        self.pause_btn.setVisible(active)
        self.stop_btn.setVisible(active)
        self.retry_btn.setVisible(not active and bool(self.cid) and self.ctx.db.counts(self.cid)["failed"] > 0)
        self.hist_btn.setVisible(not active)
        self.new_btn.setVisible(not active)
        self.pause_btn.setText("Resume" if state == "paused" else "Pause")
        theme.set_glyph(self.pause_btn, "play" if state == "paused" else "pause", "text", 18)

    def _on_state(self, state: str, msg: str):
        text, kind = STATE_PILL.get(state, ("", "mute"))
        self.state_pill.set(text, kind)
        self._set_run_buttons(state)
        if state in ("finished", "stopped"):
            self.eta.setText("")
            c = self.ctx.db.counts(self.cid) if self.cid else {}
            self.run_title.setText("All done" if state == "finished" else "Stopped")
            if self.cid:
                self._on_progress(self.cid, c)
        if msg:
            kindb = "ok" if state == "finished" else "warn" if state in ("stopped", "paused", "waiting") else "info"
            self.msg_banner.set(msg, kindb)
            self.msg_banner.setVisible(True)
        else:
            self.msg_banner.setVisible(False)
        if state in ("finished", "stopped"):
            self.ctx.settingsChanged.emit()

    def _on_progress(self, cid: int, c: dict):
        if cid != self.cid:
            return
        total = max(1, c.get("total", 0))
        done = c.get("total", 0) - c.get("pending", 0)
        self.big.setText(f"{done} of {c.get('total', 0)}")
        self.bar.setMaximum(total)
        self.bar.setValue(done)
        self.count_lbl.setText(f"✓ {c.get('sent', 0)} sent     ✗ {c.get('failed', 0)} failed     "
                               f"↷ {c.get('skipped', 0)} skipped     ⏳ {c.get('pending', 0)} waiting")
        pending = c.get("pending", 0)
        if pending and self.ctx.sender.state in ("running", "waiting", "paused"):
            secs = antiban.estimate_seconds(self.ctx.pace(), pending)
            fin = datetime.now() + timedelta(seconds=secs)
            self.eta.setText(f"About {antiban.human_duration(secs)} left  ·  finishing around {fin.strftime('%H:%M')}")

    def _on_countdown(self, lbl: str, secs: int):
        if self.ctx.sender.state == "running":
            m, s = divmod(secs, 60)
            self.msg_banner.set(f"{lbl} {m} min {s:02d} s" if m else f"{lbl} {s} s", "info", "clock")
            self.msg_banner.setVisible(True)

    def _on_activity(self, text: str):
        self.log.insertItem(0, f"{time.strftime('%H:%M:%S')}   {text}")
        while self.log.count() > 200:
            self.log.takeItem(self.log.count() - 1)
