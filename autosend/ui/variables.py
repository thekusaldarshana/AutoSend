"""Variables: the {placeholders} you can drop into a message. Create, edit, delete."""
from __future__ import annotations

from dataclasses import replace

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (QAbstractItemView, QComboBox, QDialog, QFormLayout, QHBoxLayout, QHeaderView,
                               QLineEdit, QMessageBox, QRadioButton, QTableWidget, QTableWidgetItem, QVBoxLayout,
                               QWidget)

from ..core.templating import Variable, rename_in_body, render, used_names, valid_variable_name
from ..services import AppContext
from . import theme
from .widgets import Banner, Card, Page, button, label

KIND_LABELS = {"column": "From Excel", "text": "Fixed text", "today": "Today's date"}
DATE_FORMATS = ["dd/MM/yyyy", "dd-MM-yyyy", "yyyy-MM-dd", "dd MMMM yyyy", "MMMM dd, yyyy", "dd/MM/yy"]


def describe(v: Variable) -> str:
    if v.kind == "column":
        bits = [f"Column “{v.source}”"]
        if v.number_format == "thousands":
            bits.append("with 1,000 separators")
        if v.prefix or v.suffix:
            bits.append(f"as “{v.prefix}…{v.suffix}”")
        return ", ".join(bits)
    if v.kind == "text":
        return v.source if len(v.source) < 60 else v.source[:57] + "…"
    return f"Today, written like {v.source}"


