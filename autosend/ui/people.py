"""Dialogs for people and lists: add/edit a student, add/edit a contact, import a file, pick people, edit a list."""
from __future__ import annotations

import csv
import os
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QAbstractItemView, QComboBox, QDialog, QFileDialog, QFormLayout, QHBoxLayout, QHeaderView,
                               QLineEdit, QRadioButton, QScrollArea, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget)

from ..core import paths
from ..core.phone import normalize_phone, pretty_phone
from ..core.recipients import NO_VALUE_OPS, OPS, TYPE_FIELD, available_fields, rule_matches
from ..services import AppContext
from .widgets import Banner, button, label


def phone_hint(raw: str, cc: str) -> tuple[str, str]:
    """(message, kind) describing how a typed number will be understood."""
    if not raw.strip():
        return "Add the WhatsApp number to send messages to this person.", "info"
    digits, err = normalize_phone(raw, cc)
    if digits:
        return f"Will be sent to {pretty_phone(digits)}", "ok"
    return f"{err}. This person will be skipped when sending.", "warn"


class _Base(QDialog):
    def __init__(self, parent, title: str, width: int = 520):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setMinimumWidth(width)
        self.lay = QVBoxLayout(self)
        self.lay.setContentsMargins(26, 24, 26, 20)
        self.lay.setSpacing(14)
        self.lay.addWidget(label(title, "h2"))
        self.err = Banner("", "bad")
        self.err.setVisible(False)

    def footer(self, ok_text: str):
        self.lay.addWidget(self.err)
        row = QHBoxLayout()
        row.addStretch(1)
        c = button("Cancel")
        c.clicked.connect(self.reject)
        self.ok = button(ok_text, "primary", "check")
        self.ok.clicked.connect(self._try_accept)
        self.ok.setDefault(True)
        row.addWidget(c)
        row.addWidget(self.ok)
        self.lay.addLayout(row)

    def fail(self, msg: str):
        self.err.set(msg, "bad")
        self.err.setVisible(True)

    def _try_accept(self):
        raise NotImplementedError


# ------------------------------------------------------------------ student
class StudentDialog(_Base):
    def __init__(self, ctx: AppContext, student: dict | None, parent=None):
        super().__init__(parent, "Edit student" if student else "Add a student")
        self.ctx, self.student = ctx, student
        self.values: dict[str, str] = {}
        self.lay.addWidget(label("Changes are saved straight into your Excel file.", "muted", wrap=True))
        form = QFormLayout()
        form.setSpacing(10)
        self.edits: dict[str, QLineEdit] = {}
        for col in ctx.columns:
            e = QLineEdit((student["values"].get(col, "") if student else ""))
            title = col + ("  (unique ID)" if col == ctx.key_col else "")
            form.addRow(title, e)
            self.edits[col] = e
        self.lay.addLayout(form)
        self.hint = Banner("", "info")
        self.lay.addWidget(self.hint)
        if ctx.phone_col:
            self.edits[ctx.phone_col].textChanged.connect(self._phone)
            self._phone()
        else:
            self.hint.setVisible(False)
        self.footer("Save student")
        first = next(iter(self.edits.values()), None)
        if first:
            first.setFocus()

    def _phone(self):
        msg, kind = phone_hint(self.edits[self.ctx.phone_col].text(), self.ctx.default_cc)
        self.hint.set(msg, kind)

    def _try_accept(self):
        vals = {c: e.text().strip() for c, e in self.edits.items()}
        kc, nc = self.ctx.key_col, self.ctx.name_col
        if kc and not vals.get(kc):
            return self.fail(f"Please fill in “{kc}”. It identifies the student and must be unique.")
        if nc and not vals.get(nc):
            return self.fail(f"Please fill in “{nc}”.")
        self.values = vals
        self.accept()


