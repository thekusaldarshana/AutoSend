"""Where AutoSend keeps things. Program files are read-only; user data lives in %APPDATA%."""
import os
import sys
from pathlib import Path

APP_NAME = "AutoSend"


def data_dir() -> Path:
    override = os.environ.get("AUTOSEND_DATA")
    base = Path(override) if override else Path(os.environ.get("APPDATA") or Path.home()) / APP_NAME
    base.mkdir(parents=True, exist_ok=True)
    return base


def sub_dir(name: str) -> Path:
    p = data_dir() / name
    p.mkdir(parents=True, exist_ok=True)
    return p


def db_path() -> Path:
    return data_dir() / "autosend.db"


def session_db_path() -> Path:
    return data_dir() / "whatsapp-session.db"


def log_dir() -> Path:
    return sub_dir("logs")


def media_dir() -> Path:
    return sub_dir("media")


def user_documents() -> Path:
    """This person's real Documents folder. Ask Windows: it may be on OneDrive, another drive, or have another name."""
    from PySide6.QtCore import QStandardPaths
    loc = QStandardPaths.writableLocation(QStandardPaths.DocumentsLocation)
    return Path(loc) if loc else Path.home()


def documents_dir() -> Path:
    """The folder the installer puts the starter Excel file in (a folder called AutoSend inside Documents)."""
    return user_documents() / APP_NAME


def resource_path(rel: str) -> Path:
    """Bundled read-only resource (works in dev and inside the PyInstaller build)."""
    base = getattr(sys, "_MEIPASS", None)
    if base:
        return Path(base) / rel
    return Path(__file__).resolve().parents[2] / rel