class VariableDialog(QDialog):
    def __init__(self, ctx: AppContext, var: Variable | None, parent=None):
        super().__init__(parent)
        self.ctx = ctx
        self.editing = var
        self.setWindowTitle("Edit variable" if var else "New variable")
        self.setMinimumWidth(520)
        self.result_var: Variable | None = None

        lay = QVBoxLayout(self)
        lay.setContentsMargins(24, 22, 24, 20)
        lay.setSpacing(14)
        lay.addWidget(label("Edit variable" if var else "New variable", "h2"))
        lay.addWidget(label("A variable is a {placeholder} that AutoSend replaces with real information for each student.",
                            "muted", wrap=True))

        form = QFormLayout()
        form.setSpacing(10)
        form.setLabelAlignment(Qt.AlignLeft)
        self.name = QLineEdit()
        self.name.setPlaceholderText("e.g. Name, Amount, Deadline")
        self.name.setMaxLength(40)
        form.addRow("Name", self.name)

        kinds = QWidget()
        kl = QHBoxLayout(kinds)
        kl.setContentsMargins(0, 0, 0, 0)
        self.r_col = QRadioButton("From Excel")
        self.r_text = QRadioButton("Fixed text")
        self.r_today = QRadioButton("Today's date")
        for r in (self.r_col, self.r_text, self.r_today):
            kl.addWidget(r)
            r.toggled.connect(self._kind_changed)
        kl.addStretch(1)
        form.addRow("What it holds", kinds)

        self.col = QComboBox()
        self.col.addItems(ctx.columns)
        self.col_lbl = label("Excel column")
        form.addRow(self.col_lbl, self.col)
        self.text = QLineEdit()
        self.text.setPlaceholderText("e.g. 15 September 2026")
        self.text_lbl = label("Text")
        form.addRow(self.text_lbl, self.text)
        self.datefmt = QComboBox()
        self.datefmt.setEditable(True)
        self.datefmt.addItems(DATE_FORMATS)
        self.date_lbl = label("Date style")
        form.addRow(self.date_lbl, self.datefmt)

        self.numfmt = QComboBox()
        self.numfmt.addItem("Leave as it is", "none")
        self.numfmt.addItem("Add 1,000 separators  (32000 → 32,000)", "thousands")
        self.numfmt_lbl = label("Numbers")
        form.addRow(self.numfmt_lbl, self.numfmt)
        self.case = QComboBox()
        for txt, val in (("Leave as it is", "none"), ("UPPER CASE", "upper"), ("lower case", "lower"), ("Title Case", "title")):
            self.case.addItem(txt, val)
        self.case_lbl = label("Letters")
        form.addRow(self.case_lbl, self.case)
        self.prefix = QLineEdit()
        self.prefix.setPlaceholderText("e.g. Rs. ")
        self.prefix_lbl = label("Text before")
        form.addRow(self.prefix_lbl, self.prefix)
        self.suffix = QLineEdit()
        self.suffix_lbl = label("Text after")
        form.addRow(self.suffix_lbl, self.suffix)
        self.fallback = QLineEdit()
        self.fallback.setPlaceholderText("Leave empty to skip students with an empty cell")
        self.fallback_lbl = label("If empty use")
        form.addRow(self.fallback_lbl, self.fallback)
        lay.addLayout(form)

        self.preview = Banner("", "info", "info")
        lay.addWidget(self.preview)
        self.err = Banner("", "bad")
        self.err.setVisible(False)
        lay.addWidget(self.err)

        row = QHBoxLayout()
        row.addStretch(1)
        cancel = button("Cancel")
        cancel.clicked.connect(self.reject)
        self.ok = button("Save variable", "primary", "check")
        self.ok.clicked.connect(self._save)
        row.addWidget(cancel)
        row.addWidget(self.ok)
        lay.addLayout(row)

        if var:
            self.name.setText(var.name)
            {"column": self.r_col, "text": self.r_text, "today": self.r_today}[var.kind].setChecked(True)
            if var.kind == "column":
                i = self.col.findText(var.source)
                if i < 0:
                    self.col.insertItem(0, var.source)
                    i = 0
                self.col.setCurrentIndex(i)
            elif var.kind == "text":
                self.text.setText(var.source)
            else:
                self.datefmt.setCurrentText(var.source)
            self.numfmt.setCurrentIndex(max(0, self.numfmt.findData(var.number_format)))
            self.case.setCurrentIndex(max(0, self.case.findData(var.transform)))
            self.prefix.setText(var.prefix)
            self.suffix.setText(var.suffix)
            self.fallback.setText(var.fallback)
        else:
            self.r_col.setChecked(True)
        self._kind_changed()
        for w in (self.name, self.text, self.prefix, self.suffix, self.fallback):
            w.textChanged.connect(self._update_preview)
        for w in (self.col, self.numfmt, self.case):
            w.currentIndexChanged.connect(self._update_preview)
        self.datefmt.currentTextChanged.connect(self._update_preview)
        self._update_preview()

    def _kind(self) -> str:
        return "column" if self.r_col.isChecked() else "text" if self.r_text.isChecked() else "today"

    def _kind_changed(self):
        k = self._kind()
        for w, on in ((self.col, k == "column"), (self.col_lbl, k == "column"),
                      (self.text, k == "text"), (self.text_lbl, k == "text"),
                      (self.datefmt, k == "today"), (self.date_lbl, k == "today"),
                      (self.numfmt, k == "column"), (self.numfmt_lbl, k == "column"),
                      (self.case, k == "column"), (self.case_lbl, k == "column"),
                      (self.prefix, k == "column"), (self.prefix_lbl, k == "column"),
                      (self.suffix, k == "column"), (self.suffix_lbl, k == "column"),
                      (self.fallback, k != "today"), (self.fallback_lbl, k != "today")):
            w.setVisible(on)
        self.adjustSize()
        self._update_preview()

    def _build(self) -> Variable:
        k = self._kind()
        return Variable(
            id=self.editing.id if self.editing else None, name=self.name.text().strip(), kind=k,
            source=self.col.currentText() if k == "column" else self.text.text() if k == "text" else self.datefmt.currentText(),
            number_format=self.numfmt.currentData() if k == "column" else "none",
            prefix=self.prefix.text() if k == "column" else "", suffix=self.suffix.text() if k == "column" else "",
            transform=self.case.currentData() if k == "column" else "none",
            fallback=self.fallback.text() if k != "today" else "")

    def _update_preview(self):
        v = self._build()
        sample = next((s for s in self.ctx.students() if s["phone"]), None) or (self.ctx.students() or [None])[0]
        row = sample["values"] if sample else {}
        res = render("{" + (v.name or "…") + "}", [v] if v.name else [], row)
        shown = res.text if res.text and "{" not in res.text else "(empty for this student)"
        who = f" for {self.ctx.display_name(sample)}" if sample else ""
        self.preview.set(f"Example{who}:  {shown}", "info", "info")

    def _save(self):
        v = self._build()
        if not valid_variable_name(v.name):
            return self._error("Give the variable a short name without { } characters.")
        for other in self.ctx.variables():
            if other.name.lower() == v.name.lower() and other.id != v.id:
                return self._error(f"You already have a variable called {v.name}.")
        if v.kind == "column" and not v.source:
            return self._error("Choose which Excel column this variable reads from.")
        if v.kind == "text" and not v.source.strip():
            return self._error("Type the text this variable should hold.")
        self.result_var = v
        self.accept()

    def _error(self, msg: str):
        self.err.set(msg, "bad")
        self.err.setVisible(True)


