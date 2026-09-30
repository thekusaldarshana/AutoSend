"""AutoSend entry point."""
from __future__ import annotations

import logging
import logging.handlers
import os
import sys
import traceback


def _setup_logging() -> None:
    from .core import paths
    handler = logging.handlers.RotatingFileHandler(paths.log_dir() / "autosend.log", maxBytes=1_000_000,
                                                   backupCount=3, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    root.addHandler(handler)

    def hook(exc_type, exc, tb):
        logging.getLogger("autosend").critical("Unhandled error:\n%s", "".join(traceback.format_exception(exc_type, exc, tb)))
    sys.excepthook = hook


def main() -> int:
    from PySide6.QtCore import QLockFile, Qt
    from PySide6.QtGui import QIcon
    from PySide6.QtWidgets import QApplication, QDialog, QMessageBox

    from .core import paths

    _setup_logging()
    log = logging.getLogger("autosend")
    os.environ.setdefault("QT_QPA_PLATFORM_THEME", "")
    app = QApplication(sys.argv)
    app.setApplicationName("AutoSend")
    app.setOrganizationName("AutoSend")
    app.setStyle("Fusion")

    from . import __version__
    from .ui import theme

    from .ui import fonts, inputfix
    fonts.load_bundled_fonts()         # Sinhala font that travels with the app
    inputfix.install(app)              # lets Helakuru and similar Sinhala typing tools work in text boxes
    app.setFont(theme.app_font(10))
    app.setStyleSheet(theme.build_qss())
    ico = paths.resource_path("assets/icon.ico")
    if ico.exists():
        app.setWindowIcon(QIcon(str(ico)))

    lock = QLockFile(str(paths.data_dir() / "autosend.lock"))
    lock.setStaleLockTime(0)
    if not lock.tryLock(200):
        QMessageBox.information(None, "AutoSend", "AutoSend is already open.\nLook for it on your taskbar.")
        return 0

    from .services import AppContext
    from .ui.link import WelcomeWizard
    from .ui.main_window import MainWindow

    log.info("AutoSend %s starting", __version__)
    ctx = AppContext()
    theme.apply(app, ctx.db.get("theme_mode", "system"))
    _busy = []

    def _os_scheme_changed(*_):
        if not _busy and ctx.db.get("theme_mode", "system") == "system":
            _busy.append(1)
            try:
                theme.apply(app, "system")
            finally:
                _busy.clear()
    app.styleHints().colorSchemeChanged.connect(_os_scheme_changed)
    ctx.start()
    ctx.wa.start()
    win = MainWindow(ctx)
    win.show()
    start_page = os.environ.get("AUTOSEND_START_PAGE")          # used by automated checks
    if start_page in win.pages:
        win.goto(start_page)

    smoke = bool(os.environ.get("AUTOSEND_SMOKE"))
    if smoke:
        from PySide6.QtCore import QTimer
        QTimer.singleShot(int(os.environ["AUTOSEND_SMOKE"]) * 1000, app.quit)
    if not ctx.db.get("onboarded") or not ctx.excel_path:
        wiz = WelcomeWizard(ctx, win)
        if smoke:
            QTimer.singleShot(2500, wiz.reject)
        wiz.exec()
        ctx.db.set("onboarded", True)
        win.goto("home")

    code = app.exec()
    log.info("shutting down")
    ctx.shutdown()
    lock.unlock()
    logging.shutdown()
    os._exit(code)          # the WhatsApp engine has native threads; don't wait on them


if __name__ == "__main__":
    raise SystemExit(main())
