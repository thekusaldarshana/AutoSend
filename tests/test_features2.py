import os
import sys
import time
from datetime import datetime

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
import pytest
from PySide6.QtCore import QPoint, Qt
from PySide6.QtGui import QImage
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QDialog, QLabel, QMessageBox, QWidget

app = QApplication.instance() or QApplication([])

from conftest import make_toast
from autosend.core.history import in_period, natural_key, period_range


def D(y, m, d, h=12):
    return datetime(y, m, d, h, 0)


def ts(y, m, d, h=12):
    return time.mktime(D(y, m, d, h).timetuple())


# ------------------------------------------------------------- time periods
def test_periods_including_the_edge_cases_you_described():
    now = D(2026, 2, 18)                                       # a Wednesday in February
    assert in_period(ts(2026, 2, 18), "today", now) and not in_period(ts(2026, 2, 17), "today", now)
    assert in_period(ts(2026, 2, 16), "week", now) and not in_period(ts(2026, 2, 15), "week", now)      # weeks start Monday
    assert in_period(ts(2026, 2, 1, 0), "month", now) and not in_period(ts(2026, 1, 31), "month", now)
    # in February, "last month" is January
    assert in_period(ts(2026, 1, 1, 0), "last_month", now) and in_period(ts(2026, 1, 31, 23), "last_month", now)
    assert not in_period(ts(2026, 2, 1, 0), "last_month", now) and not in_period(ts(2025, 12, 31), "last_month", now)
    # in January, "last month" is December of the previous year
    jan = D(2026, 1, 10)
    assert in_period(ts(2025, 12, 5), "last_month", jan) and not in_period(ts(2026, 1, 2), "last_month", jan)
    # in March, "last month" is February (28 days in 2026)
    assert in_period(ts(2026, 2, 28), "last_month", D(2026, 3, 9)) and not in_period(ts(2026, 3, 1, 0), "last_month", D(2026, 3, 9))
    # last 3 months is rolling and copes with short months: 31 May minus 3 months = 28 Feb
    may = D(2026, 5, 31)
    assert in_period(ts(2026, 2, 28), "three_months", may) and not in_period(ts(2026, 2, 27), "three_months", may)
    assert in_period(ts(2026, 5, 31, 23), "three_months", may)
    assert in_period(ts(2026, 1, 1, 0), "year", now) and not in_period(ts(2025, 12, 31), "year", now)
    assert in_period(None, "all") and not in_period(None, "today", now)
    assert period_range("all") == (None, None)


def test_natural_class_order():
    names = ["Grade 10 A", "Grade 4 C", "Grade 4 A", "Grade 9 B"]
    assert sorted(names, key=natural_key) == ["Grade 4 A", "Grade 4 C", "Grade 9 B", "Grade 10 A"]


# ------------------------------------------------------------- database
def test_daily_limit_survives_clearing_history(app_ctx):
    db = app_ctx.db
    cid = db.create_campaign("t", "hi", "", [("1096", "One", "94700000001", "Grade 9 A"), ("1103", "Two", "94700000002", "Grade 4 A")])
    for s in (db.next_pending(cid),):
        db.update_send(s["id"], "sent")
    s2 = db.next_pending(cid)
    db.update_send(s2["id"], "sent")
    assert db.sent_today() == 2
    db.delete_campaigns([cid])
    assert db.list_campaigns() == [] and db.sent_today() == 2      # the safety limit can't be reset by clearing history


def test_class_is_snapshotted_when_a_run_starts(app_ctx):
    db = app_ctx.db
    cid = db.create_campaign("t", "hi", "", [("1096", "One", "94700000001", "Grade 9 A"), ("x", "NoClass", None)])
    assert [s["grp"] for s in db.list_sends(cid)] == ["Grade 9 A", ""]


# ------------------------------------------------------------- history page
def _seed_history(ctx):
    db = ctx.db
    plan = [                                    # (name, when, [(ref, label, class, status)])
        ("Today run", ts(2026, 9, 30, 9), [("1096", "One", "Grade 9 A", "sent"), ("1103", "Two", "Grade 4 A", "failed"), ("1104", "Three", "Grade 9 A", "sent")]),
        ("Last month run", ts(2026, 8, 12), [("1110", "Five", "Grade 4 C", "sent"), ("1117", "Ten", "Grade 9 A", "skipped")]),
        ("Old run", ts(2026, 3, 3), [("1123", "Thirteen", "Grade 6 A", "sent")]),
    ]
    ids = []
    for name, when, people in plan:
        cid = db.create_campaign(name, "hi", "", [(r, n, "94700000001", g) for r, n, g, _s in people])
        db._x("UPDATE campaigns SET created_at=?, state='finished' WHERE id=?", (when, cid))
        for send, (_r, _n, _g, st) in zip(db.list_sends(cid), people):
            db.update_send(send["id"], st, "why" if st != "sent" else None)
            db._x("UPDATE sends SET sent_at=? WHERE id=?", (when + 60, send["id"]))
        ids.append(cid)
    return ids