class VariablesPage(Page):
    def __init__(self, ctx: AppContext, toast):
        super().__init__("Variables", "Placeholders you can use in your message, such as {Name} or {Amount}.")
        self.ctx, self.toast = ctx, toast
        self.add_btn = button("New variable", "primary", "add")
        self.add_btn.clicked.connect(self.add)
        self.header.actions.addWidget(self.add_btn)

        self.warn = Banner("", "warn")
        self.warn.setVisible(False)
        self.root.addWidget(self.warn)

        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["Placeholder", "Type", "Where the value comes from", "Example"])
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(48)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setShowGrid(False)
        h = self.table.horizontalHeader()
        h.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        h.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        h.setSectionResizeMode(2, QHeaderView.Stretch)
        h.setSectionResizeMode(3, QHeaderView.Stretch)
        self.table.doubleClicked.connect(lambda *_: self.edit())
        self.root.addWidget(self.table, 1)

        bar = QHBoxLayout()
        self.edit_btn = button("Edit", "", "edit")
        self.del_btn = button("Delete", "danger", "delete")
        self.edit_btn.clicked.connect(self.edit)
        self.del_btn.clicked.connect(self.delete)
        bar.addWidget(self.edit_btn)
        bar.addWidget(self.del_btn)
        bar.addStretch(1)
        bar.addWidget(label("Tip: double-click a variable to edit it.", "faint"))
        self.root.addLayout(bar)

        self.table.itemSelectionChanged.connect(self._sel)
        ctx.variablesChanged.connect(self.refresh)
        ctx.rosterUpdated.connect(lambda _d: self.refresh())

    def on_show(self):
        self.refresh()

    def _sample(self) -> dict:
        s = next((x for x in self.ctx.students() if x["phone"]), None) or (self.ctx.students() or [None])[0]
        return s["values"] if s else {}

    def refresh(self):
        vs = self.ctx.variables()
        row = self._sample()
        self.table.setRowCount(len(vs))
        gone = set(self.ctx.missing_columns())
        for i, v in enumerate(vs):
            items = ["{" + v.name + "}", KIND_LABELS[v.kind], describe(v), render("{" + v.name + "}", [v], row).text or "—"]
            for c, t in enumerate(items):
                it = QTableWidgetItem(t)
                it.setData(Qt.UserRole, v.id)
                if c == 0:
                    f = it.font()
                    f.setBold(True)
                    it.setFont(f)
                    it.setForeground(QColor(theme.C["primary_text"] if v.name not in gone else theme.C["danger"]))
                self.table.setItem(i, c, it)
        if gone:
            self.warn.set("These variables point at an Excel column that no longer exists: "
                          + ", ".join("{" + g + "}" for g in sorted(gone)) + ". Edit them to pick the right column.", "warn")
            self.warn.setVisible(True)
        else:
            self.warn.setVisible(False)
        self._sel()

    def _current(self) -> Variable | None:
        r = self.table.currentRow()
        if r < 0:
            return None
        vid = self.table.item(r, 0).data(Qt.UserRole)
        return next((v for v in self.ctx.variables() if v.id == vid), None)

    def _sel(self):
        on = self._current() is not None
        self.edit_btn.setEnabled(on)
        self.del_btn.setEnabled(on)

    def _templates_using(self, name: str) -> list[dict]:
        return [t for t in self.ctx.db.list_templates() if name.lower() in [n.lower() for n in used_names(t["body"])]]

    def add(self):
        dlg = VariableDialog(self.ctx, None, self)
        if dlg.exec() == QDialog.Accepted:
            self.ctx.db.save_variable(dlg.result_var)
            self.ctx.variablesChanged.emit()
            self.toast.show_message(f"Variable {{{dlg.result_var.name}}} created")

    def edit(self):
        v = self._current()
        if not v:
            return
        dlg = VariableDialog(self.ctx, v, self)
        if dlg.exec() != QDialog.Accepted:
            return
        nv = dlg.result_var
        if nv.name.lower() != v.name.lower() or nv.name != v.name:
            for t in self._templates_using(v.name):
                self.ctx.db.save_template(t["id"], t["name"], rename_in_body(t["body"], v.name, nv.name), t["image_path"])
        self.ctx.db.save_variable(nv)
        self.ctx.variablesChanged.emit()
        self.toast.show_message("Variable saved")

    def delete(self):
        v = self._current()
        if not v:
            return
        used = self._templates_using(v.name)
        msg = f"Delete the variable {{{v.name}}}?"
        if used:
            msg += "\n\nIt is used in: " + ", ".join(t["name"] for t in used) + ".\nThose messages will show a warning until you remove it."
        if QMessageBox.question(self, "Delete variable", msg, QMessageBox.Yes | QMessageBox.No, QMessageBox.No) == QMessageBox.Yes:
            self.ctx.db.delete_variable(v.id)
            self.ctx.variablesChanged.emit()
            self.toast.show_message("Variable deleted")
