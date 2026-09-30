"""Quick send: type a message and send it. Nothing is saved to Templates."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (QDialog, QFileDialog, QFrame, QHBoxLayout, QLabel, QPlainTextEdit, QVBoxLayout, QWidget)

from ..core import antiban
from ..core.media import IMAGE_TYPES, import_image
from ..core.templating import render, used_names
from ..core.waformat import to_html
from ..services import AppContext
from . import theme
from .message import VarHighlighter
from .widgets import Banner, FlowLayout, button, label


class QuickSendDialog(QDialog):
    def __init__(self, ctx: AppContext, people: list, audience_label: str, parent=None):
        super().__init__(parent)
        self.ctx, self.people = ctx, people
        self.text = ""
        self.image_path = ctx.quick_draft.get("image", "")
        if self.image_path and not Path(self.image_path).exists():
            self.image_path = ""
        self.setWindowTitle("Quick send")
        self.setMinimumSize(980, 640)

        root = QVBoxLayout(self)
        root.setContentsMargins(26, 22, 26, 20)
        root.setSpacing(12)
        root.addWidget(label("Quick send", "h1"))
        root.addWidget(label(f"To {audience_label}: {len(people)} {'person' if len(people) == 1 else 'people'}.  "
                             "Type your message and send it. It is not saved as a template.", "muted", wrap=True))

        body = QHBoxLayout()
        body.setSpacing(20)
        root.addLayout(body, 1)

        # ---- left: editor
        left = QVBoxLayout()
        left.setSpacing(8)
        body.addLayout(left, 3)
        self.editor = QPlainTextEdit()
        self.editor.setFont(theme.mono_message_font(11.5))
        self.editor.setPlaceholderText("Type your message here…")
        self.editor.setTabChangesFocus(True)
        self.editor.setPlainText(ctx.quick_draft.get("text", ""))
        self.hl = VarHighlighter(self.editor.document(), lambda: {v.name.lower() for v in self.ctx.variables()})
        left.addWidget(self.editor, 1)
        left.addWidget(label("Add student details  —  click to insert", "h3"))
        host = QWidget()
        chips = FlowLayout(host)
        for v in ctx.variables():
            b = button("{" + v.name + "}")
            b.setProperty("chip", True)
            b.clicked.connect(lambda _=False, n=v.name: self._insert(n))
            chips.addWidget(b)
        left.addWidget(host)
        photo = QHBoxLayout()
        self.thumb = QLabel()
        self.thumb.setFixedSize(40, 40)
        self.thumb.setScaledContents(True)
        self.photo_lbl = label("Photo (optional)", "muted")
        self.add_photo = button("Add photo", "", "photo")
        self.rm_photo = button("Remove", "ghost", "cancel")
        self.add_photo.clicked.connect(self._pick)
        self.rm_photo.clicked.connect(lambda: self._set_image(""))
        for w in (self.thumb, self.photo_lbl):
            photo.addWidget(w)
        photo.addStretch(1)
        photo.addWidget(self.add_photo)
        photo.addWidget(self.rm_photo)
        left.addLayout(photo)

        # ---- right: preview
        right = QVBoxLayout()
        right.setSpacing(8)
        body.addLayout(right, 2)
        self.prev_title = label("Preview", "h3")
        right.addWidget(self.prev_title)
        self.phone = QFrame()
        self.phone.setObjectName("phone")
        pl = QVBoxLayout(self.phone)
        pl.setContentsMargins(14, 14, 14, 14)
        self.pic = QLabel()
        self.pic.setAlignment(Qt.AlignCenter)
        pl.addWidget(self.pic)
        self.bubble = QLabel()
        self.bubble.setObjectName("bubble")
        self.bubble.setWordWrap(True)
        self.bubble.setTextFormat(Qt.RichText)
        self.bubble.setFont(theme.mono_message_font(10.5))
        self.bubble.setAlignment(Qt.AlignLeft | Qt.AlignTop)
        pl.addWidget(self.bubble, 0, Qt.AlignTop)
        pl.addStretch(1)
        right.addWidget(self.phone, 1)
        self.warn = Banner("", "warn")
        right.addWidget(self.warn)

        # ---- footer
        foot = QHBoxLayout()
        self.est = label("", "muted")
        foot.addWidget(self.est, 1)
        cancel = button("Cancel")
        cancel.clicked.connect(self.reject)
        self.send = button("", "primary", "send", "lg")
        self.send.clicked.connect(self._accept)
        foot.addWidget(cancel)
        foot.addWidget(self.send)
        root.addLayout(foot)

        self.editor.textChanged.connect(self._changed)
        self._show_image()
        self._changed()
        self.editor.setFocus()

    # ---------------------------------------------------------------- editing
    def _insert(self, name: str):
        c = self.editor.textCursor()
        c.insertText("{" + name + "}")
        self.editor.setTextCursor(c)
        self.editor.setFocus()

    def _pick(self):
        p, _ = QFileDialog.getOpenFileName(self, "Choose a photo", "", IMAGE_TYPES)
        if p:
            self._set_image(import_image(p))

    def _set_image(self, path: str):
        self.image_path = path
        self._show_image()
        self._changed()

    def _show_image(self):
        has = bool(self.image_path)
        self.thumb.setVisible(has)
        self.rm_photo.setVisible(has)
        self.add_photo.setText("Change photo" if has else "Add photo")
        self.photo_lbl.setText(Path(self.image_path).name if has else "Photo (optional)")
        if has:
            self.thumb.setPixmap(QPixmap(self.image_path))

    # ---------------------------------------------------------------- checks
    def _changed(self):
        body = self.editor.toPlainText()
        self.ctx.quick_draft = {"text": body, "image": self.image_path}
        vs = self.ctx.variables()
        first = self.people[0]
        res = render(body, vs, first.values)
        self.prev_title.setText(f"Preview for {first.label}")
        self.bubble.setText(to_html(res.text) if body.strip() else f"<span style='color:#8696A0'>Your message will appear here…</span>")
        if self.image_path:
            self.pic.setPixmap(QPixmap(self.image_path).scaledToWidth(240, Qt.SmoothTransformation))
            self.pic.setVisible(True)
        else:
            self.pic.setVisible(False)

        known = {v.name.lower() for v in vs}
        unknown = [n for n in used_names(body) if n.lower() not in known]
        empties: dict[str, int] = {}
        if not unknown:
            for p in self.people:
                for m in render(body, vs, p.values).missing:
                    empties[m] = empties.get(m, 0) + 1
        problem = ""
        if unknown:
            problem = "Not a known detail: " + ", ".join("{" + u + "}" for u in unknown) + ". Check the spelling."
            self.warn.set(problem, "bad")
        elif empties:
            self.warn.set("; ".join(f"{n} people have an empty {{{v}}}" for v, n in empties.items()) + ". They will be skipped.", "warn")
        self.warn.setVisible(bool(unknown or empties))
        n = len(self.people)
        est = antiban.estimate_seconds(self.ctx.pace(), n)
        self.est.setText(f"About {antiban.human_duration(est)} to finish. Keep this computer on.")
        self.send.setText(f"Send {n} message{'s' if n != 1 else ''}")
        self.send.setEnabled(bool(body.strip()) and not unknown)
        if len(res.text) > 1000 and self.image_path:
            self.est.setText(self.est.text() + "  The photo goes first, then the text.")

    def _accept(self):
        self.text = self.editor.toPlainText().strip()
        if not self.text:
            return
        self.ctx.quick_draft = {"text": "", "image": ""}          # sent: forget the draft
        self.accept()
