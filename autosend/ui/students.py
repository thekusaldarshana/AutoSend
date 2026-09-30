"""Students screen: a live view of the Excel file with send status."""
from __future__ import annotations

import os

from PySide6.QtCore import QAbstractTableModel, QItemSelectionModel, QModelIndex, QSortFilterProxyModel, Qt, QTimer
from PySide6.QtGui import QBrush, QColor
from PySide6.QtWidgets import (QAbstractItemView, QComboBox, QFileDialog, QHBoxLayout, QHeaderView, QLineEdit,
                               QMenu, QTableView, QVBoxLayout)

from ..core.phone import pretty_phone
from ..services import AppContext
from . import actions, theme
from .widgets import Banner, Page, button, label

STATUS_FILTERS = ["All students", "Ready to send", "Needs attention", "Sent", "Failed", "Not sent yet"]


class StudentModel(QAbstractTableModel):
    def __init__(self, ctx: AppContext):
        super().__init__()
        self.ctx = ctx
        self.rows: list[dict] = []
        self.states: dict[str, tuple[str, str | None]] = {}
        self.cols: list[str] = []

    # ---- data
    def reload(self) -> None:
        self.beginResetModel()
        self.rows = self.ctx.students()
        self.cols = list(self.ctx.columns)
        camp = self.ctx.db.latest_campaign()
        self.states = self.ctx.db.send_states(camp["id"]) if camp else {}
        self.endResetModel()

    def status_of(self, s: dict) -> tuple[str, str]:
        """(label, kind) where kind in ok/bad/warn/mute/info"""
        if not s["phone"]:
            return (s.get("phone_error") or "No phone number", "warn")
        st = self.states.get(s["key"])
        if st:
            status, err = st
            if status == "sent":
                return ("Sent", "ok")
            if status == "failed":
                return (err or "Failed", "bad")
            if status == "skipped":
                return (err or "Skipped", "warn")
            return ("Waiting to send", "info")
        if s.get("wa_state") == "no":
            return ("Not on WhatsApp", "warn")
        return ("Ready", "mute")

    # ---- Qt model
    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self.rows)

    def columnCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self.cols) + 2

    def headerData(self, section, orientation, role=Qt.DisplayRole):
        if orientation == Qt.Horizontal and role == Qt.DisplayRole:
            if section == 0:
                return ""
            if section <= len(self.cols):
                return self.cols[section - 1]
            return "Status"
        if orientation == Qt.Horizontal and role == Qt.TextAlignmentRole:
            return int(Qt.AlignLeft | Qt.AlignVCenter)
        return None

    def flags(self, index):
        f = Qt.ItemIsEnabled | Qt.ItemIsSelectable
        if index.column() == 0 and self.rows[index.row()]["phone"]:
            f |= Qt.ItemIsUserCheckable
        return f

    def data(self, index, role=Qt.DisplayRole):
        s = self.rows[index.row()]
        c = index.column()
        if c == 0:
            if role == Qt.CheckStateRole and s["phone"]:
                return Qt.Checked if s["selected"] else Qt.Unchecked
            return None
        if c <= len(self.cols):
            col = self.cols[c - 1]
            if role == Qt.DisplayRole:
                if col == self.ctx.phone_col and s["phone"]:
                    return pretty_phone(s["phone"])
                return s["values"].get(col, "")
            if role == Qt.ForegroundRole and col == self.ctx.phone_col and not s["phone"]:
                return QBrush(QColor(theme.C["danger"]))
            return None
        text, kind = self.status_of(s)
        if role == Qt.DisplayRole:
            return ("●  " if kind != "mute" else "○  ") + text
        if role == Qt.ForegroundRole:
            col = dict(ok=theme.C["primary_text"], bad=theme.C["danger"], warn=theme.C["warn"],
                       info=theme.C["info"], mute=theme.C["muted"])[kind]
            return QBrush(QColor(col))
        return None

    def setData(self, index, value, role=Qt.EditRole):
        if index.column() == 0 and role == Qt.CheckStateRole:
            s = self.rows[index.row()]
            on = Qt.CheckState(value) == Qt.Checked
            s["selected"] = on
            self.ctx.db.set_selected([s["key"]], on)
            self.dataChanged.emit(index, index, [Qt.CheckStateRole])
            self.ctx.settingsChanged.emit()
            return True
        return False


