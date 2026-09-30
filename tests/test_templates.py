import os
import shutil
import sys
import tempfile

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
import pytest
from PySide6.QtWidgets import QApplication, QInputDialog, QMessageBox

app = QApplication.instance() or QApplication([])
from conftest import SAMPLE_XLSX as SRC, make_toast


@pytest.fixture()
def page(monkeypatch):
    d = tempfile.mkdtemp()
    monkeypatch.setenv("AUTOSEND_DATA", d)
    x = os.path.join(d, "l.xlsx")
    shutil.copy(SRC, x)
    from autosend.services import AppContext
    from autosend.ui.templates import TemplatesPage
    from autosend.ui.widgets import Toast
    from PySide6.QtWidgets import QWidget
    ctx = AppContext()
    ctx.db.set("excel_path", x)
    ctx.reload(force=True)
    host = QWidget()
    opened, went = [], []
    p = TemplatesPage(ctx, Toast(host), went.append, opened.append)
    p.opened, p.went = opened, went
    yield p
    ctx.db.close()


def _answer(monkeypatch, text, ok=True):
    monkeypatch.setattr(QInputDialog, "getText", staticmethod(lambda *a, **k: (text, ok)))


def test_create_opens_editor(page, monkeypatch):
    _answer(monkeypatch, "September reminder")
    page.new_template()
    t = [x for x in page.ctx.db.list_templates() if x["name"] == "September reminder"]
    assert len(t) == 1 and page.opened == [t[0]["id"]]


def test_duplicate_names_are_refused(page, monkeypatch):
    page.ctx.db.save_template(None, "A", "hello", "")
    monkeypatch.setattr(QMessageBox, "information", staticmethod(lambda *a, **k: None))
    _answer(monkeypatch, "a")                               # same name, different case
    page.new_template()
    assert [x["name"] for x in page.ctx.db.list_templates()].count("A") == 1
    assert page.opened == []


def test_rename_duplicate_delete(page, monkeypatch):
    db = page.ctx.db
    a = db.save_template(None, "A", "body {Name}", "")
    b = db.save_template(None, "B", "other", "")
    _answer(monkeypatch, "A renamed")
    page.rename(a)
    assert db.get_template(a)["name"] == "A renamed" and db.get_template(a)["body"] == "body {Name}"
    page.duplicate(a)
    page.duplicate(a)
    names = [t["name"] for t in db.list_templates()]
    assert "A renamed (copy)" in names and "A renamed (copy) 2" in names
    # deleting the one that is chosen for sending / editing moves those pointers to another template
    db.set("send_template", b)
    db.set("active_template", b)
    monkeypatch.setattr(QMessageBox, "question", staticmethod(lambda *a, **k: QMessageBox.Yes))
    page.delete(b)
    assert db.get_template(b) is None
    assert db.get("send_template") != b and db.get_template(db.get("send_template"))
    assert db.get_template(db.get("active_template"))


def test_cannot_delete_last_template(page, monkeypatch):
    db = page.ctx.db
    for t in db.list_templates()[1:]:
        db.delete_template(t["id"])
    only = db.list_templates()
    if not only:
        db.save_template(None, "Only", "x", "")
        only = db.list_templates()
    monkeypatch.setattr(QMessageBox, "information", staticmethod(lambda *a, **k: None))
    monkeypatch.setattr(QMessageBox, "question", staticmethod(lambda *a, **k: QMessageBox.Yes))
    page.delete(only[0]["id"])
    assert len(db.list_templates()) == 1


def test_use_to_send_selects_it_for_the_send_screen(page):
    tid = page.ctx.db.save_template(None, "Notice", "hi", "")
    page.use_to_send(tid)
    assert page.ctx.db.get("send_template") == tid and page.went == ["home"]
