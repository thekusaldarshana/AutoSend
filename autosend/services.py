"""App-wide state shared by every screen: database, WhatsApp link, Excel sync, sender."""
from __future__ import annotations

import logging
import os
from datetime import datetime

from PySide6.QtCore import QObject, QTimer, Signal

from .core import paths
from .core.antiban import PRESETS, Pace
from .core.db import Database, SyncDiff
from .core import excel_write
from .core.excel import ExcelError, Roster, read_roster
from .core.recipients import Recipient, all_recipients, list_members
from .core.sender import SendController
from .core.templating import Variable, suggest_variables
from .core.whatsapp import WhatsAppService

log = logging.getLogger("autosend.ctx")


class AppContext(QObject):
    rosterUpdated = Signal(object)       # SyncDiff
    rosterProblem = Signal(str)          # "" when fine
    variablesChanged = Signal()
    settingsChanged = Signal()
    listsChanged = Signal()              # lists, contacts or members changed

    POLL_MS = 1500

    def __init__(self):
        super().__init__()
        self.db = Database(paths.db_path())
        self.wa = WhatsAppService(paths.session_db_path())
        self.sender = SendController(self.db, self.wa, self.pace_dict, lambda: self.name_col, lambda: self.default_cc)
        self.columns: list[str] = []
        self.key_col: str | None = None
        self.phone_col: str | None = None
        self.name_col: str | None = None
        self.class_col: str | None = None
        self.quick_draft: dict = {"text": "", "image": ""}     # Quick send draft, kept only while the app is open
        self.last_sync: datetime | None = None
        self.problem = ""
        self._sig = None
        self._pending = None
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._poll)

    # ---------------------------------------------------------------- setup
    def start(self) -> None:
        self.reload(force=True)
        self.timer.start(self.POLL_MS)

    def shutdown(self) -> None:
        self.timer.stop()
        self.sender.stop()
        self.sender.join(2.0)
        self.wa.stop()
        try:
            self.db.close()
        except Exception:
            pass

    # ------------------------------------------------------------- settings
    @property
    def excel_path(self) -> str:
        return self.db.get("excel_path", "") or ""

    def set_excel_path(self, path: str) -> None:
        self.db.set("excel_path", path)
        self.db.set("key_col", "")
        self.db.set("phone_col", "")
        self._sig = self._pending = None
        self.reload(force=True)

    @property
    def default_cc(self) -> str:
        return str(self.db.get("country_code", "94") or "94")

    def pace_dict(self) -> dict:
        d = dict(PRESETS["balanced"])
        d.update(self.db.get("pace", {}) or {})
        return d

    def pace(self) -> Pace:
        return Pace.from_dict(self.pace_dict())

    def set_pace(self, pace: Pace) -> None:
        self.db.set("pace", pace.to_dict())
        self.settingsChanged.emit()

    def set_column_override(self, key_col: str, phone_col: str) -> None:
        self.db.set("key_col", key_col or "")
        self.db.set("phone_col", phone_col or "")
        self._sig = None
        self.reload(force=True)

    # ------------------------------------------------------------ Excel sync
    def _stat(self):
        try:
            st = os.stat(self.excel_path)
            return (st.st_mtime_ns, st.st_size)
        except OSError:
            return None

    def _poll(self) -> None:
        if not self.excel_path:
            return
        sig = self._stat()
        if sig is None:
            if not self.problem:
                self._set_problem("The Excel file could not be found. Was it moved or renamed?")
            return
        if sig == self._sig:
            return
        if sig != self._pending:            # changed just now: wait one more tick so a half-saved file isn't read
            self._pending = sig
            return
        self.reload(force=True)

    def _set_problem(self, msg: str) -> None:
        self.problem = msg
        self.rosterProblem.emit(msg)

    def reload(self, force: bool = False) -> Roster | None:
        path = self.excel_path
        if not path:
            return None
        sig = self._stat()
        if not force and sig == self._sig:
            return None
        try:
            roster = read_roster(path, self.db.get("key_col") or None, self.db.get("phone_col") or None,
                                 self.default_cc)
        except ExcelError as e:
            self._set_problem(str(e))
            return None
        except Exception:
            log.exception("reading Excel failed")
            self._set_problem("Something went wrong reading the Excel file.")
            return None
        self._sig, self._pending = sig, sig
        self.columns = roster.columns
        self.key_col, self.phone_col, self.name_col = roster.key_col, roster.phone_col, roster.name_col
        self.class_col = roster.class_col
        diff = self.db.sync_students(roster.rows)
        if not self.db.list_variables():
            for v in suggest_variables(roster.columns, roster.phone_col):
                self.db.save_variable(v)
            self.variablesChanged.emit()
        self.last_sync = datetime.now()
        if self.problem:
            self._set_problem("")
        self.rosterUpdated.emit(diff)
        return roster

    # ------------------------------------------------------------- helpers
    def variables(self) -> list[Variable]:
        return self.db.list_variables()

    def students(self) -> list[dict]:
        return self.db.list_students()

    def display_name(self, student: dict) -> str:
        if self.name_col and student["values"].get(self.name_col):
            return student["values"][self.name_col]
        return student["key"]

    def sendable(self, student: dict) -> bool:
        return bool(student["phone"]) and student["present"]

    def missing_columns(self) -> list[str]:
        """Column-variables that point at a header no longer in the Excel file."""
        cols = set(self.columns)
        return [v.name for v in self.variables() if v.kind == "column" and v.source not in cols]

    # ------------------------------------------------- people & lists
    def recipients(self) -> list[Recipient]:
        return all_recipients(self.db, self.name_col, self.default_cc, self.class_col)

    def people_in(self, lst: dict, everyone: list[Recipient] | None = None) -> list[Recipient]:
        return list_members(self.db, lst, everyone if everyone is not None else self.recipients())

    # ------------------------------------------- students: edit the Excel file
    def _text_cols(self) -> set[str]:
        return {c for c in (self.key_col, self.phone_col) if c}

    def _require_file(self) -> str:
        if not self.excel_path:
            raise ExcelError("Choose your Excel file first.")
        return self.excel_path

    def _fresh(self) -> None:
        """Re-read the file so row numbers are current before we change anything."""
        self.reload(force=True)
        if self.problem:
            raise ExcelError(self.problem)

    def _check_key_free(self, values: dict[str, str], own_key: str | None = None) -> None:
        if not self.key_col:
            return
        k = (values.get(self.key_col) or "").strip()
        if not k or k == own_key:
            return
        if self.db.get_student(k) and self.db.get_student(k)["present"]:
            raise ExcelError(f"A student with {self.key_col} {k} already exists.")

    def add_student(self, values: dict[str, str]) -> None:
        path = self._require_file()
        self._fresh()
        self._check_key_free(values)
        excel_write.add_row(path, values, self._text_cols())
        self.reload(force=True)
        self.listsChanged.emit()

    def update_student(self, key: str, values: dict[str, str]) -> None:
        path = self._require_file()
        self._fresh()
        st = self.db.get_student(key)
        if not st or not st["present"]:
            raise ExcelError("That student is no longer in the Excel file.")
        self._check_key_free(values, key)
        excel_write.update_row(path, st["row_no"], key, self.key_col, values, self._text_cols())
        new_key = (values.get(self.key_col) or "").strip() if self.key_col else key
        if new_key and new_key != key:
            self.db.rename_student_key(key, new_key)
        self.reload(force=True)
        self.listsChanged.emit()

    def delete_students(self, keys: list[str]) -> None:
        path = self._require_file()
        self._fresh()
        rows = []
        for k in keys:
            st = self.db.get_student(k)
            if st and st["present"]:
                rows.append((st["row_no"], k))
        if not rows:
            return
        excel_write.delete_rows(path, rows, self.key_col)
        self.db.forget_students(keys)
        self.reload(force=True)
        self.listsChanged.emit()