class StudentFilter(QSortFilterProxyModel):
    def __init__(self):
        super().__init__()
        self.text = ""
        self.mode = 0
        self.allowed: set[str] | None = None

    def set_filter(self, text: str, mode: int, allowed: set[str] | None = None) -> None:
        self.text, self.mode, self.allowed = text.strip().lower(), mode, allowed
        self.invalidateFilter()

    def filterAcceptsRow(self, row, parent):
        m: StudentModel = self.sourceModel()
        s = m.rows[row]
        if self.allowed is not None and s["key"] not in self.allowed:
            return False
        if self.text and not any(self.text in v.lower() for v in s["values"].values()) \
                and self.text not in (s["phone"] or ""):
            return False
        label_, kind = m.status_of(s)
        st = m.states.get(s["key"], ("", None))[0]
        if self.mode == 1:
            return bool(s["phone"]) and st in ("", "pending") and s.get("wa_state") != "no"
        if self.mode == 2:
            return kind in ("warn", "bad")
        if self.mode == 3:
            return st == "sent"
        if self.mode == 4:
            return st == "failed"
        if self.mode == 5:
            return st != "sent"
        return True


class StudentsPage(Page):
    def __init__(self, ctx: AppContext, toast):
        super().__init__("Students", "This list mirrors your Excel file. Edit the file and save. It updates here by itself.")
        self.ctx, self.toast = ctx, toast

        self.add_btn = button("Add student", "primary", "add")
        self.add_btn.clicked.connect(self.add_student)
        self.header.actions.addWidget(self.add_btn)
        self.open_btn = button("Open in Excel", "", "excel")
        self.open_btn.clicked.connect(self.open_excel)
        self.change_btn = button("Change file…", "", "folder")
        self.change_btn.clicked.connect(self.change_file)
        self.header.actions.addWidget(self.open_btn)
        self.header.actions.addWidget(self.change_btn)

        self.banner = Banner("", "warn")
        self.banner.setVisible(False)
        self.root.addWidget(self.banner)

        bar = QHBoxLayout()
        bar.setSpacing(10)
        self.search = QLineEdit()
        self.search.setPlaceholderText("Search name, class, admission or number…")
        self.search.setClearButtonEnabled(True)
        self.search.setMinimumWidth(300)
        self.filter = QComboBox()
        self.filter.addItems(STATUS_FILTERS)
        self.list_filter = QComboBox()
        self.list_filter.setMinimumWidth(160)
        self.all_btn = button("Select all", "ghost")
        self.none_btn = button("Select none", "ghost")
        bar.addWidget(self.search, 1)
        bar.addWidget(self.list_filter)
        bar.addWidget(self.filter)
        bar.addWidget(self.all_btn)
        bar.addWidget(self.none_btn)
        self.root.addLayout(bar)

        acts = QHBoxLayout()
        acts.setSpacing(8)
        self.edit_btn = button("Edit", "", "edit")
        self.del_btn = button("Delete", "danger", "delete")
        self.to_list_btn = button("Add to list", "", "add")
        self.from_list_btn = button("Remove from this list", "", "cancel")
        for b in (self.edit_btn, self.del_btn, self.to_list_btn, self.from_list_btn):
            acts.addWidget(b)
        acts.addStretch(1)
        acts.addWidget(label("Tip: double-click a row to edit it. Changes are saved to your Excel file.", "faint"))
        self.root.addLayout(acts)
        self.edit_btn.clicked.connect(self.edit_selected)
        self.del_btn.clicked.connect(self.delete_selected)
        self.from_list_btn.clicked.connect(self.remove_from_list)

        self.model = StudentModel(ctx)
        self.proxy = StudentFilter()
        self.proxy.setSourceModel(self.model)
        self.model.dataChanged.connect(self._tick_changed)
        self.table = QTableView()
        self.table.setModel(self.proxy)
        self.table.setAlternatingRowColors(True)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(40)
        self.table.setShowGrid(False)
        self.table.setWordWrap(False)
        self.root.addWidget(self.table, 1)

        foot = QHBoxLayout()
        self.summary = label("", "muted")
        self.sync_lbl = label("", "faint")
        foot.addWidget(self.summary, 1)
        foot.addWidget(self.sync_lbl)
        self.root.addLayout(foot)

        self.search.textChanged.connect(self._refilter)
        self.filter.currentIndexChanged.connect(self._refilter)
        self.list_filter.currentIndexChanged.connect(self._refilter)
        self.table.doubleClicked.connect(lambda *_: self.edit_selected())
        self.table.selectionModel().selectionChanged.connect(lambda *_: self._buttons())
        ctx.listsChanged.connect(lambda: self.isVisible() and self.refresh())
        self.all_btn.clicked.connect(lambda: self._select_all(True))
        self.none_btn.clicked.connect(lambda: self._select_all(False))
        theme.signals.changed.connect(lambda: self.table.viewport().update())
        ctx.rosterUpdated.connect(self._on_roster)
        ctx.rosterProblem.connect(lambda _m: self._update_banner())
        ctx.sender.itemDone.connect(lambda *_: self._debounced_reload())
        self._t = QTimer(self)
        self._t.setSingleShot(True)
        self._t.setInterval(400)
        self._t.timeout.connect(self.refresh)
        self._age = QTimer(self)
        self._age.timeout.connect(self._update_sync_label)
        self._age.start(5000)

    # ---------------------------------------------------------------- actions
    def open_excel(self):
        p = self.ctx.excel_path
        if p and os.path.exists(p):
            os.startfile(p)

    def change_file(self):
        start = os.path.dirname(self.ctx.excel_path) if self.ctx.excel_path else ""
        p, _ = QFileDialog.getOpenFileName(self, "Choose your Excel file", start, "Excel files (*.xlsx *.xlsm)")
        if p:
            self.ctx.set_excel_path(p)
            self.toast.show_message("Excel file changed")

    def _tick_changed(self, top_left, _bottom_right, roles):
        """Qt swallows the mouse press on a tick box, so the row would not highlight. Do it here."""
        if top_left.column() != 0 or (roles and Qt.CheckStateRole not in roles):
            return
        idx = self.proxy.mapFromSource(top_left)
        if not idx.isValid():
            return
        sel = self.table.selectionModel()
        on = self.model.rows[top_left.row()]["selected"]
        sel.select(idx, (QItemSelectionModel.Select if on else QItemSelectionModel.Deselect) | QItemSelectionModel.Rows)
        sel.setCurrentIndex(idx, QItemSelectionModel.NoUpdate)

    def _select_rows(self, keys: set[str]) -> None:
        sel = self.table.selectionModel()
        sel.clearSelection()
        for r in range(self.proxy.rowCount()):
            idx = self.proxy.index(r, 0)
            if self.model.rows[self.proxy.mapToSource(idx).row()]["key"] in keys:
                sel.select(idx, QItemSelectionModel.Select | QItemSelectionModel.Rows)

    def _select_all(self, on: bool):
        keys = []
        for r in range(self.proxy.rowCount()):
            s = self.model.rows[self.proxy.mapToSource(self.proxy.index(r, 0)).row()]
            if s["phone"]:
                keys.append(s["key"])
        self.ctx.db.set_selected(keys, on)
        self.refresh()
        self._select_rows(set(keys) if on else set())
        self.ctx.settingsChanged.emit()

    def _current_list(self) -> dict | None:
        lid = self.list_filter.currentData()
        return self.ctx.db.get_list(lid) if lid else None

    def _refilter(self):
        lst = self._current_list()
        allowed = None
        if lst:
            allowed = {p.ref for p in self.ctx.people_in(lst) if p.kind == "student"}
        self.proxy.set_filter(self.search.text(), self.filter.currentIndex(), allowed)
        self._update_summary()
        self._buttons()

    def _fill_lists(self):
        cur = self.list_filter.currentData()
        self.list_filter.blockSignals(True)
        self.list_filter.clear()
        self.list_filter.addItem("All lists", 0)
        for l in self.ctx.db.list_lists():
            self.list_filter.addItem(l["name"], l["id"])
        self.list_filter.setCurrentIndex(max(0, self.list_filter.findData(cur)))
        self.list_filter.blockSignals(False)

    # ------------------------------------------------------------- CRUD
    def _selected_keys(self) -> list[str]:
        rows = sorted({self.proxy.mapToSource(i).row() for i in self.table.selectionModel().selectedRows()})
        return [self.model.rows[r]["key"] for r in rows]

    def _buttons(self):
        n = len(self._selected_keys())
        lst = self._current_list()
        self.edit_btn.setEnabled(n == 1)
        self.del_btn.setEnabled(n >= 1)
        self.to_list_btn.setEnabled(n >= 1)
        self.from_list_btn.setVisible(bool(lst and lst["kind"] == "static"))
        self.from_list_btn.setEnabled(n >= 1)
        menu = QMenu(self)
        for l in self.ctx.db.list_lists():
            if l["kind"] == "static":
                menu.addAction(l["name"], lambda lid=l["id"], nm=l["name"]: self.add_to_list(lid, nm))
        if not menu.isEmpty():
            menu.addSeparator()
        menu.addAction("＋ New list with these students…", self.add_to_new_list)
        self.to_list_btn.setMenu(menu)

    def add_student(self):
        key = actions.add_student(self.ctx, self, self.toast)
        if key:
            self.refresh()

    def edit_selected(self):
        keys = self._selected_keys()
        if len(keys) == 1 and actions.edit_student(self.ctx, self, self.toast, keys[0]):
            self.refresh()

    def delete_selected(self):
        if actions.delete_people(self.ctx, self, self.toast, self._selected_keys()):
            self.refresh()

    def add_to_list(self, lid: int, name: str):
        n = self.ctx.db.add_members(lid, self._selected_keys())
        self.ctx.listsChanged.emit()
        self.toast.show_message(f"{n} added to “{name}”")

    def add_to_new_list(self):
        from PySide6.QtWidgets import QInputDialog
        name, ok = QInputDialog.getText(self, "New list", "Name for the new list:")
        name = name.strip()
        if ok and name:
            if any(l["name"].lower() == name.lower() for l in self.ctx.db.list_lists()):
                self.toast.show_message("You already have a list with that name")
                return
            lid = self.ctx.db.save_list(None, name, "static", {}, None)
            self.add_to_list(lid, name)

    def remove_from_list(self):
        lst = self._current_list()
        if lst:
            self.ctx.db.remove_members(lst["id"], self._selected_keys())
            self.ctx.listsChanged.emit()
            self.toast.show_message(f"Removed from “{lst['name']}”")

    def _debounced_reload(self):
        if self.isVisible():
            self._t.start()

    # ---------------------------------------------------------------- refresh
    def on_show(self):
        self.refresh()

    def _on_roster(self, diff):
        self.refresh()
        if diff is not None and diff.changed and self.isVisible():
            bits = []
            if diff.added:
                bits.append(f"{diff.added} added")
            if diff.updated:
                bits.append(f"{diff.updated} changed")
            if diff.removed:
                bits.append(f"{diff.removed} removed")
            self.toast.show_message("Excel updated: " + ", ".join(bits))

    def refresh(self):
        keep = set(self._selected_keys()) if hasattr(self, "table") else set()
        self.model.reload()
        self._fill_lists()
        self._refilter()
        if keep:
            self._select_rows(keep)
        self._configure_columns()
        self._update_banner()
        self._update_summary()
        self._update_sync_label()

    def _configure_columns(self):
        h = self.table.horizontalHeader()
        n = self.model.columnCount()
        if n < 3:
            return
        h.setSectionResizeMode(QHeaderView.ResizeToContents)
        h.setStretchLastSection(True)
        self.table.setColumnWidth(0, 44)
        h.setSectionResizeMode(0, QHeaderView.Fixed)
        for i, col in enumerate(self.model.cols, start=1):
            if "name" in col.lower():
                h.setSectionResizeMode(i, QHeaderView.Interactive)
                self.table.setColumnWidth(i, 250)

    def _update_banner(self):
        if not self.ctx.excel_path:
            self.banner.set("No Excel file chosen yet. Click 'Change file…' to pick your student list.", "warn")
            self.banner.setVisible(True)
        elif self.ctx.problem:
            self.banner.set(self.ctx.problem, "bad")
            self.banner.setVisible(True)
        else:
            self.banner.setVisible(False)

    def _update_summary(self):
        total = len(self.model.rows)
        sel = sum(1 for s in self.model.rows if s["selected"] and s["phone"])
        bad = sum(1 for s in self.model.rows if not s["phone"])
        shown = self.proxy.rowCount()
        txt = f"{total} students · {sel} selected to receive a message"
        if bad:
            txt += f" · {bad} without a usable number"
        if shown != total:
            txt += f" · showing {shown}"
        self.summary.setText(txt)

    def _update_sync_label(self):
        ls = self.ctx.last_sync
        self.sync_lbl.setText("Synced with Excel at " + ls.strftime("%H:%M:%S") if ls else "")
