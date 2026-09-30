"""History: every run and what happened to each message. Filter by period, class and result; clear when you want."""
from __future__ import annotations

import time
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (QAbstractItemView, QComboBox, QFileDialog, QHBoxLayout, QHeaderView, QLineEdit, QListWidget,
                               QListWidgetItem, QMenu, QMessageBox, QTableWidget, QTableWidgetItem, QVBoxLayout)

from ..core import paths
from ..core.history import PERIODS, in_period, natural_key
from ..core.phone import pretty_phone
from ..services import AppContext
from . import theme
from .widgets import Page, button, label, status_kind

ALL_RUNS = -1
RESULTS = [("", "Any result"), ("sent", "Sent"), ("failed", "Failed"), ("skipped", "Skipped"), ("pending", "Not sent yet")]


def _when(ts) -> str:
    return time.strftime("%d %b %Y, %H:%M", time.localtime(ts)) if ts else ""


class SortItem(QTableWidgetItem):
    """A cell that sorts by a real value (a time, a natural class order) instead of by its text."""

    def __init__(self, text: str, key):
        super().__init__(text)
        self._key = key

    def __lt__(self, other):
        k = getattr(other, "_key", None)
        try:
            return self._key < k
        except TypeError:
            return str(self._key) < str(k)


class HistoryPage(Page):
    def __init__(self, ctx: AppContext, toast):
        super().__init__("History", "Every run you have started, and what happened to each message.")
        self.ctx, self.toast = ctx, toast
        self._rows: list[dict] = []          # what the table currently shows
        self._loading = False

        self.export_btn = button("Save as Excel", "", "export")
        self.export_btn.clicked.connect(self.export)
        self.clear_btn = button("Clear history", "danger", "delete")
        menu = QMenu(self)
        self.act_run = menu.addAction("Delete the selected run", self.delete_run)
        self.act_period = menu.addAction("Delete all runs in the chosen period", self.delete_period)
        menu.addSeparator()
        menu.addAction("Delete all history…", self.delete_all)
        self.clear_btn.setMenu(menu)
        self.header.actions.addWidget(self.clear_btn)
        self.header.actions.addWidget(self.export_btn)

        bar = QHBoxLayout()
        bar.setSpacing(10)
        self.period = QComboBox()
        for key, txt in PERIODS:
            self.period.addItem(txt, key)
        self.period.setCurrentIndex(0)
        self.cls = QComboBox()
        self.cls.setMinimumWidth(150)
        self.result = QComboBox()
        for key, txt in RESULTS:
            self.result.addItem(txt, key)
        self.search = QLineEdit()
        self.search.setPlaceholderText("Search name or number…")
        self.search.setClearButtonEnabled(True)
        bar.addWidget(label("Period", "muted"))
        bar.addWidget(self.period)
        bar.addWidget(label("Class", "muted"))
        bar.addWidget(self.cls)
        bar.addWidget(self.result)
        bar.addWidget(self.search, 1)
        self.root.addLayout(bar)

        body = QHBoxLayout()
        body.setSpacing(16)
        self.root.addLayout(body, 1)
        self.runs = QListWidget()
        self.runs.setFixedWidth(300)
        self.runs.currentRowChanged.connect(lambda *_: self._show())
        body.addWidget(self.runs)

        right = QVBoxLayout()
        self.summary = label("", "h3")
        right.addWidget(self.summary)
        self.table = QTableWidget(0, 7)
        self.table.setHorizontalHeaderLabels(["Student", "Class", "Number", "Result", "Time", "Details", "Run"])
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setShowGrid(False)
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().setDefaultSectionSize(40)
        h = self.table.horizontalHeader()
        h.setSectionResizeMode(0, QHeaderView.Stretch)
        for i in (1, 2, 3, 4):
            h.setSectionResizeMode(i, QHeaderView.ResizeToContents)
        h.setSectionResizeMode(5, QHeaderView.Stretch)
        h.setSectionResizeMode(6, QHeaderView.ResizeToContents)
        h.setSortIndicatorShown(True)
        right.addWidget(self.table, 1)
        self.empty = label("", "muted")
        self.empty.setAlignment(Qt.AlignCenter)
        right.addWidget(self.empty)
        body.addLayout(right, 1)

        self.period.currentIndexChanged.connect(lambda *_: self.refresh())
        self.cls.currentIndexChanged.connect(lambda *_: self._fill_runs())
        self.result.currentIndexChanged.connect(lambda *_: self._fill_runs())
        self.search.textChanged.connect(lambda *_: self._fill_runs())
        ctx.sender.stateChanged.connect(lambda *_: self.isVisible() and self.refresh())
        theme.signals.changed.connect(lambda: self.isVisible() and self._show())

    def on_show(self):
        self.refresh()

    # -------------------------------------------------------------- data
    def _class_of(self, s: dict, current: dict[str, str]) -> str:
        return (s.get("grp") or current.get(s["student_key"], "") or "").strip()

    def _load(self) -> None:
        cc = self.ctx.class_col
        current = {}
        if cc:
            current = {st["key"]: st["values"].get(cc, "") for st in self.ctx.db.list_students(present_only=False)}
        p = self.period.currentData()
        self._camps = sorted((c for c in self.ctx.db.list_campaigns() if in_period(c["created_at"], p)),
                              key=lambda c: c["created_at"] or 0, reverse=True)
        self._sends: dict[int, list[dict]] = {}
        for c in self._camps:
            rows = self.ctx.db.list_sends(c["id"])
            for s in rows:
                s["cls"] = self._class_of(s, current)
                s["run"] = c["name"] or "Message"
                s["run_at"] = c["created_at"]
            self._sends[c["id"]] = rows

    def _matches(self, s: dict) -> bool:
        cls, res, q = self.cls.currentData(), self.result.currentData(), self.search.text().strip().lower()
        if cls and s["cls"] != cls:
            return False
        if res and s["status"] != res:
            return False
        if q and q not in (s["name"] or "").lower() and q not in (s["phone"] or ""):
            return False
        return True

    def _filtering(self) -> bool:
        return bool(self.cls.currentData() or self.result.currentData() or self.search.text().strip())

    def refresh(self):
        self._loading = True
        self._load()
        # class list comes from the messages in the chosen period
        classes = sorted({s["cls"] for rows in self._sends.values() for s in rows if s["cls"]}, key=natural_key)
        keep = self.cls.currentData()
        self.cls.blockSignals(True)
        self.cls.clear()
        self.cls.addItem("All classes", "")
        for c in classes:
            self.cls.addItem(c, c)
        self.cls.setCurrentIndex(max(0, self.cls.findData(keep)))
        self.cls.blockSignals(False)
        self._loading = False
        self._fill_runs()

    def _fill_runs(self):
        if self._loading:
            return
        cur = self.current_id()
        self.runs.blockSignals(True)
        self.runs.clear()
        total_matching = sum(1 for rows in self._sends.values() for s in rows if self._matches(s))
        it = QListWidgetItem(f"All runs in this period\n{total_matching} message{'s' if total_matching != 1 else ''}"
                             + (" match" if self._filtering() else ""))
        it.setData(Qt.UserRole, ALL_RUNS)
        self.runs.addItem(it)
        shown = 0
        for c in self._camps:
            hits = sum(1 for s in self._sends[c["id"]] if self._matches(s))
            if self._filtering() and not hits:
                continue
            n = c["counts"]
            extra = f"  ·  {hits} match" if self._filtering() else ""
            it = QListWidgetItem(f"{_when(c['created_at'])}\n{c['name'] or 'Message'}  ·  {n['sent']}/{n['total']} sent{extra}")
            it.setData(Qt.UserRole, c["id"])
            self.runs.addItem(it)
            shown += 1
        self.runs.blockSignals(False)
        idx = next((i for i in range(self.runs.count()) if self.runs.item(i).data(Qt.UserRole) == cur), 0)
        self.runs.setCurrentRow(idx)
        self._show()

    def current_id(self) -> int | None:
        it = self.runs.currentItem()
        return it.data(Qt.UserRole) if it else None

    def _show(self):
        cid = self.current_id()
        if cid is None:
            return
        rows = [s for c in self._camps for s in self._sends[c["id"]]] if cid == ALL_RUNS else list(self._sends.get(cid, []))
        rows = [s for s in rows if self._matches(s)]
        self._rows = rows
        counts = {"sent": 0, "failed": 0, "skipped": 0, "pending": 0}
        for s in rows:
            counts[s["status"]] = counts.get(s["status"], 0) + 1
        self.summary.setText(f"{len(rows)} message{'s' if len(rows) != 1 else ''}  ·  {counts['sent']} sent  ·  "
                             f"{counts['failed']} failed  ·  {counts['skipped']} skipped  ·  {counts['pending']} not sent yet")

        self.table.setSortingEnabled(False)
        self.table.setRowCount(len(rows))
        colors = dict(ok=theme.C["primary_text"], bad=theme.C["danger"], warn=theme.C["warn"], mute=theme.C["muted"])
        for i, s in enumerate(rows):
            txt, kind = status_kind(s["status"])
            ts = s["sent_at"] or s["updated_at"] or 0
            cells = [
                SortItem(s["name"] or s["student_key"], (s["name"] or "").lower()),
                SortItem(s["cls"], natural_key(s["cls"])),
                SortItem(pretty_phone(s["phone"]), s["phone"] or ""),
                SortItem(txt, txt),
                SortItem(_when(ts) if s["status"] != "pending" else "", ts if s["status"] != "pending" else 0),
                SortItem(s["error"] or "", (s["error"] or "").lower()),
                SortItem(s["run"], s["run_at"] or 0),
            ]
            cells[3].setForeground(QColor(colors.get(kind, theme.C["text"])))
            for j, it in enumerate(cells):
                self.table.setItem(i, j, it)
        self.table.setSortingEnabled(True)
        self.table.sortItems(4, Qt.DescendingOrder)          # newest first

        none_at_all = not self.ctx.db.list_campaigns()
        self.table.setVisible(bool(rows))
        self.empty.setVisible(not rows)
        if not rows:
            self.empty.setText("No runs yet. Your first run will show up here." if none_at_all
                               else "Nothing matches these filters.")
        self.export_btn.setEnabled(bool(rows))
        self.clear_btn.setEnabled(not none_at_all)
        self.act_run.setEnabled(cid not in (None, ALL_RUNS))
        self.act_period.setEnabled(bool(self._camps))

    # ------------------------------------------------------------- clearing
    def _protected(self) -> int | None:
        return self.ctx.sender.campaign_id if self.ctx.sender.active else None

    def _delete(self, ids: list[int], what: str) -> None:
        busy = self._protected()
        ids = [i for i in ids if i != busy]
        if not ids:
            QMessageBox.information(self, "Clear history", "Nothing to delete. A run that is sending right now can't be removed.")
            return
        unfinished = sum(1 for c in self.ctx.db.list_campaigns() if c["id"] in ids and c["counts"]["pending"] > 0)
        msg = f"Delete {what}?\n\nThis only removes the records from History. Messages that were already sent are not affected."
        if unfinished:
            msg += f"\n\n{unfinished} of these runs are unfinished. They can no longer be resumed."
        if busy is not None:
            msg += "\n\nThe run that is sending right now is kept."
        box = QMessageBox(self)
        box.setWindowTitle("Clear history")
        box.setIcon(QMessageBox.Warning)
        box.setText(msg)
        yes = box.addButton("Delete", QMessageBox.DestructiveRole)
        box.addButton("Cancel", QMessageBox.RejectRole)
        box.exec()
        if box.clickedButton() is not yes:
            return
        n = self.ctx.db.delete_campaigns(ids)
        self.ctx.settingsChanged.emit()
        self.refresh()
        self.toast.show_message(f"{n} run{'s' if n != 1 else ''} deleted from History")

    def delete_run(self):
        cid = self.current_id()
        if cid in (None, ALL_RUNS):
            return
        c = self.ctx.db.get_campaign(cid)
        self._delete([cid], f"the run “{c['name'] or 'Message'}” from {_when(c['created_at'])}")

    def delete_period(self):
        label_ = self.period.currentText().lower()
        self._delete([c["id"] for c in self._camps], f"all {len(self._camps)} runs from {label_}")

    def delete_all(self):
        allc = self.ctx.db.list_campaigns()
        self._delete([c["id"] for c in allc], f"ALL history ({len(allc)} runs)")

    # -------------------------------------------------------------- export
    def export(self):
        if not self._rows:
            return
        import openpyxl
        p, _ = QFileDialog.getSaveFileName(self, "Save results", str(paths.user_documents() / f"AutoSend results {time.strftime('%Y-%m-%d')}.xlsx"),
                                           "Excel files (*.xlsx)")
        if not p:
            return
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "Results"
        ws.append(["Student", "Class", "Number", "Result", "Time", "Details", "Run", "Message sent"])
        for s in sorted(self._rows, key=lambda r: r["sent_at"] or r["updated_at"] or 0, reverse=True):
            ws.append([s["name"], s["cls"], pretty_phone(s["phone"]), status_kind(s["status"])[0],
                       _when(s["sent_at"] or s["updated_at"]) if s["status"] != "pending" else "", s["error"] or "",
                       s["run"], s["message"] or ""])
        for col, w in zip("ABCDEFGH", (30, 14, 18, 12, 20, 34, 28, 80)):
            ws.column_dimensions[col].width = w
        try:
            wb.save(p)
        except PermissionError:
            self.toast.show_message("Close that Excel file first, then try again")
            return
        self.toast.show_message(f"Saved {len(self._rows)} rows")