@pytest.fixture()
def history(app_ctx, monkeypatch):
    from autosend.ui import history as H
    from autosend.ui.widgets import Toast
    now = D(2026, 9, 30, 15)

    class FixedNow(datetime):
        @classmethod
        def now(cls, tz=None):
            return now
    monkeypatch.setattr("autosend.core.history.datetime", FixedNow)
    ids = _seed_history(app_ctx)
    page = H.HistoryPage(app_ctx, make_toast())
    page.on_show()
    return page, ids


def _rows(page):
    return sorted(page.table.item(i, 0).text() for i in range(page.table.rowCount()))


def _pick(combo, data):
    combo.setCurrentIndex(combo.findData(data))


def test_history_filters_by_period_class_and_result(history):
    page, ids = history
    assert len(_rows(page)) == 6                                                   # all time
    _pick(page.period, "today")
    assert _rows(page) == ["One", "Three", "Two"]
    _pick(page.period, "last_month")
    assert _rows(page) == ["Five", "Ten"]
    _pick(page.period, "year")
    assert len(_rows(page)) == 6
    _pick(page.period, "all")
    # class list is natural-sorted and built from what happened
    assert [page.cls.itemText(i) for i in range(page.cls.count())] == ["All classes", "Grade 4 A", "Grade 4 C", "Grade 6 A", "Grade 9 A"]
    _pick(page.cls, "Grade 9 A")
    assert _rows(page) == ["One", "Ten", "Three"]
    _pick(page.result, "sent")
    assert _rows(page) == ["One", "Three"]
    # runs with no matching message disappear from the run list
    names = [page.runs.item(i).text().split("\n")[1].split("  ·")[0] for i in range(1, page.runs.count())]
    assert names == ["Today run"]
    _pick(page.cls, "")
    _pick(page.result, "")
    page.search.setText("thir")
    assert _rows(page) == ["Thirteen"]


def test_history_is_sorted_newest_first_and_columns_can_be_resorted(history):
    page, _ = history
    times = [page.table.item(i, 4).data(Qt.DisplayRole) for i in range(page.table.rowCount())]
    assert "30 Sep 2026" in times[0] and "03 Mar 2026" in times[-1]
    page.table.sortItems(1, Qt.AscendingOrder)                                     # by class, naturally
    classes = [page.table.item(i, 1).text() for i in range(page.table.rowCount())]
    assert classes == sorted(classes, key=natural_key)


def _auto_confirm(monkeypatch, yes=True):
    monkeypatch.setattr(QMessageBox, "exec", lambda self: 0)

    def clicked(self):
        role = QMessageBox.DestructiveRole if yes else QMessageBox.RejectRole
        return next(b for b in self.buttons() if self.buttonRole(b) == role)
    monkeypatch.setattr(QMessageBox, "clickedButton", clicked)


def test_clear_history_options(history, monkeypatch):
    page, ids = history
    db = page.ctx.db
    _auto_confirm(monkeypatch, yes=False)
    page.delete_all()
    assert len(db.list_campaigns()) == 3                                            # cancelled: nothing happens
    _auto_confirm(monkeypatch)
    page.runs.setCurrentRow(1)                                                      # newest run
    page.delete_run()
    assert [c["name"] for c in db.list_campaigns()] == ["Last month run", "Old run"] or len(db.list_campaigns()) == 2
    _pick(page.period, "last_month")
    page.delete_period()                                                            # only that month's runs
    assert [c["name"] for c in db.list_campaigns()] == ["Old run"]
    page.delete_all()
    assert db.list_campaigns() == [] and page.table.rowCount() == 0
    assert not page.clear_btn.isEnabled() and "No runs yet" in page.empty.text()


def test_a_run_that_is_sending_is_never_deleted(history, monkeypatch):
    page, ids = history
    from autosend.core.sender import SendController
    monkeypatch.setattr(SendController, "active", property(lambda self: True))
    page.ctx.sender.campaign_id = ids[0]
    _auto_confirm(monkeypatch)
    monkeypatch.setattr(QMessageBox, "information", staticmethod(lambda *a, **k: None))
    page.delete_all()
    assert [c["id"] for c in page.ctx.db.list_campaigns()] == [ids[0]]


