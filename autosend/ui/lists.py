"""Lists: groups of people (students and other contacts) you can message together."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QBrush, QColor
from PySide6.QtWidgets import (QAbstractItemView, QDialog, QHBoxLayout, QHeaderView, QLineEdit, QListWidget,
                               QListWidgetItem, QMenu, QMessageBox, QTableWidget, QTableWidgetItem, QVBoxLayout)

from ..core.phone import pretty_phone
from ..core.recipients import describe_rule
from ..services import AppContext
from . import actions, theme
from .people import ImportDialog, ListDialog, PickPeopleDialog
from .widgets import Banner, Card, Page, Pill, button, label

EVERYONE = 0


class ListsPage(Page):
    def __init__(self, ctx: AppContext, toast, goto):
        super().__init__("Lists", "Group people so you can message them together. Add students, contacts, or both.")
        self.ctx, self.toast, self.goto = ctx, toast, goto
        self._everyone = []

        self.new_btn = button("New list", "primary", "add")
        menu = QMenu(self)
        menu.addAction("Fixed list: I choose who is in it", lambda: self.new_list("static"))
        menu.addAction("Smart list: fills itself from a rule", lambda: self.new_list("smart"))
        menu.addSeparator()
        menu.addAction("Import people from a file…", self.import_file)
        self.new_btn.setMenu(menu)
        self.header.actions.addWidget(self.new_btn)

        body = QHBoxLayout()
        body.setSpacing(16)
        self.root.addLayout(body, 1)

        self.side = QListWidget()
        self.side.setFixedWidth(250)
        self.side.currentRowChanged.connect(lambda *_: self._show())
        body.addWidget(self.side)

        right = QVBoxLayout()
        right.setSpacing(12)
        body.addLayout(right, 1)

        top = Card(pad=16, spacing=8)
        row = QHBoxLayout()
        self.title = label("", "h2")
        self.kind_pill = Pill("", "mute")
        row.addWidget(self.title)
        row.addWidget(self.kind_pill)
        row.addStretch(1)
        top.body.addLayout(row)
        row2 = QHBoxLayout()
        row2.setSpacing(8)
        self.send_btn = button("Send to this list", "primary", "send")
        self.edit_btn = button("Edit list", "", "edit")
        self.del_btn = button("Delete list", "danger", "delete")
        self.send_btn.clicked.connect(self.send_to_list)
        self.edit_btn.clicked.connect(self.edit_list)
        self.del_btn.clicked.connect(self.delete_list)
        for b in (self.send_btn, self.edit_btn, self.del_btn):
            row2.addWidget(b)
        row2.addStretch(1)
        top.body.addLayout(row2)
        self.desc = label("", "muted", wrap=True)
        top.body.addWidget(self.desc)
        top.setMinimumHeight(150)
        from PySide6.QtWidgets import QSizePolicy
        top.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Minimum)
        self.desc.setMinimumHeight(22)
        right.addWidget(top)

        bar = QHBoxLayout()
        bar.setSpacing(8)
        self.search = QLineEdit()
        self.search.setPlaceholderText("Search this list…")
        self.search.setClearButtonEnabled(True)
        bar.addWidget(self.search, 1)
        right.addLayout(bar)
        bar = QHBoxLayout()
        bar.setSpacing(8)
        self.add_student_btn = button("Add student", "", "add")
        self.add_student_btn.clicked.connect(lambda: actions.add_student(self.ctx, self, self.toast))
        self.add_people = button("Add people", "", "add")
        self.add_contact_btn = button("New contact", "", "contact")
        self.import_btn = button("Import", "", "export", tip="Import people from an Excel or CSV file")
        self.remove_btn = button("Remove", "", "cancel", tip="Remove the selected people from this list (they stay in your data)")
        self.edit_person_btn = button("Edit", "", "edit")
        self.delete_person_btn = button("Delete", "danger", "delete")
        for b in (self.add_student_btn, self.add_people, self.add_contact_btn, self.import_btn, self.remove_btn,
                  self.edit_person_btn, self.delete_person_btn):
            b.setMinimumWidth(b.sizeHint().width())
            bar.addWidget(b)
        bar.addStretch(1)
        right.addLayout(bar)

        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["Name", "WhatsApp number", "Type", "Details"])
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(40)
        self.table.setShowGrid(False)
        self.table.setAlternatingRowColors(True)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        h = self.table.horizontalHeader()
        h.setSectionResizeMode(0, QHeaderView.Stretch)
        h.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        h.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        h.setSectionResizeMode(3, QHeaderView.Stretch)
        right.addWidget(self.table, 1)
        self.empty = Banner("", "info")
        right.addWidget(self.empty)
        self.count = label("", "muted")
        right.addWidget(self.count)

        self.add_people.clicked.connect(self.add_to_list)
        self.add_contact_btn.clicked.connect(self.new_contact)
        self.import_btn.clicked.connect(self.import_file)
        self.remove_btn.clicked.connect(self.remove_from_list)
        self.edit_person_btn.clicked.connect(self.edit_selected)
        self.delete_person_btn.clicked.connect(self.delete_selected)
        self.table.doubleClicked.connect(lambda *_: self.edit_selected())
        self.table.itemSelectionChanged.connect(self._buttons)
        self.search.textChanged.connect(self._filter)
        ctx.listsChanged.connect(self.refresh)
        ctx.rosterUpdated.connect(lambda _d: self.isVisible() and self.refresh())

    # ------------------------------------------------------------- helpers
    def on_show(self):
        self.refresh()

    def current_list(self) -> dict | None:
        it = self.side.currentItem()
        lid = it.data(Qt.UserRole) if it else EVERYONE
        return None if lid == EVERYONE else self.ctx.db.get_list(lid)

    def select_list(self, lid: int):
        for i in range(self.side.count()):
            if self.side.item(i).data(Qt.UserRole) == lid:
                self.side.setCurrentRow(i)
                return

    def refresh(self):
        keep = self.side.currentItem().data(Qt.UserRole) if self.side.currentItem() else EVERYONE
        self._everyone = self.ctx.recipients()
        present = [p for p in self._everyone if p.present]
        self.side.blockSignals(True)
        self.side.clear()
        it = QListWidgetItem(f"Everyone\n{len(present)} people")
        it.setData(Qt.UserRole, EVERYONE)
        self.side.addItem(it)
        for l in self.ctx.db.list_lists():
            n = len(self.ctx.people_in(l, self._everyone))
            it = QListWidgetItem(f"{l['name']}\n{n} {'person' if n == 1 else 'people'}  ·  {'Smart' if l['kind'] == 'smart' else 'Fixed'}")
            it.setData(Qt.UserRole, l["id"])
            self.side.addItem(it)
        self.side.blockSignals(False)
        self.select_list(keep) if any(self.side.item(i).data(Qt.UserRole) == keep for i in range(self.side.count())) \
            else self.side.setCurrentRow(0)
        self._show()

    def _people(self) -> list:
        lst = self.current_list()
        if lst is None:
            return [p for p in self._everyone if p.present]
        return self.ctx.people_in(lst, self._everyone)

    def _show(self):
        lst = self.current_list()
        people = self._people()
        static = lst is not None and lst["kind"] == "static"
        self.title.setText(lst["name"] if lst else "Everyone")
        if lst:
            self.kind_pill.set("Smart list" if lst["kind"] == "smart" else "Fixed list", "info" if lst["kind"] == "smart" else "mute")
            self.desc.setText("Includes everyone where: " + describe_rule(lst["rule"]) if lst["kind"] == "smart"
                              else "You choose who is in this list. Add students or contacts with “Add people”.")
        else:
            self.kind_pill.set("All students + contacts", "mute")
            self.desc.setText("Every student from your Excel file plus every contact you have added. "
                              "Add or edit anyone from here.")
        for b, on in ((self.send_btn, bool(lst)), (self.edit_btn, bool(lst)), (self.del_btn, bool(lst)),
                      (self.add_student_btn, lst is None), (self.add_people, static),
                      (self.add_contact_btn, lst is None or static),
                      (self.import_btn, lst is None or static), (self.remove_btn, static)):
            b.setVisible(on)
        self.table.setRowCount(len(people))
        for i, p in enumerate(people):
            details = ", ".join(v for k, v in p.values.items() if v and k not in (self.ctx.name_col, self.ctx.phone_col, "Name", "Phone")
                                and k != self.ctx.key_col)[:80]
            cells = [p.label, pretty_phone(p.phone) or (p.phone_error or "No number"), p.type_label, details]
            for j, t in enumerate(cells):
                item = QTableWidgetItem(t)
                item.setData(Qt.UserRole, p.ref)
                if j == 1 and not p.phone:
                    item.setForeground(QBrush(QColor(theme.C["danger"])))
                self.table.setItem(i, j, item)
        if not people:
            if static:
                self.empty.set("No one in this list yet. Click “Add people…” or “Import file”.", "info")
            elif lst:
                self.empty.set("No one matches this rule right now.", "warn")
            else:
                self.empty.set("Nothing here yet. Choose your Excel file, or add a contact or import a file.", "info")
        self.empty.setVisible(not people)
        n_ok = sum(1 for p in people if p.sendable)
        self.count.setText(f"{len(people)} people · {n_ok} with a usable WhatsApp number")
        self._filter()
        self._buttons()

    def _filter(self):
        t = self.search.text().strip().lower()
        for i in range(self.table.rowCount()):
            hay = " ".join(self.table.item(i, j).text() for j in range(4)).lower()
            self.table.setRowHidden(i, bool(t) and t not in hay)

    def _selected_refs(self) -> list[str]:
        rows = sorted({i.row() for i in self.table.selectedIndexes()})
        return [self.table.item(r, 0).data(Qt.UserRole) for r in rows]

    def _buttons(self):
        n = len(self._selected_refs())
        self.edit_person_btn.setEnabled(n == 1)
        self.delete_person_btn.setEnabled(n >= 1)
        self.remove_btn.setEnabled(n >= 1)

    # -------------------------------------------------------------- actions
    def new_list(self, kind: str):
        dlg = ListDialog(self.ctx, None, self, kind)
        if dlg.exec() == QDialog.Accepted:
            r = dlg.result
            lid = self.ctx.db.save_list(None, r["name"], r["kind"], r["rule"], None)
            self.ctx.listsChanged.emit()
            self.select_list(lid)
            self.toast.show_message(f"List “{r['name']}” created")

    def edit_list(self):
        lst = self.current_list()
        if not lst:
            return
        dlg = ListDialog(self.ctx, lst, self)
        if dlg.exec() == QDialog.Accepted:
            r = dlg.result
            if lst["kind"] == "static" and r["kind"] == "smart":
                self.ctx.db.remove_members(lst["id"], self.ctx.db.member_refs(lst["id"]))
            self.ctx.db.save_list(lst["id"], r["name"], r["kind"], r["rule"], None)
            self.ctx.listsChanged.emit()
            self.toast.show_message("List saved")

    def delete_list(self):
        lst = self.current_list()
        if lst and QMessageBox.question(
                self, "Delete list", f"Delete the list “{lst['name']}”?\n\nThe people in it are not deleted.",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No) == QMessageBox.Yes:
            self.ctx.db.delete_list(lst["id"])
            self.ctx.listsChanged.emit()
            self.toast.show_message("List deleted")

    def add_to_list(self):
        lst = self.current_list()
        if not lst:
            return
        dlg = PickPeopleDialog(self.ctx, set(self.ctx.db.member_refs(lst["id"])), self)
        if dlg.exec() == QDialog.Accepted:
            n = self.ctx.db.add_members(lst["id"], dlg.refs)
            self.ctx.listsChanged.emit()
            self.toast.show_message(f"{n} added to “{lst['name']}”")

    def remove_from_list(self):
        lst = self.current_list()
        refs = self._selected_refs()
        if lst and refs:
            self.ctx.db.remove_members(lst["id"], refs)
            self.ctx.listsChanged.emit()
            self.toast.show_message(f"Removed from “{lst['name']}”. They are still in your data.")

    def new_contact(self):
        lst = self.current_list()
        actions.add_contact(self.ctx, self, self.toast, lst["id"] if lst and lst["kind"] == "static" else None)

    def import_file(self):
        lst = self.current_list()
        dlg = ImportDialog(self.ctx, self, lst["id"] if lst and lst["kind"] == "static" else None)
        if dlg.exec() == QDialog.Accepted:
            self.refresh()
            if dlg.imported_list_id:
                self.select_list(dlg.imported_list_id)
            self.toast.show_message(dlg.summary, 5000)

    def edit_selected(self):
        refs = self._selected_refs()
        if len(refs) == 1:
            actions.edit_person(self.ctx, self, self.toast, refs[0])

    def delete_selected(self):
        actions.delete_people(self.ctx, self, self.toast, self._selected_refs())

    def send_to_list(self):
        lst = self.current_list()
        if lst:
            self.ctx.db.set("audience", lst["id"])
            self.goto("home")
