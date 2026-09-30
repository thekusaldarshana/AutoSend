"""Message screen: write exactly what parents will read, drop in variables, see a live preview."""
from __future__ import annotations

import time
from pathlib import Path

from PySide6.QtCore import QRegularExpression, Qt, QTimer
from PySide6.QtGui import (QColor, QFont, QPixmap, QSyntaxHighlighter, QTextCharFormat, QTextCursor)
from PySide6.QtWidgets import (QComboBox, QDialog, QFileDialog, QFrame, QHBoxLayout, QInputDialog, QLabel, QMenu,
                               QMessageBox, QPlainTextEdit, QScrollArea, QToolButton, QVBoxLayout, QWidget)

from ..core.media import IMAGE_TYPES, import_image
from ..core.templating import VAR_RE, render, used_names
from ..core.waformat import to_html
from ..services import AppContext
from . import theme
from .bg import run_async
from .variables import VariableDialog
from .widgets import Banner, Card, FlowLayout, Page, button, label

STARTER = ("Hello,\n\nThis is a friendly reminder that the outstanding balance for {Name} "
           "({Class}, Admission No. {Admission}) is Rs. {Amount}.\n\nThank you.")


class VarHighlighter(QSyntaxHighlighter):
    def __init__(self, doc, known_fn):
        super().__init__(doc)
        self.known_fn = known_fn
        self.re = QRegularExpression(r"\{[^{}\n]{1,40}\}")

    def highlightBlock(self, text: str):
        known = self.known_fn()
        it = self.re.globalMatch(text)
        while it.hasNext():
            m = it.next()
            name = m.captured(0)[1:-1].strip().lower()
            fmt = QTextCharFormat()
            ok = name in known
            fmt.setBackground(QColor(theme.C["primary_soft"] if ok else theme.C["danger_soft"]))
            fmt.setForeground(QColor(theme.C["primary_text"] if ok else theme.C["danger"]))
            fmt.setFontWeight(QFont.Bold)
            self.setFormat(m.capturedStart(), m.capturedLength(), fmt)


