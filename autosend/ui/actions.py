"""Add / edit / delete people. Shared by the Students and Lists screens so they behave identically."""
from __future__ import annotations

from PySide6.QtWidgets import QDialog, QMessageBox

from ..core.excel import ExcelError
from ..core.excel_write import ExcelBusy
from ..services import AppContext
from .people import ContactDialog, StudentDialog


def _excel_problem(parent, e: ExcelError) -> bool:
    """Show a friendly error. Returns True if the user wants to retry."""
    if isinstance(e, ExcelBusy):
        box = QMessageBox(parent)
        box.setWindowTitle("Excel file is open")
        box.setIcon(QMessageBox.Warning)
        box.setText("Your Excel file is open in Excel.")
        box.setInformativeText("Please close it (or save and close), then press Try again. AutoSend keeps a backup copy of "
                               "your file before every change.")
        retry = box.addButton("Try again", QMessageBox.AcceptRole)
        box.addButton("Cancel", QMessageBox.RejectRole)
        box.exec()
        return box.clickedButton() is retry
    QMessageBox.warning(parent, "Could not save", str(e))
    return False


def _try(parent, fn) -> bool:
    while True:
        try:
            fn()
            return True
        except ExcelError as e:
            if not _excel_problem(parent, e):
                return False


def add_student(ctx: AppContext, parent, toast) -> str | None:
    if not ctx.excel_path:
        QMessageBox.information(parent, "Add a student", "Choose your Excel file first (Settings → Student list).")
        return None
    dlg = StudentDialog(ctx, None, parent)
    if dlg.exec() != QDialog.Accepted:
        return None
    if _try(parent, lambda: ctx.add_student(dlg.values)):
        toast.show_message("Student added to your Excel file")
        return (dlg.values.get(ctx.key_col) or "").strip() if ctx.key_col else None
    return None


def edit_student(ctx: AppContext, parent, toast, key: str) -> bool:
    st = ctx.db.get_student(key)
    if not st:
        return False
    dlg = StudentDialog(ctx, st, parent)
    if dlg.exec() != QDialog.Accepted:
        return False
    if _try(parent, lambda: ctx.update_student(key, dlg.values)):
        toast.show_message("Saved to your Excel file")
        return True
    return False


def add_contact(ctx: AppContext, parent, toast, list_id: int | None = None) -> int | None:
    dlg = ContactDialog(ctx, None, parent)
    if dlg.exec() != QDialog.Accepted:
        return None
    cid = ctx.db.save_contact(None, dlg.fields)
    if list_id:
        ctx.db.add_members(list_id, [f"c:{cid}"])
    ctx.listsChanged.emit()
    toast.show_message("Contact added")
    return cid


def edit_contact(ctx: AppContext, parent, toast, cid: int) -> bool:
    c = ctx.db.get_contact(cid)
    if not c:
        return False
    dlg = ContactDialog(ctx, c, parent)
    if dlg.exec() != QDialog.Accepted:
        return False
    ctx.db.save_contact(cid, dlg.fields)
    ctx.listsChanged.emit()
    toast.show_message("Contact saved")
    return True


def edit_person(ctx: AppContext, parent, toast, ref: str) -> bool:
    if ref.startswith("c:"):
        return edit_contact(ctx, parent, toast, int(ref[2:]))
    return edit_student(ctx, parent, toast, ref)


def delete_people(ctx: AppContext, parent, toast, refs: list[str]) -> bool:
    students = [r for r in refs if not r.startswith("c:")]
    contacts = [int(r[2:]) for r in refs if r.startswith("c:")]
    if not refs:
        return False
    parts = []
    if students:
        parts.append(f"{len(students)} student{'s' if len(students) != 1 else ''} (removed from your Excel file too)")
    if contacts:
        parts.append(f"{len(contacts)} contact{'s' if len(contacts) != 1 else ''}")
    box = QMessageBox(parent)
    box.setWindowTitle("Delete")
    box.setIcon(QMessageBox.Warning)
    box.setText("Delete " + " and ".join(parts) + "?")
    box.setInformativeText("This can't be undone." + (" A backup of your Excel file is kept." if students else ""))
    yes = box.addButton("Delete", QMessageBox.DestructiveRole)
    box.addButton("Cancel", QMessageBox.RejectRole)
    box.exec()
    if box.clickedButton() is not yes:
        return False
    ok = True
    if students:
        ok = _try(parent, lambda: ctx.delete_students(students))
    if ok and contacts:
        ctx.db.delete_contacts(contacts)
        ctx.listsChanged.emit()
    if ok:
        toast.show_message("Deleted")
    return ok
