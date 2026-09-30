import os
import shutil
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
import pytest

from autosend.core import excel_write
from autosend.core.db import Database
from autosend.core.excel import read_roster
from autosend.core.recipients import (all_recipients, describe_rule, get_recipient, list_members, rule_matches)

from conftest import SAMPLE_XLSX as SRC


@pytest.fixture()
def env(monkeypatch):
    d = tempfile.mkdtemp()
    monkeypatch.setenv("AUTOSEND_DATA", d)
    excel_write._backed_up.clear()
    x = os.path.join(d, "list.xlsx")
    shutil.copy(SRC, x)
    db = Database(os.path.join(d, "t.db"))
    r = read_roster(x)
    db.sync_students(r.rows)
    yield d, x, db, r
    db.close()


def test_excel_add_update_delete(env):
    d, x, db, r = env
    text = {r.key_col, r.phone_col}
    excel_write.add_row(x, {"Admission No.": "2001", "Name": "New Kid", "Class": "Grade 1 A",
                            "Whatsapp Number": "+94 77 123 4567", "Outstanding Amount(Rs.)": "5000"}, text)
    r2 = read_roster(x)
    assert len(r2.rows) == 16 and r2.rows[-1].key == "2001" and r2.rows[-1].phone == "94771234567"
    assert r2.rows[-1].values["Outstanding Amount(Rs.)"] == "5000"
    # edit
    row = next(z for z in r2.rows if z.key == "1103")
    excel_write.update_row(x, row.row_no, "1103", r.key_col, {"Name": "Renamed Person", "Outstanding Amount(Rs.)": "123"}, text)
    r3 = read_roster(x)
    assert next(z for z in r3.rows if z.key == "1103").values["Name"] == "Renamed Person"
    # stale row is refused, nothing is written
    with pytest.raises(excel_write.ExcelChanged):
        excel_write.update_row(x, row.row_no, "9999", r.key_col, {"Name": "X"}, text)
    # delete two rows at once
    victims = [(z.row_no, z.key) for z in r3.rows if z.key in ("1096", "1104")]
    excel_write.delete_rows(x, victims, r.key_col)
    r4 = read_roster(x)
    assert {z.key for z in r4.rows}.isdisjoint({"1096", "1104"}) and len(r4.rows) == 14
    # a backup was taken
    assert os.listdir(os.path.join(d, "backups"))


def test_excel_locked_is_reported(env, monkeypatch):
    d, x, db, r = env

    def deny(*a, **k):
        raise PermissionError("locked")
    monkeypatch.setattr(excel_write.os, "replace", deny)
    with pytest.raises(excel_write.ExcelBusy):
        excel_write.add_row(x, {"Name": "A"}, set())
    assert len(read_roster(x).rows) == 15          # untouched
    assert not [f for f in os.listdir(d) if f.startswith("~autosend")]


def test_contacts_lists_and_rules(env):
    d, x, db, r = env
    cid = db.save_contact(None, {"Name": "Teacher Nimal", "Phone": "0771112222", "Role": "Teacher"})
    bad = db.save_contact(None, {"Name": "No Number", "Phone": ""})
    everyone = all_recipients(db, r.name_col, "94")
    assert len(everyone) == 17
    t = get_recipient(db, f"c:{cid}", r.name_col, "94")
    assert t.phone == "94771112222" and t.values["Name"] == "Teacher Nimal" and t.type_label == "Contact"
    assert get_recipient(db, f"c:{bad}", r.name_col, "94").phone is None
    assert get_recipient(db, "1096", r.name_col, "94").kind == "student"

    # static list mixing a student and a contact
    lid = db.save_list(None, "VIPs", "static", {}, None)
    assert db.add_members(lid, ["1096", f"c:{cid}", "1096"]) == 2
    lst = db.get_list(lid)
    assert {p.ref for p in list_members(db, lst, everyone)} == {"1096", f"c:{cid}"}

    # smart lists
    rule = {"match": "all", "conds": [{"field": "Class", "op": "is", "value": "grade 9 a"}]}
    smart = {"kind": "smart", "rule": rule, "id": 0}
    g9a = list_members(db, smart, everyone)
    assert g9a and all(p.values["Class"] == "Grade 9 A" for p in g9a)
    rich = {"match": "all", "conds": [{"field": "Outstanding Amount(Rs.)", "op": "gt", "value": "30000"},
                                      {"field": "Type", "op": "is", "value": "Student"}]}
    assert all(int(p.values["Outstanding Amount(Rs.)"]) > 30000 for p in list_members(db, {"kind": "smart", "rule": rich}, everyone))
    anyof = {"match": "any", "conds": [{"field": "Role", "op": "is", "value": "Teacher"},
                                       {"field": "Class", "op": "is", "value": "Grade 6 A"}]}
    got = list_members(db, {"kind": "smart", "rule": anyof}, everyone)
    assert any(p.kind == "contact" for p in got) and any(p.values.get("Class") == "Grade 6 A" for p in got)
    assert list_members(db, {"kind": "smart", "rule": {"conds": []}}, everyone) == []
    assert "Class is “grade 9 a”" in describe_rule(rule)

    # deleting things cleans up membership
    db.delete_contacts([cid])
    assert f"c:{cid}" not in db.member_refs(lid)
    db.rename_student_key("1096", "1096X")
    assert db.member_refs(lid) == ["1096X"]
    db.delete_list(lid)
    assert db.get_list(lid) is None and db.member_refs(lid) == []