# ------------------------------------------------------------------ contact
class ContactDialog(_Base):
    def __init__(self, ctx: AppContext, contact: dict | None, parent=None):
        super().__init__(parent, "Edit contact" if contact else "Add a contact", 540)
        self.ctx, self.contact = ctx, contact
        self.fields: dict[str, str] = {}
        self.lay.addWidget(label("Contacts are people who aren't students, such as teachers, staff or one-off numbers. "
                                 "They are kept inside AutoSend.", "muted", wrap=True))
        f = contact["fields"] if contact else {}
        form = QFormLayout()
        form.setSpacing(10)
        self.name = QLineEdit(f.get("Name", ""))
        self.phone = QLineEdit(f.get("Phone", ""))
        self.phone.setPlaceholderText("e.g. +94 77 123 4567 or 0771234567")
        form.addRow("Name", self.name)
        form.addRow("WhatsApp number", self.phone)
        self.lay.addLayout(form)
        self.hint = Banner("", "info")
        self.lay.addWidget(self.hint)
        self.phone.textChanged.connect(self._phone)
        self._phone()

        self.lay.addWidget(label("More details (optional)", "h3"))
        self.rows_host = QWidget()
        self.rows = QVBoxLayout(self.rows_host)
        self.rows.setContentsMargins(0, 0, 0, 0)
        self.rows.setSpacing(6)
        self.lay.addWidget(self.rows_host)
        self._extra: list[tuple[QLineEdit, QLineEdit, QWidget]] = []
        for k, v in f.items():
            if k not in ("Name", "Phone"):
                self._add_row(k, v)
        add = button("+ Add a detail", "link")
        add.clicked.connect(lambda: self._add_row("", ""))
        self.lay.addWidget(add, 0, Qt.AlignLeft)
        self.footer("Save contact")
        self.name.setFocus()

    def _add_row(self, k: str, v: str):
        w = QWidget()
        h = QHBoxLayout(w)
        h.setContentsMargins(0, 0, 0, 0)
        ke, ve = QLineEdit(k), QLineEdit(v)
        ke.setPlaceholderText("Detail, e.g. Class")
        ve.setPlaceholderText("Value")
        rm = button("", "ghost", "cancel")
        h.addWidget(ke, 2)
        h.addWidget(ve, 3)
        h.addWidget(rm)
        self.rows.addWidget(w)
        item = (ke, ve, w)
        self._extra.append(item)

        def remove():
            self._extra.remove(item)
            w.deleteLater()
        rm.clicked.connect(remove)

    def _phone(self):
        msg, kind = phone_hint(self.phone.text(), self.ctx.default_cc)
        self.hint.set(msg, kind)

    def _try_accept(self):
        name, phone = self.name.text().strip(), self.phone.text().strip()
        if not name:
            return self.fail("Please type a name.")
        if not phone:
            return self.fail("Please type a WhatsApp number.")
        f = {"Name": name, "Phone": phone}
        for ke, ve, _w in self._extra:
            k = ke.text().strip()
            if k and k not in ("Name", "Phone"):
                f[k] = ve.text().strip()
        self.fields = f
        self.accept()