class MessagePage(Page):
    def __init__(self, ctx: AppContext, toast, goto=None):
        super().__init__("Message", "Write it exactly as you want parents to see it. Line breaks and spacing are kept.")
        self.ctx, self.toast, self.goto = ctx, toast, goto
        self.tid: int | None = None
        self.image_path = ""
        self._loading = False

        if goto:
            back = button("All templates", "", "back")
            back.clicked.connect(lambda: self.goto("templates"))
            self.header.actions.addWidget(back)

        body = QHBoxLayout()
        body.setSpacing(18)
        self.root.addLayout(body, 1)

        # ------------------------------------------------ left: editor
        left = Card(pad=18, spacing=12)
        body.addWidget(left, 3)

        top = QHBoxLayout()
        top.setSpacing(8)
        self.combo = QComboBox()
        self.combo.setMinimumWidth(240)
        top.addWidget(self.combo, 1)
        self.more = button("", "ghost", "chevron", tip="Message options")
        theme.set_glyph(self.more, "settings", "muted", 18)
        menu = QMenu(self)
        menu.addAction("New message…", self.new_template)
        menu.addAction("Rename…", self.rename_template)
        menu.addAction("Duplicate", self.duplicate_template)
        menu.addSeparator()
        menu.addAction("Delete", self.delete_template)
        self.more.setMenu(menu)
        top.addWidget(self.more)
        self.saved = label("", "faint")
        top.addWidget(self.saved)
        left.body.addLayout(top)

        fmt = QHBoxLayout()
        fmt.setSpacing(4)
        for glyph, mark, tip in (("bold", "*", "Bold  (*text*)"), ("italic", "_", "Italic  (_text_)"),
                                 ("strike", "~", "Strikethrough  (~text~)")):
            tb = QToolButton()
            theme.set_glyph(tb, glyph, "text", 18)
            tb.setToolTip(tip)
            tb.clicked.connect(lambda _=False, m=mark: self.wrap(m))
            fmt.addWidget(tb)
        fmt.addSpacing(8)
        fmt.addWidget(label("Tip: press Windows + . (period) to add emoji.", "faint"))
        fmt.addStretch(1)
        self.counter = label("", "faint")
        fmt.addWidget(self.counter)
        left.body.addLayout(fmt)

        self.editor = QPlainTextEdit()
        self.editor.setFont(theme.mono_message_font(11.5))
        self.editor.setPlaceholderText("Type your message here…")
        self.editor.setTabChangesFocus(True)
        self.editor.setMinimumHeight(260)
        self.hl = VarHighlighter(self.editor.document(), lambda: {v.name.lower() for v in self.ctx.variables()})
        left.body.addWidget(self.editor, 1)

        left.body.addWidget(label("Add student details  —  click to insert", "h3"))
        chips_host = QWidget()
        self.chips = FlowLayout(chips_host)
        left.body.addWidget(chips_host)

        # photo row
        photo = QHBoxLayout()
        photo.setSpacing(10)
        self.thumb = QLabel()
        self.thumb.setFixedSize(46, 46)
        self.thumb.setScaledContents(True)
        self.thumb.setVisible(False)
        self.photo_name = label("Photo (optional): send a picture together with the message.", "muted", wrap=True)
        self.photo_btn = button("Add photo", "", "photo")
        self.photo_rm = button("Remove", "ghost", "cancel")
        self.photo_btn.clicked.connect(self.pick_image)
        self.photo_rm.clicked.connect(lambda: self.set_image(""))
        photo.addWidget(self.thumb)
        photo.addWidget(self.photo_name, 1)
        photo.addWidget(self.photo_btn)
        photo.addWidget(self.photo_rm)
        left.body.addLayout(photo)

        # ------------------------------------------------ right: preview
        right = QVBoxLayout()
        right.setSpacing(12)
        body.addLayout(right, 2)
        prev = Card(pad=18, spacing=10)
        right.addWidget(prev)
        prev.body.addWidget(label("Preview", "h2"))
        self.who = QComboBox()
        prev.body.addWidget(self.who)

        self.phone = QFrame()
        self.phone.setObjectName("phone")
        pl = QVBoxLayout(self.phone)
        pl.setContentsMargins(14, 14, 14, 14)
        self.pic = QLabel()
        self.pic.setAlignment(Qt.AlignCenter)
        self.pic.setVisible(False)
        pl.addWidget(self.pic)
        self.bubble = QLabel()
        self.bubble.setObjectName("bubble")
        self.bubble.setWordWrap(True)
        self.bubble.setTextFormat(Qt.RichText)
        self.bubble.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.bubble.setFont(theme.mono_message_font(10.5))
        self.bubble.setAlignment(Qt.AlignLeft | Qt.AlignTop)
        pl.addWidget(self.bubble, 0, Qt.AlignTop)
        pl.addStretch(1)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(self.phone)
        scroll.setMinimumHeight(260)
        scroll.setFrameShape(QFrame.NoFrame)
        prev.body.addWidget(scroll, 1)

        self.warn = Banner("", "warn")
        self.warn.setVisible(False)
        prev.body.addWidget(self.warn)
        self.test_btn = button("Send a test to my phone", "", "send")
        self.test_btn.clicked.connect(self.send_test)
        prev.body.addWidget(self.test_btn)

        # ------------------------------------------------ wiring
        self.combo.activated.connect(self._combo_changed)
        self.editor.textChanged.connect(self._text_changed)
        self.who.currentIndexChanged.connect(self.update_preview)
        self._save_t = QTimer(self)
        self._save_t.setSingleShot(True)
        self._save_t.setInterval(600)
        self._save_t.timeout.connect(self.save_now)
        self._prev_t = QTimer(self)
        self._prev_t.setSingleShot(True)
        self._prev_t.setInterval(120)
        self._prev_t.timeout.connect(self.update_preview)
        ctx.variablesChanged.connect(self._vars_changed)
        theme.signals.changed.connect(self.on_theme_changed)
        ctx.rosterUpdated.connect(lambda _d: self._fill_students())
        ctx.settingsChanged.connect(self._sched_preview)
        ctx.wa.stateChanged.connect(lambda *_: self._wa_changed())

        self._ensure_template()
        self._fill_templates()
        self._rebuild_chips()
        self._fill_students()
        self._wa_changed()

    # ------------------------------------------------------------- templates
    def _ensure_template(self):
        if not self.ctx.db.list_templates():
            tid = self.ctx.db.save_template(None, "Fee reminder", STARTER, "")
            self.ctx.db.set("active_template", tid)

    def _fill_templates(self):
        ts = self.ctx.db.list_templates()
        active = self.ctx.db.get("active_template")
        self.combo.blockSignals(True)
        self.combo.clear()
        for t in ts:
            self.combo.addItem(t["name"], t["id"])
        idx = next((i for i, t in enumerate(ts) if t["id"] == active), 0)
        self.combo.setCurrentIndex(idx)
        self.combo.blockSignals(False)
        self._load(ts[idx]["id"])

    def _load(self, tid: int):
        t = self.ctx.db.get_template(tid)
        if not t:
            return
        self._loading = True
        self.tid = tid
        self.ctx.db.set("active_template", tid)
        self.editor.setPlainText(t["body"])
        self.image_path = t["image_path"] if t["image_path"] and Path(t["image_path"]).exists() else ""
        self._loading = False
        self._show_image()
        self.update_preview()
        self.saved.setText("")

    def open_template(self, tid: int):
        """Show a specific template in the editor (used by the Templates page)."""
        self.save_now()
        self.ctx.db.set("active_template", tid)
        self._fill_templates()
        self.editor.setFocus()

    def _combo_changed(self, _i):
        self.save_now()
        self._load(self.combo.currentData())
        self.ctx.settingsChanged.emit()

    def new_template(self):
        name, ok = QInputDialog.getText(self, "New message", "Name for this message:", text="New message")
        if ok and name.strip():
            self.save_now()
            tid = self.ctx.db.save_template(None, name.strip(), "", "")
            self.ctx.db.set("active_template", tid)
            self._fill_templates()
            self.editor.setFocus()

    def rename_template(self):
        cur = self.combo.currentText()
        name, ok = QInputDialog.getText(self, "Rename message", "New name:", text=cur)
        if ok and name.strip() and self.tid:
            t = self.ctx.db.get_template(self.tid)
            self.ctx.db.save_template(self.tid, name.strip(), t["body"], t["image_path"])
            self._fill_templates()

    def duplicate_template(self):
        if not self.tid:
            return
        self.save_now()
        t = self.ctx.db.get_template(self.tid)
        tid = self.ctx.db.save_template(None, t["name"] + " (copy)", t["body"], t["image_path"])
        self.ctx.db.set("active_template", tid)
        self._fill_templates()
        self.toast.show_message("Message duplicated")

    def delete_template(self):
        ts = self.ctx.db.list_templates()
        if len(ts) <= 1:
            QMessageBox.information(self, "Delete message", "You need at least one message. Edit this one instead.")
            return
        if QMessageBox.question(self, "Delete message", f"Delete “{self.combo.currentText()}”?",
                                QMessageBox.Yes | QMessageBox.No, QMessageBox.No) == QMessageBox.Yes:
            self.ctx.db.delete_template(self.tid)
            self.ctx.db.set("active_template", next(t["id"] for t in ts if t["id"] != self.tid))
            self._fill_templates()
            self.toast.show_message("Message deleted")

    # ------------------------------------------------------------- editing
    def _text_changed(self):
        if self._loading:
            return
        self.saved.setText("Saving…")
        self._save_t.start()
        self._prev_t.start()
        n = len(self.editor.toPlainText())
        self.counter.setText(f"{n} characters")

    def save_now(self):
        if self.tid is None:
            return
        t = self.ctx.db.get_template(self.tid)
        if not t:
            return
        self.ctx.db.save_template(self.tid, t["name"], self.editor.toPlainText(), self.image_path)
        self.saved.setText("Saved ✓")
        self.ctx.settingsChanged.emit()

    def body(self) -> str:
        return self.editor.toPlainText()

    def wrap(self, mark: str):
        c = self.editor.textCursor()
        if c.hasSelection():
            txt = c.selectedText().replace(" ", "\n")
            c.insertText(f"{mark}{txt}{mark}")
        else:
            c.insertText(mark + mark)
            c.movePosition(QTextCursor.Left)
            self.editor.setTextCursor(c)
        self.editor.setFocus()

    def insert_variable(self, name: str):
        c = self.editor.textCursor()
        c.insertText("{" + name + "}")
        self.editor.setTextCursor(c)
        self.editor.setFocus()

    # ---------------------------------------------------------- variable chips
    def _rebuild_chips(self):
        self.chips.clear()
        for v in self.ctx.variables():
            b = button("{" + v.name + "}")
            b.setProperty("chip", True)
            b.setToolTip(f"Insert {{{v.name}}} at the cursor")
            b.clicked.connect(lambda _=False, n=v.name: self.insert_variable(n))
            self.chips.addWidget(b)
        add = button("+ New detail", "link")
        add.clicked.connect(self._new_var)
        self.chips.addWidget(add)
        self.chips.invalidate()

    def _new_var(self):
        dlg = VariableDialog(self.ctx, None, self)
        if dlg.exec() == QDialog.Accepted:
            self.ctx.db.save_variable(dlg.result_var)
            self.ctx.variablesChanged.emit()
            self.insert_variable(dlg.result_var.name)

    def _vars_changed(self):
        self._rebuild_chips()
        self.hl.rehighlight()
        # names may have been rewritten in stored templates
        if self.tid:
            t = self.ctx.db.get_template(self.tid)
            if t and t["body"] != self.editor.toPlainText():
                self._loading = True
                self.editor.setPlainText(t["body"])
                self._loading = False
        self.update_preview()

    # ---------------------------------------------------------------- photo
    def pick_image(self):
        p, _ = QFileDialog.getOpenFileName(self, "Choose a photo", "", IMAGE_TYPES)
        if not p:
            return
        self.set_image(import_image(p))

    def set_image(self, path: str):
        self.image_path = path
        self._show_image()
        self.save_now()
        self.update_preview()

    def _show_image(self):
        has = bool(self.image_path)
        self.thumb.setVisible(has)
        self.photo_rm.setVisible(has)
        self.photo_btn.setText("Change photo" if has else "Add photo")
        if has:
            self.thumb.setPixmap(QPixmap(self.image_path))
            self.photo_name.setText(Path(self.image_path).name + "  ·  will be sent with the message")
        else:
            self.photo_name.setText("Photo (optional): send a picture together with the message.")

    # -------------------------------------------------------------- preview
    def _fill_students(self):
        rows = self.ctx.students()
        rows = [s for s in rows if s["phone"]] or rows
        cur = self.who.currentData()
        self.who.blockSignals(True)
        self.who.clear()
        for s in rows:
            self.who.addItem(self.ctx.display_name(s), s["key"])
        i = self.who.findData(cur)
        self.who.setCurrentIndex(max(0, i))
        self.who.blockSignals(False)
        self.update_preview()

    def _sched_preview(self):
        self._prev_t.start()

    def current_student(self) -> dict | None:
        key = self.who.currentData()
        return self.ctx.db.get_student(key) if key else None

    def update_preview(self):
        body = self.editor.toPlainText()
        s = self.current_student()
        vs = self.ctx.variables()
        res = render(body, vs, s["values"] if s else {})
        shown = res.text if body.strip() else "Your message will appear here…"
        self.bubble.setText(to_html(shown) if body.strip() else f"<span style='color:#8696A0'>{shown}</span>")
        if self.image_path:
            pm = QPixmap(self.image_path)
            self.pic.setPixmap(pm.scaledToWidth(260, Qt.SmoothTransformation))
            self.pic.setVisible(True)
        else:
            self.pic.setVisible(False)
        self.counter.setText(f"{len(body)} characters")
        self._update_warning(body, vs)

    def _update_warning(self, body: str, vs):
        known = {v.name.lower() for v in vs}
        unknown = [n for n in used_names(body) if n.lower() not in known]
        if unknown:
            self.warn.set("Not a known detail: " + ", ".join("{" + u + "}" for u in unknown)
                          + ". Check the spelling, or create it under Variables. Sending is blocked until this is fixed.", "bad")
            self.warn.setVisible(True)
            return
        empties: dict[str, list[str]] = {}
        for st in self.ctx.students():
            if not (st["selected"] and st["phone"]):
                continue
            r = render(body, vs, st["values"])
            for m in r.missing:
                empties.setdefault(m, []).append(self.ctx.display_name(st))
        if empties:
            parts = []
            for var, names in empties.items():
                eg = ", ".join(names[:2]) + ("…" if len(names) > 2 else "")
                parts.append(f"{len(names)} student(s) have an empty {{{var}}} ({eg})")
            self.warn.set("; ".join(parts) + ". They will be skipped.", "warn")
            self.warn.setVisible(True)
            return
        self.warn.setVisible(False)

    # ----------------------------------------------------------------- test
    def _wa_changed(self):
        self.test_btn.setEnabled(self.ctx.wa.ready)
        self.test_btn.setToolTip("" if self.ctx.wa.ready else "Link WhatsApp first")

    def send_test(self):
        s = self.current_student()
        res = render(self.body(), self.ctx.variables(), s["values"] if s else {})
        if not res.text:
            self.toast.show_message("Type a message first")
            return
        if res.unknown:
            self.toast.show_message("Fix the unknown details first")
            return
        text, image = res.text, self.image_path
        self.test_btn.setEnabled(False)
        self.test_btn.setText("Sending…")

        def work():
            jid = self.ctx.wa.own_jid()
            if image and len(text) <= 1000:
                self.ctx.wa.send_image(jid, image, text)
            elif image:
                self.ctx.wa.send_image(jid, image, None)
                time.sleep(1.5)
                self.ctx.wa.send_text(jid, text)
            else:
                self.ctx.wa.send_text(jid, text)

        def done(_r, err):
            self.test_btn.setText("Send a test to my phone")
            self._wa_changed()
            if err:
                self.toast.show_message("Could not send the test. Is WhatsApp connected?")
            else:
                self.toast.show_message("Test sent. Check “Message yourself” in WhatsApp")

        run_async(work, done)

    def on_theme_changed(self):
        self.hl.rehighlight()
        self.update_preview()

    def on_show(self):
        self._fill_students()
        self._rebuild_chips()
        self._wa_changed()
        QTimer.singleShot(0, self.editor.setFocus)          # ready to type as soon as the page opens
