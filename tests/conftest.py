"""Shared test data: a small, entirely fictional student sheet (never the client's real file)."""
import os
import sys
from pathlib import Path

import openpyxl

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

FIXTURES = Path(__file__).resolve().parent / "fixtures"
SAMPLE_XLSX = str(FIXTURES / "students.xlsx")

HEADER = ["Admission No.", "Name", "Class", "Whatsapp Number", "Outstanding Amount(Rs.)"]
ROWS = [
    ("1096", "Student One", "Grade 9 A", "+94 70 000 0001", 32000),
    ("1103", "Student Two", "Grade 4 A", "+94 70 000 0002", 27000),
    ("1104", "Student Three", "Grade 9 A", "+94 70 000 0003", 31000),
    ("1106", "Student Four", "Grade 4 A", "0700000004", 27000),
    ("1110", "Student Five", "Grade 4 C", "70 000 0005", 27675),
    ("1111", "Student Six", "Grade 4 A", "+94 70 000 0006", 27000),
    ("1112", "Student Seven", "Grade 4 C", "+94 70 000 0007", 27000),
    ("1113", "Student Eight", "Grade 4 C", "+94 70 000 0008", 27000),
    ("1116", "Student Nine", "Grade 9 B", "+94 70 000 0009", 32000),
    ("1117", "Student Ten", "Grade 9 A", "+94 70 000 0010", 33000),
    ("1119", "Student Eleven", "Grade 9 B", "+94 70 000 0011", 95487),
    ("1121", "Student Twelve", "Grade 4 B", "+94 70 000 0012", 28100),
    ("1123", "Student Thirteen", "Grade 6 A", "+94 70 000 0013", 31000),
    ("1124", "Student Fourteen", "Grade 9 A", "+94 70 000 0014", 33000),
    ("1125", "Student Fifteen", "Grade 6 A", "+94 70 000 0015", 28000),
]


def _build() -> None:
    FIXTURES.mkdir(exist_ok=True)
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Sheet 1"
    ws.append(HEADER)
    for r in ROWS:
        ws.append(list(r))
    wb.save(SAMPLE_XLSX)


_build()          # always rebuilt, so the fixture can never drift


import shutil
import tempfile

import pytest


@pytest.fixture()
def app_ctx(monkeypatch):
    """A real AppContext on a temporary data folder with a copy of the fictional sample sheet."""
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication
    QApplication.instance() or QApplication([])
    d = tempfile.mkdtemp()
    monkeypatch.setenv("AUTOSEND_DATA", d)
    x = os.path.join(d, "students.xlsx")
    shutil.copy(SAMPLE_XLSX, x)
    from autosend.services import AppContext
    c = AppContext()
    c.db.set("excel_path", x)
    c.reload(force=True)
    yield c
    c.db.close()


_keep = []


def make_toast():
    """A Toast whose parent window stays alive for the whole test session."""
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication, QWidget
    QApplication.instance() or QApplication([])
    from autosend.ui.widgets import Toast
    host = QWidget()
    _keep.append(host)
    return Toast(host)
