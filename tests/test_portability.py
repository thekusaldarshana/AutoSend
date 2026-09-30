"""AutoSend must not depend on anything about the computer it was built on."""
import os
import re
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
import pytest
from PySide6.QtCore import QStandardPaths
from PySide6.QtWidgets import QApplication

app = QApplication.instance() or QApplication([])
from autosend.core import paths

ROOT = Path(__file__).resolve().parents[1]


def test_documents_folder_follows_windows_not_a_guess(monkeypatch, tmp_path):
    redirected = tmp_path / "OneDrive - School" / "Dokumente"          # OneDrive backup, another language, another drive...
    monkeypatch.setattr(QStandardPaths, "writableLocation", staticmethod(lambda loc: str(redirected)))
    assert paths.user_documents() == redirected
    assert paths.documents_dir() == redirected / "AutoSend"


def test_documents_falls_back_to_home_if_windows_gives_nothing(monkeypatch):
    monkeypatch.setattr(QStandardPaths, "writableLocation", staticmethod(lambda loc: ""))
    assert paths.user_documents() == Path.home()


def test_app_data_goes_to_the_current_users_profile(monkeypatch, tmp_path):
    monkeypatch.delenv("AUTOSEND_DATA", raising=False)
    monkeypatch.setenv("APPDATA", str(tmp_path / "SomeOtherUser" / "Roaming"))
    d = paths.data_dir()
    assert d == tmp_path / "SomeOtherUser" / "Roaming" / "AutoSend" and d.is_dir()
    assert paths.db_path().parent == d and paths.session_db_path().parent == d and paths.log_dir().parent == d


def test_nothing_in_the_shipped_code_is_tied_to_a_computer_or_a_person():
    """No drive letters, user names, home folders or personal data in anything that ships."""
    bs = chr(92)                                            # a backslash, spelled out so no editor can mangle it
    banned = re.compile(rf"(?<![A-Za-z])[A-Za-z]:[{bs}{bs}/](?!n)|/Users/|{bs}{bs}Users{bs}{bs}|Desktop[{bs}{bs}/]|@gmail")
    offenders = []
    for folder in ("autosend", "installer", "tools"):
        for f in (ROOT / folder).rglob("*"):
            if f.suffix not in (".py", ".iss") or "output" in f.parts:
                continue
            for n, line in enumerate(f.read_text(encoding="utf-8", errors="ignore").splitlines(), 1):
                if banned.search(line) and "desktopicon" not in line and "autodesktop" not in line and "on my Desktop" not in line:
                    offenders.append(f"{f.relative_to(ROOT)}:{n}: {line.strip()[:80]}")
    assert not offenders, offenders


def test_only_paths_py_decides_where_folders_are():
    offenders = []
    for f in (ROOT / "autosend").rglob("*.py"):
        if f.name == "paths.py":
            continue
        text = f.read_text(encoding="utf-8")
        for token in ('"Documents"', "Path.home()", "USERPROFILE", "APPDATA", "expanduser"):
            if token in text:
                offenders.append(f"{f.name}: {token}")
    assert not offenders, offenders
