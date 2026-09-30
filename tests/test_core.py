import os, sys, random, tempfile
from datetime import date, datetime
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from conftest import SAMPLE_XLSX
from autosend.core.phone import normalize_phone
from autosend.core.templating import Variable, render, suggest_variables, rename_in_body, format_date
from autosend.core.antiban import Pace, Scheduler, estimate_seconds, in_window, seconds_until_window, PRESETS, preset_name
from autosend.core.excel import read_roster, write_starter_workbook
from autosend.core.db import Database

def test_phone():
    assert normalize_phone("+94 70 000 0001") == ("94700000001", None)
    assert normalize_phone("0700000001")[0] == "94700000001"
    assert normalize_phone("700000001")[0] == "94700000001"
    assert normalize_phone(700000001.0)[0] == "94700000001"
    assert normalize_phone("700000001.0")[0] == "94700000001"
    assert normalize_phone("94700000001")[0] == "94700000001"
    assert normalize_phone("0700000001 / 0712345678")[0] == "94700000001"
    assert normalize_phone("0094700000001")[0] == "94700000001"
    assert normalize_phone("+44 7911 123456")[0] == "447911123456"
    assert normalize_phone("")[0] is None and normalize_phone(None)[0] is None
    assert normalize_phone("nan")[0] is None
    assert normalize_phone("12345")[0] is None
    assert normalize_phone("070000")[0] is None

def test_render():
    vs = suggest_variables(["Admission No.", "Name", "Class", "Whatsapp Number", "Outstanding Amount(Rs.)"], "Whatsapp Number")
    names = [v.name for v in vs]
    assert names == ["Admission", "Name", "Class", "Amount", "Today"], names
    row = {"Admission No.": "1096", "Name": "A B", "Class": "G9", "Outstanding Amount(Rs.)": "32000"}
    r = render("Hi {Name} ({admission}) owes Rs. {Amount}\n\nline2 *bold* {Today}", vs, row, date(2026, 9, 10))
    assert r.ok, r
    assert r.text == "Hi A B (1096) owes Rs. 32,000\n\nline2 *bold* 10/09/2026", repr(r.text)
    row["Name"] = ""
    r = render("{Name} {Nope}", vs, row)
    assert r.missing == ["Name"] and r.unknown == ["Nope"]
    assert rename_in_body("{Name} {name} {x}", "Name", "Student") == "{Student} {Student} {x}"
    assert format_date(date(2026, 9, 5), "d MMMM yyyy".replace("d ", "dd ")) == "05 September 2026"

def test_antiban():
    p = Pace()
    s = Scheduler(p, random.Random(1))
    gaps, breaks = [], 0
    for _ in range(400):
        w, b = s.pause_after_send()
        if b: breaks += 1; assert p.break_min*60 <= w <= p.break_max*60
        else: gaps.append(w); assert w >= p.gap_min
    assert breaks >= 8 and len(set(round(g) for g in gaps)) > 20
    assert 0 < estimate_seconds(p, 100) < 6*3600
    assert preset_name(Pace.from_dict(PRESETS["fast"])) == "fast"
    q = Pace(window_on=True, window_start=9, window_end=19)
    assert in_window(q, datetime(2026,9,1,10)) and not in_window(q, datetime(2026,9,1,20))
    assert seconds_until_window(q, datetime(2026,9,1,20)) == 13*3600

def test_excel_and_db():
    with tempfile.TemporaryDirectory() as d:
        r = read_roster(SAMPLE_XLSX)
        assert r.phone_col == "Whatsapp Number" and r.key_col == "Admission No." and r.name_col == "Name"
        assert len(r.rows) == 15 and all(x.phone for x in r.rows), [x.phone_error for x in r.rows]
        db = Database(os.path.join(d, "t.db"))
        diff = db.sync_students(r.rows)
        assert (diff.added, diff.updated, diff.removed) == (15, 0, 0)
        assert not db.sync_students(r.rows).changed
        r.rows[0].values["Class"] = "Grade 10"; r.rows.pop()
        diff = db.sync_students(r.rows)
        assert (diff.added, diff.updated, diff.removed) == (0, 1, 1), diff
        db.set_selected([r.rows[1].key], False)
        db.sync_students(r.rows)
        assert not db.get_student(r.rows[1].key)["selected"]
        cid = db.create_campaign("t", "hi", "", [(x.key, x.values["Name"], x.phone) for x in r.rows[:3]])
        assert db.counts(cid)["pending"] == 3
        s = db.next_pending(cid); db.update_send(s["id"], "sent", message="m"); assert db.counts(cid)["sent"] == 1
        assert db.sent_today() == 1 and db.open_campaign()["id"] == cid
        db.set("pace", {"a": 1}); assert db.get("pace") == {"a": 1}
        db.close()
        p = os.path.join(d, "s.xlsx"); write_starter_workbook(p)
        st = read_roster(p); assert len(st.rows) == 3 and st.rows[0].phone is None


def test_sender_with_fake_wa():
    import time
    from PySide6.QtCore import QCoreApplication
    from autosend.core.sender import SendController
    from autosend.core.whatsapp import NotOnWhatsApp
    app = QCoreApplication.instance() or QCoreApplication([])

    class FakeWA:
        ready = True
        def __init__(self): self.sent = []; self.bad = {"94771111111"}
        def resolve(self, ph):
            if ph in self.bad: raise NotOnWhatsApp("no")
            return ph
        def typing(self, *a, **k): pass
        def send_text(self, jid, text): self.sent.append((jid, text))
        def send_image(self, jid, path, cap): self.sent.append((jid, path, cap))

    with tempfile.TemporaryDirectory() as d:
        r = read_roster(SAMPLE_XLSX)
        r.rows[2].phone = "94771111111"          # not on WhatsApp
        r.rows[3].values["Class"] = ""           # empty variable -> skipped
        r.rows[4].phone = None                   # no number -> skipped
        db = Database(os.path.join(d, "t.db")); db.sync_students(r.rows)
        for v in __import__("autosend.core.templating", fromlist=["x"]).suggest_variables(r.columns, r.phone_col):
            db.save_variable(v)
        wa = FakeWA()
        fast = dict(gap_min=0.0, gap_max=0.0, batch_min=3, batch_max=3, break_min=0.0, break_max=0.0, typing=False)
        sc = SendController(db, wa, lambda: fast, lambda: r.name_col)
        cid = db.create_campaign("t", "Hi {Name} of {Class}, Rs {Amount}\n\nBye", "", [(x.key, x.values["Name"], x.phone) for x in r.rows[:8]])
        sc.start(cid)
        t0 = time.time()
        while sc.active and time.time() - t0 < 20:
            app.processEvents(); time.sleep(0.02)
        c = db.counts(cid)
        assert c == {"pending": 0, "sent": 5, "failed": 1, "skipped": 2, "total": 8}, c
        assert wa.sent[0][1].startswith("Hi Student One of Grade 9 A, Rs 32,000\n\nBye"), wa.sent[0]
        assert db.get_campaign(cid)["state"] == "finished"
        db.close()
