import os
import shutil
import sys
import tempfile
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
import pytest
from PySide6.QtWidgets import QApplication

from autosend.core import excel_write
from autosend.core.excel import ExcelError, read_roster

from conftest import SAMPLE_XLSX as SRC
app = QApplication.instance() or QApplication([])


@pytest.fixture()
def ctx(monkeypatch):
    d = tempfile.mkdtemp()
    monkeypatch.setenv("AUTOSEND_DATA", d)
    excel_write._backed_up.clear()
    x = os.path.join(d, "list.xlsx")
    shutil.copy(SRC, x)
    from autosend.services import AppContext
    c = AppContext()
    c.db.set("excel_path", x)
    c.reload(force=True)
    yield c
    c.db.close()


def test_student_crud_through_the_app(ctx):
    n0 = len(ctx.students())
    new = {"Admission No.": "3001", "Name": "Test Child", "Class": "Grade 2 A",
           "Whatsapp Number": "0779998888", "Outstanding Amount(Rs.)": "4500"}
    ctx.add_student(new)
    assert len(ctx.students()) == n0 + 1
    assert ctx.db.get_student("3001")["phone"] == "94779998888"
    with pytest.raises(ExcelError):                       # duplicate ID is refused
        ctx.add_student(new)

    # select + list membership survive an edit that changes the ID
    ctx.db.set_selected(["3001"], False)
    lid = ctx.db.save_list(None, "L", "static", {}, None)
    ctx.db.add_members(lid, ["3001"])
    ctx.update_student("3001", {**new, "Admission No.": "3002", "Name": "Test Child Renamed"})
    st = ctx.db.get_student("3002")
    assert st["values"]["Name"] == "Test Child Renamed" and not st["selected"]
    assert ctx.db.member_refs(lid) == ["3002"]
    assert ctx.db.get_student("3001") is None

    ctx.delete_students(["3002", "1096"])
    keys = {s["key"] for s in ctx.students()}
    assert "3002" not in keys and "1096" not in keys and len(keys) == n0 - 1
    assert ctx.db.member_refs(lid) == []
    assert {z.key for z in read_roster(ctx.excel_path).rows} == keys      # Excel file matches exactly


def test_excel_open_in_excel_is_reported_and_nothing_changes(ctx, monkeypatch):
    monkeypatch.setattr(excel_write.os, "replace", lambda *a: (_ for _ in ()).throw(PermissionError()))
    before = len(ctx.students())
    with pytest.raises(excel_write.ExcelBusy):
        ctx.add_student({"Admission No.": "3100", "Name": "X"})
    assert len(ctx.students()) == before and len(read_roster(ctx.excel_path).rows) == before


def test_import_csv_into_list(ctx, tmp_path):
    from autosend.ui.people import ImportDialog, read_table_file
    csvf = tmp_path / "staff.csv"
    csvf.write_text("Name,Whatsapp,Role\nගුරු නිමල්,0771112222,Teacher\nDuplicate Of Student,+94 70 000 0001,X\n"
                    "Bad Number,12,Y\nගුරු කමලා,071 555 6677,Principal\n", encoding="utf-8")
    headers, rows = read_table_file(str(csvf))
    assert headers == ["Name", "Whatsapp", "Role"] and len(rows) == 4

    dlg = ImportDialog(ctx)
    dlg.headers, dlg.body = headers, rows
    for c in (dlg.c_name, dlg.c_phone):
        c.addItems(headers)
    dlg.c_name.setCurrentIndex(0)
    dlg.c_phone.setCurrentIndex(1)
    dlg.new_name.setText("Staff import")
    dlg._try_accept()
    assert dlg.imported_list_id and "2 new contacts added" in dlg.summary and "1 already existed" in dlg.summary \
        and "1 skipped" in dlg.summary, dlg.summary
    members = ctx.people_in(ctx.db.get_list(dlg.imported_list_id))
    assert sorted(p.label for p in members) == sorted(["ගුරු නිමල්", "ගුරු කමලා", next(p.label for p in ctx.recipients() if p.ref == "1096")])
    teacher = next(p for p in members if p.label == "ගුරු නිමල්")
    assert teacher.values["Role"] == "Teacher" and teacher.phone == "94771112222"
    # importing the same file again creates no duplicates
    dlg2 = ImportDialog(ctx, target_list_id=dlg.imported_list_id)
    dlg2.headers, dlg2.body = headers, rows
    for c in (dlg2.c_name, dlg2.c_phone):
        c.addItems(headers)
    dlg2.c_phone.setCurrentIndex(1)
    dlg2._try_accept()
    assert "0 new contacts added" in dlg2.summary and len(ctx.db.list_contacts()) == 2


def test_sending_to_a_contact_uses_their_values(ctx):
    from autosend.core.sender import SendController
    from autosend.core.templating import suggest_variables

    for v in suggest_variables(ctx.columns, ctx.phone_col):
        if not any(x.name == v.name for x in ctx.variables()):
            ctx.db.save_variable(v)
    cid = ctx.db.save_contact(None, {"Name": "Teacher Nimal", "Phone": "0771112222"})
    got = []

    class FakeWA:
        ready = True
        def resolve(self, ph): return ph
        def typing(self, *a, **k): pass
        def send_text(self, jid, text): got.append((jid, text))
        def send_image(self, *a): raise AssertionError

    ctx.db.set_wa  # smoke
    sc = SendController(ctx.db, FakeWA(), lambda: dict(gap_min=0.0, gap_max=0.0, batch_min=9, batch_max=9,
                                                        break_min=0.0, break_max=0.0, typing=False),
                        lambda: ctx.name_col, lambda: ctx.default_cc)
    camp = ctx.db.create_campaign("t", "Dear {Name}, hello", "", [(f"c:{cid}", "Teacher Nimal", "94771112222"),
                                                                    ("1096", "Student One", "94700000001")])
    sc.start(camp)
    t0 = time.time()
    while sc.active and time.time() - t0 < 20:
        app.processEvents()
        time.sleep(0.02)
    assert [t for _j, t in got] == ["Dear Teacher Nimal, hello", "Dear Student One, hello"]
    assert ctx.db.counts(camp)["sent"] == 2
