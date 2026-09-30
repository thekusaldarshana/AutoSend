"""Templates: your library of saved messages. Open one to edit it, or pick it on the Send screen."""
from __future__ import annotations

import time

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QFrame, QHBoxLayout, QInputDialog, QLineEdit, QMenu, QMessageBox, QScrollArea,
                               QVBoxLayout, QWidget)

from ..core.templating import used_names
from ..services import AppContext
from . import theme
from .widgets import Card, Page, Pill, button, label

SNIPPET_LINES = 3


def ago(ts: float | None) -> str:
    if not ts:
        return ""
    secs = max(0, time.time() - ts)
    if secs < 90:
        return "just now"
    if secs < 3600:
        return f"{int(secs // 60)} min ago"
    if secs < 86400:
        return f"{int(secs // 3600)} h ago"
    if secs < 86400 * 14:
        d = int(secs // 86400)
        return f"{d} day{'s' if d != 1 else ''} ago"
    return time.strftime("%d %b %Y", time.localtime(ts))


def snippet(body: str) -> str:
    lines = [ln.strip() for ln in body.strip().splitlines() if ln.strip()]
    if not lines:
        return "(empty)"
    out = "\n".join(lines[:SNIPPET_LINES])
    return out + ("…" if len(lines) > SNIPPET_LINES else "")


class TemplatesPage(Page):
    def __init__(self, ctx: AppContext, toast, goto, open_editor):
        super().__init__("Templates", "Your saved messages. Open one to edit it, or choose it on the Send screen.")
        self.ctx, self.toast, self.goto, self.open_editor = ctx, toast, goto, open_editor

        self.vars_btn = button("Manage variables", "", "vars")
        self.vars_btn.clicked.connect(lambda: self.goto("variables"))
        self.new_btn = button("New template", "primary", "add")
        self.new_btn.clicked.connect(self.new_template)
        self.header.actions.addWidget(self.vars_btn)
        self.header.actions.addWidget(self.new_btn)

        self.search = QLineEdit()
        self.search.setPlaceholderText("Search templates…")
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(self._filter)
        self.root.addWidget(self.search)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        host = QWidget()
        host.setObjectName("page")
        self.col = QVBoxLayout(host)
        self.col.setContentsMargins(0, 0, 8, 0)
        self.col.setSpacing(12)
        self.col.addStretch(1)
        scroll.setWidget(host)
        self.root.addWidget(scroll, 1)
        self.cards: list[tuple[QWidget, str]] = []

        ctx.variablesChanged.connect(lambda: self.isVisible() and self.refresh())

    def on_show(self):
        self.refresh()

    # ------------------------------------------------------------ building
    def refresh(self):
        for w, _ in self.cards:
            w.setParent(None)
            w.deleteLater()
        self.cards = []
        known = {v.name.lower() for v in self.ctx.variables()}
        send_id = self.ctx.db.get("send_template")
        templates = self.ctx.db.list_templates()
        templates.sort(key=lambda t: t["updated_at"] or 0, reverse=True)
        for t in templates:
            card = self._card(t, known, t["id"] == send_id)
            self.col.insertWidget(self.col.count() - 1, card)
            hay = (t["name"] + " " + t["body"]).lower()
            self.cards.append((card, hay))
        self._filter()

    def _card(self, t: dict, known: set[str], selected: bool) -> Card:
        c = Card(pad=18, spacing=8)
        top = QHBoxLayout()
        top.setSpacing(10)
        name = label(t["name"], "h2")
        top.addWidget(name)
        if selected:
            top.addWidget(Pill("Chosen on Send screen", "ok"))
        top.addStretch(1)
        edit = button("Edit", "primary", "edit")
        use = button("Use to send", "", "send")
        more = button("", "ghost", "settings", tip="More options")
        menu = QMenu(self)
        menu.addAction("Rename…", lambda tid=t["id"]: self.rename(tid))
        menu.addAction("Duplicate", lambda tid=t["id"]: self.duplicate(tid))
        menu.addSeparator()
        menu.addAction("Delete", lambda tid=t["id"]: self.delete(tid))
        more.setMenu(menu)
        edit.clicked.connect(lambda _=False, tid=t["id"]: self.open_editor(tid))
        use.clicked.connect(lambda _=False, tid=t["id"]: self.use_to_send(tid))
        for b in (edit, use, more):
            top.addWidget(b)
        c.body.addLayout(top)

        meta = [f"Edited {ago(t['updated_at'])}", f"{len(t['body'])} characters"]
        if t["image_path"]:
            meta.append("with photo")
        c.body.addWidget(label("  ·  ".join(m for m in meta if m), "faint"))

        sn = label(snippet(t["body"]), "muted", wrap=True)
        sn.setFont(theme.mono_message_font(10))
        c.body.addWidget(sn)

        names = used_names(t["body"])
        if names:
            row = QHBoxLayout()
            row.setSpacing(6)
            row.addWidget(label("Uses:", "faint"))
            for n in names[:8]:
                row.addWidget(Pill("{" + n + "}", "ok" if n.lower() in known else "bad"))
            if len(names) > 8:
                row.addWidget(label(f"+{len(names) - 8} more", "faint"))
            row.addStretch(1)
            c.body.addLayout(row)
        return c

    def _filter(self):
        q = self.search.text().strip().lower()
        for w, hay in self.cards:
            w.setVisible(not q or q in hay)

    # ------------------------------------------------------------- actions
    def _name_taken(self, name: str, own_id: int | None = None) -> bool:
        return any(t["name"].lower() == name.lower() and t["id"] != own_id for t in self.ctx.db.list_templates())

    def _ask_name(self, title: str, default: str, own_id: int | None = None) -> str | None:
        name, ok = QInputDialog.getText(self, title, "Template name:", text=default)
        name = name.strip()
        if not ok or not name:
            return None
        if self._name_taken(name, own_id):
            QMessageBox.information(self, title, f"You already have a template called “{name}”. Choose a different name.")
            return None
        return name

    def new_template(self):
        name = self._ask_name("New template", "New template")
        if name:
            tid = self.ctx.db.save_template(None, name, "", "")
            self.open_editor(tid)

    def rename(self, tid: int):
        t = self.ctx.db.get_template(tid)
        name = self._ask_name("Rename template", t["name"], tid) if t else None
        if name:
            self.ctx.db.save_template(tid, name, t["body"], t["image_path"])
            self.refresh()
            self.toast.show_message("Renamed")

    def duplicate(self, tid: int):
        t = self.ctx.db.get_template(tid)
        if not t:
            return
        base, n = t["name"] + " (copy)", 2
        name = base
        while self._name_taken(name):
            name, n = f"{base} {n}", n + 1
        self.ctx.db.save_template(None, name, t["body"], t["image_path"])
        self.refresh()
        self.toast.show_message("Template duplicated")

    def delete(self, tid: int):
        ts = self.ctx.db.list_templates()
        t = self.ctx.db.get_template(tid)
        if not t:
            return
        if len(ts) <= 1:
            QMessageBox.information(self, "Delete template", "You need at least one template. Edit this one, or create another first.")
            return
        if QMessageBox.question(self, "Delete template", f"Delete “{t['name']}”?\n\nThis can't be undone.",
                                QMessageBox.Yes | QMessageBox.No, QMessageBox.No) != QMessageBox.Yes:
            return
        self.ctx.db.delete_template(tid)
        rest = [x["id"] for x in ts if x["id"] != tid]
        if self.ctx.db.get("active_template") == tid:
            self.ctx.db.set("active_template", rest[0])
        if self.ctx.db.get("send_template") == tid:
            self.ctx.db.set("send_template", rest[0])
        self.refresh()
        self.toast.show_message("Template deleted")

    def use_to_send(self, tid: int):
        self.ctx.db.set("send_template", tid)
        self.goto("home")
