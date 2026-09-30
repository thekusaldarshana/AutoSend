"""Run a slow function off the UI thread and get the result back on it."""
from __future__ import annotations

import threading
import traceback
import logging

from PySide6.QtCore import QObject, Signal, Slot

log = logging.getLogger("autosend.bg")
_alive: set = set()


class _Bridge(QObject):
    done = Signal(object, object)

    def __init__(self, cb):
        super().__init__()
        self._cb = cb
        self.done.connect(self._finish)

    @Slot(object, object)
    def _finish(self, result, error):
        _alive.discard(self)
        try:
            self._cb(result, error)
        finally:
            self.deleteLater()


def run_async(fn, cb) -> None:
    """cb(result, error) is called on the UI thread."""
    br = _Bridge(cb)
    _alive.add(br)

    def work():
        try:
            br.done.emit(fn(), None)
        except Exception as e:  # noqa: BLE001
            log.warning("background task failed: %s", traceback.format_exc())
            br.done.emit(None, e)

    threading.Thread(target=work, daemon=True).start()