# ------------------------------------------------------------- students page
def test_ticking_a_row_selects_it(app_ctx):
    from autosend.ui.students import StudentsPage
    from autosend.ui.widgets import Toast
    page = StudentsPage(app_ctx, make_toast())
    page.resize(1100, 700)
    page.show()
    page.on_show()
    app.processEvents()
    tbl = page.table
    # a real mouse click on the tick box of the third row
    idx = tbl.model().index(2, 0)
    rect = tbl.visualRect(idx)
    app_ctx.db.set_all_selected(False)
    page.refresh()
    assert tbl.selectionModel().selectedRows() == []
    QTest.mouseClick(tbl.viewport(), Qt.LeftButton, Qt.NoModifier, QPoint(rect.left() + 14, rect.center().y()))
    app.processEvents()
    assert [i.row() for i in tbl.selectionModel().selectedRows()] == [2]
    assert app_ctx.students()[2]["selected"] is True
    assert page.edit_btn.isEnabled() and page.del_btn.isEnabled()
    # ticking another adds to the selection; unticking removes just that one
    rect5 = tbl.visualRect(tbl.model().index(5, 0))
    QTest.mouseClick(tbl.viewport(), Qt.LeftButton, Qt.NoModifier, QPoint(rect5.left() + 14, rect5.center().y()))
    assert sorted(i.row() for i in tbl.selectionModel().selectedRows()) == [2, 5]
    QTest.mouseClick(tbl.viewport(), Qt.LeftButton, Qt.NoModifier, QPoint(rect.left() + 14, rect.center().y()))
    assert [i.row() for i in tbl.selectionModel().selectedRows()] == [5]
    assert app_ctx.students()[2]["selected"] is False
    # Select all / none highlight the rows too, and actions target exactly them
    page._select_all(True)
    assert len(page._selected_keys()) == len(app_ctx.students())
    page._select_all(False)
    assert page._selected_keys() == []


# ------------------------------------------------------------- quick send + confirm dialog
def test_quick_send_validates_and_does_not_touch_templates(app_ctx):
    from autosend.ui.quicksend import QuickSendDialog
    people = [p for p in app_ctx.recipients() if p.sendable][:3]
    before = app_ctx.db.list_templates()
    dlg = QuickSendDialog(app_ctx, people, "list “Test”", None)
    assert not dlg.send.isEnabled()                                                 # nothing typed yet
    dlg.editor.setPlainText("Hello {Nmae}")
    assert not dlg.send.isEnabled() and "Not a known detail" in dlg.warn.text.text()
    dlg.editor.setPlainText("Dear parent of {Name},\n\n*Reminder*: school is closed tomorrow.")
    assert dlg.send.isEnabled() and dlg.send.text() == "Send 3 messages"
    assert "Student One" in dlg.bubble.text()                                       # live preview for the first person
    assert app_ctx.quick_draft["text"].startswith("Dear parent")                    # draft survives an accidental close
    dlg._accept()
    assert dlg.text.startswith("Dear parent of {Name}") and app_ctx.quick_draft["text"] == ""
    assert app_ctx.db.list_templates() == before                                    # not saved as a template


def test_quick_send_from_the_send_screen_creates_a_run_with_that_text(app_ctx, monkeypatch):
    from autosend.ui.home import HomePage
    from autosend.ui.quicksend import QuickSendDialog
    from autosend.ui.widgets import Toast
    home = HomePage(app_ctx, make_toast(), lambda k: None)
    started = []
    monkeypatch.setattr(home, "_begin", started.append)
    home.on_show()

    def fake_exec(self):
        self.editor.setPlainText("Quick note for {Name}")
        self._accept()
        return QDialog.Accepted
    monkeypatch.setattr(QuickSendDialog, "exec", fake_exec)
    n_templates = len(app_ctx.db.list_templates())
    home.quick_send()
    assert len(started) == 1
    camp = app_ctx.db.get_campaign(started[0])
    assert camp["name"] == "Quick message" and camp["body"] == "Quick note for {Name}"
    sends = app_ctx.db.list_sends(started[0])
    assert len(sends) == 15 and sends[0]["grp"] == "Grade 9 A"                     # everyone ticked, class recorded
    assert len(app_ctx.db.list_templates()) == n_templates


def test_confirm_dialog_shows_the_attached_photo(app_ctx, tmp_path):
    from autosend.ui.home import ConfirmSend
    png = tmp_path / "pic.png"
    img = QImage(300, 200, QImage.Format_RGB32)
    img.fill(0x2E7D32)
    img.save(str(png))

    def pixmaps(dlg):
        return [lb for lb in dlg.findChildren(QLabel) if lb.pixmap() is not None and not lb.pixmap().isNull()]
    with_photo = ConfirmSend(None, 5, "Reminder", "Hello", str(png), 300, 0, 0, "list “X”")
    assert len(pixmaps(with_photo)) == 1 and "with a photo" in " ".join(lb.text() for lb in with_photo.findChildren(QLabel))
    without = ConfirmSend(None, 5, "Reminder", "Hello", "", 300, 0, 0, "list “X”")
    assert pixmaps(without) == []
    long_text = ConfirmSend(None, 5, "Reminder", "x" * 1200, str(png), 300, 0, 0, "")
    assert any("photo is sent first" in lb.text() for lb in long_text.findChildren(QLabel))


def test_typing_test_lists_every_character():
    from autosend.ui.typingtest import describe
    text = describe("ක්‍ර")
    assert "U+0D9A" in text and "U+0DCA" in text and "U+200D  ZERO WIDTH JOINER" in text and "U+0DBB" in text