# -------------------------------------------------------------- pick people
class PickPeopleDialog(_Base):
    def __init__(self, ctx: AppContext, exclude: set[str], parent=None, title: str = "Add people to this list"):
        super().__init__(parent, title, 640)
        self.ctx = ctx
        self.refs: list[str] = []
        self.people = [p for p in ctx.recipients() if p.present and p.ref not in exclude]
        self.search = QLineEdit()
        self.search.setPlaceholderText("Search by name, class or number…")
        self.search.setClearButtonEnabled(True)
        self.lay.addWidget(self.search)
        self.table = QTableWidget(len(self.people), 4)
        self.table.setHorizontalHeaderLabels(["", "Name", "Number", "Type"])
        self.table.verticalHeader().setVisible(False)
        self.table.setShowGrid(False)
        self.table.setSelectionMode(QAbstractItemView.NoSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.verticalHeader().setDefaultSectionSize(38)
        self.table.setMinimumHeight(320)
        h = self.table.horizontalHeader()
        h.setSectionResizeMode(0, QHeaderView.Fixed)
        self.table.setColumnWidth(0, 40)
        h.setSectionResizeMode(1, QHeaderView.Stretch)
        h.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        h.setSectionResizeMode(3, QHeaderView.ResizeToContents)
        for i, p in enumerate(self.people):
            chk = QTableWidgetItem()
            chk.setFlags(Qt.ItemIsUserCheckable | Qt.ItemIsEnabled)
            chk.setCheckState(Qt.Unchecked)
            self.table.setItem(i, 0, chk)
            self.table.setItem(i, 1, QTableWidgetItem(p.label))
            self.table.setItem(i, 2, QTableWidgetItem(pretty_phone(p.phone) or "—"))
            self.table.setItem(i, 3, QTableWidgetItem(p.type_label))
        self.lay.addWidget(self.table, 1)
        row = QHBoxLayout()
        a = button("Select all shown", "ghost")
        n = button("Clear", "ghost")
        self.count = label("", "muted")
        a.clicked.connect(lambda: self._all(True))
        n.clicked.connect(lambda: self._all(False))
        row.addWidget(a)
        row.addWidget(n)
        row.addStretch(1)
        row.addWidget(self.count)
        self.lay.addLayout(row)
        self.footer("Add selected")
        self.search.textChanged.connect(self._filter)
        self.table.itemChanged.connect(lambda *_: self._count())
        self._count()

    def _filter(self, text: str):
        t = text.strip().lower()
        for i, p in enumerate(self.people):
            hay = " ".join([p.label, p.phone or "", *p.values.values()]).lower()
            self.table.setRowHidden(i, bool(t) and t not in hay)

    def _all(self, on: bool):
        for i in range(len(self.people)):
            if not self.table.isRowHidden(i):
                self.table.item(i, 0).setCheckState(Qt.Checked if on else Qt.Unchecked)

    def _count(self):
        n = sum(1 for i in range(len(self.people)) if self.table.item(i, 0).checkState() == Qt.Checked)
        self.count.setText(f"{n} selected")

    def _try_accept(self):
        self.refs = [self.people[i].ref for i in range(len(self.people)) if self.table.item(i, 0).checkState() == Qt.Checked]
        if not self.refs:
            return self.fail("Tick at least one person.")
        self.accept()


# ------------------------------------------------------------------- lists
class RuleRow(QWidget):
    def __init__(self, fields: list[str], cond: dict | None, on_change, on_remove):
        super().__init__()
        h = QHBoxLayout(self)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(8)
        self.field = QComboBox()
        self.field.addItems(fields)
        self.op = QComboBox()
        for key, txt in OPS:
            self.op.addItem(txt, key)
        self.value = QLineEdit()
        self.value.setPlaceholderText("value")
        rm = button("", "ghost", "cancel")
        h.addWidget(self.field, 3)
        h.addWidget(self.op, 3)
        h.addWidget(self.value, 3)
        h.addWidget(rm)
        if cond:
            i = self.field.findText(cond.get("field", ""))
            if i < 0:
                self.field.insertItem(0, cond.get("field", ""))
                i = 0
            self.field.setCurrentIndex(i)
            self.op.setCurrentIndex(max(0, self.op.findData(cond.get("op", "is"))))
            self.value.setText(cond.get("value", ""))
        self.field.currentIndexChanged.connect(lambda *_: on_change())
        self.op.currentIndexChanged.connect(lambda *_: (self._sync(), on_change()))
        self.value.textChanged.connect(lambda *_: on_change())
        rm.clicked.connect(lambda: on_remove(self))
        self._sync()

    def _sync(self):
        self.value.setVisible(self.op.currentData() not in NO_VALUE_OPS)

    def cond(self) -> dict:
        return {"field": self.field.currentText(), "op": self.op.currentData(), "value": self.value.text().strip()}


class ListDialog(_Base):
    def __init__(self, ctx: AppContext, lst: dict | None, parent=None, preset_kind: str = "static"):
        super().__init__(parent, "Edit list" if lst else "New list", 640)
        self.ctx, self.lst = ctx, lst
        self.result: dict | None = None
        form = QFormLayout()
        form.setSpacing(10)
        self.name = QLineEdit(lst["name"] if lst else "")
        self.name.setPlaceholderText("e.g. Grade 9 parents")
        form.addRow("List name", self.name)
        kinds = QWidget()
        kl = QHBoxLayout(kinds)
        kl.setContentsMargins(0, 0, 0, 0)
        self.r_static = QRadioButton("Fixed list  (I choose who is in it)")
        self.r_smart = QRadioButton("Smart list  (fills itself from a rule)")
        kl.addWidget(self.r_static)
        kl.addWidget(self.r_smart)
        form.addRow("Type", kinds)
        self.lay.addLayout(form)

        self.rule_box = QWidget()
        rb = QVBoxLayout(self.rule_box)
        rb.setContentsMargins(0, 0, 0, 0)
        rb.setSpacing(8)
        top = QHBoxLayout()
        top.addWidget(label("Include a person when", "h3"))
        self.match = QComboBox()
        self.match.addItem("all of these are true", "all")
        self.match.addItem("any of these is true", "any")
        top.addWidget(self.match)
        top.addStretch(1)
        rb.addLayout(top)
        self.rows_host = QVBoxLayout()
        self.rows_host.setSpacing(6)
        rb.addLayout(self.rows_host)
        add = button("+ Add a condition", "link")
        add.clicked.connect(lambda: self._add_cond(None))
        rb.addWidget(add, 0, Qt.AlignLeft)
        self.matches = Banner("", "info", "people" if False else "info")
        rb.addWidget(self.matches)
        self.lay.addWidget(self.rule_box)

        self.fields = available_fields(ctx.db, ctx.columns)
        self.rows: list[RuleRow] = []
        if lst:
            (self.r_smart if lst["kind"] == "smart" else self.r_static).setChecked(True)
            self.match.setCurrentIndex(0 if lst["rule"].get("match", "all") == "all" else 1)
            for c in lst["rule"].get("conds", []):
                self._add_cond(c)
        else:
            (self.r_smart if preset_kind == "smart" else self.r_static).setChecked(True)
        if self.r_smart.isChecked() and not self.rows:
            self._add_cond(None)
        self.r_smart.toggled.connect(self._kind)
        self.match.currentIndexChanged.connect(self._preview)
        self._kind()
        self.footer("Save list")
        self.name.setFocus()

    def _add_cond(self, cond):
        if cond is None:
            cond = {"field": "Class" if "Class" in self.fields else self.fields[min(1, len(self.fields) - 1)], "op": "is", "value": ""}
        row = RuleRow(self.fields, cond, self._preview, self._remove_row)
        self.rows.append(row)
        self.rows_host.addWidget(row)
        self._preview()

    def _remove_row(self, row):
        self.rows.remove(row)
        row.deleteLater()
        self._preview()

    def _kind(self):
        smart = self.r_smart.isChecked()
        self.rule_box.setVisible(smart)
        if smart and not self.rows:
            self._add_cond(None)
        self.adjustSize()
        self._preview()

    def rule(self) -> dict:
        return {"match": self.match.currentData(), "conds": [r.cond() for r in self.rows]}

    def _preview(self):
        if not self.r_smart.isChecked():
            return
        rule = self.rule()
        n = sum(1 for p in self.ctx.recipients() if p.present and rule_matches(rule, p))
        self.matches.set(f"{n} {'person matches' if n == 1 else 'people match'} right now. The list updates by itself "
                         "when your data changes.", "info")

    def _try_accept(self):
        name = self.name.text().strip()
        if not name:
            return self.fail("Give the list a name.")
        for other in self.ctx.db.list_lists():
            if other["name"].lower() == name.lower() and (not self.lst or other["id"] != self.lst["id"]):
                return self.fail(f"You already have a list called “{name}”.")
        kind = "smart" if self.r_smart.isChecked() else "static"
        rule = self.rule() if kind == "smart" else {}
        if kind == "smart" and not [c for c in rule["conds"] if c["op"] in NO_VALUE_OPS or c["value"]]:
            return self.fail("Add at least one condition with a value.")
        if kind == "smart":
            rule["conds"] = [c for c in rule["conds"] if c["op"] in NO_VALUE_OPS or c["value"]]
        self.result = dict(name=name, kind=kind, rule=rule)
        self.accept()


# ------------------------------------------------------------------ import
HEADER_HINTS = {"phone": ("whatsapp", "phone", "mobile", "contact", "tel", "number"), "name": ("name",)}


def read_table_file(path: str) -> tuple[list[str], list[list[str]]]:
    """(headers, rows) from a .csv or .xlsx file."""
    ext = Path(path).suffix.lower()
    rows: list[list[str]] = []
    if ext in (".xlsx", ".xlsm"):
        import openpyxl
        from ..core.excel import _cell_to_str
        wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
        try:
            for r in wb.active.iter_rows(values_only=True):
                rows.append([_cell_to_str(c) for c in r])
        finally:
            wb.close()
    else:
        text = None
        for enc in ("utf-8-sig", "utf-16", "cp1252"):
            try:
                text = Path(path).read_text(encoding=enc)
                break
            except (UnicodeError, OSError):
                continue
        if text is None:
            raise ValueError("Could not read this file.")
        first = text.splitlines()[0] if text.strip() else ""
        delim = max((",", ";", "\t"), key=first.count)
        rows = [[c.strip() for c in r] for r in csv.reader(text.splitlines(), delimiter=delim)]
    rows = [r for r in rows if any(c.strip() for c in r)]
    if not rows:
        raise ValueError("This file is empty.")
    headers = [h.strip() or f"Column {i + 1}" for i, h in enumerate(rows[0])]
    body = [r + [""] * (len(headers) - len(r)) for r in rows[1:]]
    return headers, body


class ImportDialog(_Base):
    def __init__(self, ctx: AppContext, parent=None, target_list_id: int | None = None):
        super().__init__(parent, "Import people from a file", 700)
        self.ctx = ctx
        self.summary = ""
        self.headers: list[str] = []
        self.body: list[list[str]] = []
        self.imported_list_id: int | None = None
        self.lay.addWidget(label("Choose an Excel or CSV file. AutoSend adds each person as a contact and puts them in a list. "
                                 "People you already have (same number) are not duplicated.", "muted", wrap=True))
        pick = QHBoxLayout()
        self.file_lbl = label("No file chosen", "muted")
        b = button("Choose file…", "", "folder")
        b.clicked.connect(self.choose)
        pick.addWidget(b)
        pick.addWidget(self.file_lbl, 1)
        self.lay.addLayout(pick)

        self.form_host = QWidget()
        fh = QVBoxLayout(self.form_host)
        fh.setContentsMargins(0, 0, 0, 0)
        fh.setSpacing(10)
        self.preview = QTableWidget(0, 0)
        self.preview.setMaximumHeight(170)
        self.preview.verticalHeader().setVisible(False)
        self.preview.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.preview.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        fh.addWidget(self.preview)
        form = QFormLayout()
        form.setSpacing(10)
        self.c_name = QComboBox()
        self.c_phone = QComboBox()
        form.addRow("Name column", self.c_name)
        form.addRow("WhatsApp number column", self.c_phone)
        self.dest = QComboBox()
        self.dest.addItem("＋ Create a new list", None)
        for l in ctx.db.list_lists():
            if l["kind"] == "static":
                self.dest.addItem(l["name"], l["id"])
        self.new_name = QLineEdit()
        self.new_name.setPlaceholderText("Name for the new list")
        form.addRow("Put them in", self.dest)
        form.addRow("New list name", self.new_name)
        fh.addLayout(form)
        self.dest.currentIndexChanged.connect(lambda *_: self.new_name.setEnabled(self.dest.currentData() is None))
        self.lay.addWidget(self.form_host)
        self.form_host.setVisible(False)
        if target_list_id is not None:
            self.dest.setCurrentIndex(max(0, self.dest.findData(target_list_id)))
        self.footer("Import")
        self.ok.setEnabled(False)

    def choose(self):
        p, _ = QFileDialog.getOpenFileName(self, "Choose a file", str(paths.user_documents()),
                                           "Excel or CSV (*.xlsx *.xlsm *.csv *.txt)")
        if not p:
            return
        try:
            self.headers, self.body = read_table_file(p)
        except Exception as e:  # noqa: BLE001
            self.file_lbl.setText("")
            return self.fail(str(e) if isinstance(e, ValueError) else "That file could not be read. Is it open in Excel?")
        self.err.setVisible(False)
        self.file_lbl.setText(f"{os.path.basename(p)}  ·  {len(self.body)} people found")
        self.form_host.setVisible(True)
        self.preview.clear()
        self.preview.setColumnCount(len(self.headers))
        self.preview.setHorizontalHeaderLabels(self.headers)
        show = self.body[:5]
        self.preview.setRowCount(len(show))
        for i, r in enumerate(show):
            for j, v in enumerate(r):
                self.preview.setItem(i, j, QTableWidgetItem(v))
        for combo in (self.c_name, self.c_phone):
            combo.clear()
            combo.addItems(self.headers)
        self.c_name.setCurrentIndex(self._guess("name"))
        self.c_phone.setCurrentIndex(self._guess("phone"))
        if not self.new_name.text():
            self.new_name.setText(Path(p).stem)
        self.new_name.setEnabled(self.dest.currentData() is None)
        self.ok.setEnabled(True)
        self.adjustSize()

    def _guess(self, what: str) -> int:
        for hint in HEADER_HINTS[what]:
            for i, h in enumerate(self.headers):
                if hint in h.lower():
                    return i
        return 0 if what == "name" else min(1, len(self.headers) - 1)

    def _try_accept(self):
        ni, pi = self.c_name.currentIndex(), self.c_phone.currentIndex()
        if ni == pi:
            return self.fail("The name and number must come from different columns.")
        lid = self.dest.currentData()
        if lid is None:
            name = self.new_name.text().strip()
            if not name:
                return self.fail("Give the new list a name.")
            if any(l["name"].lower() == name.lower() for l in self.ctx.db.list_lists()):
                return self.fail(f"You already have a list called “{name}”. Choose it from “Put them in”.")
        existing = {p.phone: p.ref for p in self.ctx.recipients() if p.phone and p.present}
        added = reused = invalid = 0
        refs: list[str] = []
        for r in self.body:
            nm, ph = r[ni].strip(), r[pi].strip()
            digits, _err = normalize_phone(ph, self.ctx.default_cc)
            if not digits:
                invalid += 1
                continue
            if digits in existing:
                refs.append(existing[digits])
                reused += 1
                continue
            fields = {h: v.strip() for h, v in zip(self.headers, r) if v.strip()}
            fields["Name"], fields["Phone"] = nm or ph, ph
            for h in list(fields):
                if h not in ("Name", "Phone") and h in (self.headers[ni], self.headers[pi]):
                    fields.pop(h)
            cid = self.ctx.db.save_contact(None, fields)
            existing[digits] = f"c:{cid}"
            refs.append(f"c:{cid}")
            added += 1
        if lid is None:
            lid = self.ctx.db.save_list(None, self.new_name.text().strip(), "static", {}, None)
        self.ctx.db.add_members(lid, refs)
        self.imported_list_id = lid
        bits = [f"{added} new contact{'s' if added != 1 else ''} added"]
        if reused:
            bits.append(f"{reused} already existed")
        if invalid:
            bits.append(f"{invalid} skipped (no valid number)")
        self.summary = ", ".join(bits)
        self.ctx.listsChanged.emit()
        self.accept()
